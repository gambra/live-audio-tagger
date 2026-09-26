"""Local, best-effort reading of taper info files and extra folder contents."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from tagger_core import ExtraFile, SUPPORTED, natural_key, stamp

EXCLUDED_EXTRAS = SUPPORTED | {'.ffp', '.md5', '.txt'}


@dataclass
class InfoGuess:
    fields: dict[str, str] = field(default_factory=dict)
    titles: list[str] = field(default_factory=list)
    files: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def guess_date(text: str) -> str | None:
    patterns = [r'\b\d{4}[-/.]\d{1,2}[-/.]\d{1,2}\b',
                r'\b\d{1,2}[-/.]\d{1,2}[-/.]\d{4}\b',
                r'\b\d{1,2}\s+[A-Za-z]+\s+\d{4}\b',
                r'\b[A-Za-z]+\s+\d{1,2},?\s+\d{4}\b']
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            value = re.sub(r'[,./]', lambda m: '-' if m[0] in './' else '', match[0])
            for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%m-%d-%Y', '%d %B %Y',
                        '%d %b %Y', '%B %d %Y', '%b %d %Y'):
                try:
                    return datetime.strptime(value, fmt).date().isoformat()
                except ValueError:
                    pass
    return None


ALIASES = {
    'artist': 'artist', 'band': 'artist', 'performer': 'artist',
    'date': 'date', 'show date': 'date', 'recording date': 'date',
    'venue': 'venue', 'city': 'city', 'country': 'country',
    'album': 'album', 'album title': 'album', 'title': 'album',
    'source': 'source', 'recording source': 'source',
    'lineage': 'tech_notes', 'source/lineage': 'tech_notes',
    'transfer': 'tech_notes', 'equipment': 'tech_notes', 'gear': 'tech_notes',
    'tech notes': 'tech_notes', 'technical notes': 'tech_notes',
    'taper': 'taper', 'recorded by': 'taper', 'taped by': 'taper',
    'location': 'location', 'taping location': 'taping_location',
    'show notes': 'show_notes', 'notes': 'show_notes', 'comments': 'show_notes',
    'genre': 'genre',
}
KEYS = '|'.join(re.escape(k) for k in sorted(ALIASES, key=len, reverse=True))
FIELD = re.compile(rf'^\s*({KEYS})\s*(?::|=|\s+-\s+)\s*(.*)$', re.I)
TRACK = re.compile(r'^\s*(?:d\d+\s*)?(?:t)?(\d{1,3})(?:[.)\]:-]\s*|\s+[-–—]\s*|\s+)(.+)$', re.I)
DURATION = re.compile(r'\s*(?:\[|\()?\d{1,3}:\d{2}(?::\d{2})?(?:\]|\))?\s*$')


def parse_info(text: str) -> InfoGuess:
    result = InfoGuess()
    lines = [line.strip() for line in text.replace('\r\n', '\n').splitlines()]
    header = []
    section = None
    in_tracks = False
    for line in lines:
        if not line:
            if section not in ('tech_notes', 'show_notes'):
                section = None
            continue
        if re.fullmatch(r'[-=_*~]{3,}', line):
            section = None
            in_tracks = False
            continue
        if re.match(r'^(?:format|total(?: running time| time| size)?|running time|length|size)\s*:', line, re.I):
            section = None
            continue
        if re.match(r'^(?:track\s*list(?:ing)?|set\s*list|tracks)\s*:?$', line, re.I):
            in_tracks, section = True, None
            continue
        found = FIELD.match(line)
        if found:
            in_tracks = False
            key = ALIASES[found[1].lower()]
            value = found[2].strip()
            section = key
            if key == 'date':
                value = guess_date(value) or ''
            if key in ('tech_notes', 'show_notes') and value:
                result.fields[key] = '\n'.join(filter(None, [result.fields.get(key), value]))
            elif value:
                result.fields.setdefault(key, value)
            continue
        track = TRACK.match(line)
        if track and not guess_date(line):
            title = DURATION.sub('', track[2]).strip().lstrip('-–— ').strip()
            if title:
                result.titles.append(title)
                in_tracks = True
                section = None
                continue
        if in_tracks:
            if not re.match(r'^(?:disc|cd|set|encore)\s*\d*\s*:?$', line, re.I):
                result.titles.append(DURATION.sub('', line).strip())
            continue
        if section in ('tech_notes', 'show_notes', 'source'):
            result.fields[section] = '\n'.join(filter(None, [result.fields.get(section), line]))
        elif section and not result.fields.get(section):
            result.fields[section] = guess_date(line) if section == 'date' else line
        elif len(header) < 12 and not re.match(r'^(?:format|total|length|size|disc|cd)\b', line, re.I):
            header.append(line)

    # Loose headers commonly contain Artist / Venue / City, Country / Date.
    dated = next((i for i, line in enumerate(header) if guess_date(line)), None)
    if dated is not None:
        result.fields.setdefault('date', guess_date(header[dated]))
    candidates = [line for line in header if not guess_date(line)]
    infer_header = dated is not None or bool(result.fields.get('date'))
    if candidates and infer_header:
        result.fields.setdefault('artist', candidates[0])
    if len(candidates) >= 2 and infer_header:
        result.fields.setdefault('venue', candidates[1])
    location = result.fields.pop('location', '')
    if not location and len(candidates) >= 3 and infer_header:
        location = candidates[2]
    if location:
        parts = [p.strip() for p in location.split(',')]
        result.fields.setdefault('city', parts[0])
        if len(parts) > 1:
            result.fields.setdefault('country', parts[-1])
    source = result.fields.get('source', '')
    if source and (len(source) > 60 or re.search(r'[<>:"/\\|?*\n]', source)):
        result.fields['tech_notes'] = '\n'.join(filter(None, [source, result.fields.get('tech_notes')]))
        kind = re.search(r'\b(AUD|SBD|FM|MATRIX)\b', source, re.I)
        if kind:
            result.fields['source'] = kind[1].upper()
        else:
            result.fields.pop('source', None)
    if not result.fields.get('album') and all(result.fields.get(k) for k in ('artist', 'date', 'venue')):
        result.fields['album'] = f"{result.fields['artist']} - {result.fields['date']} - {result.fields['venue']}"
    result.fields = {k: v for k, v in result.fields.items() if v}
    return result


def read_info_files(paths: list[Path]) -> InfoGuess:
    guesses = []
    warnings = []
    for path in sorted(paths, key=natural_key):
        try:
            with path.open('rb') as handle:
                data = handle.read(2 * 1024 * 1024 + 1)
            if len(data) > 2 * 1024 * 1024:
                warnings.append(f'Skipped oversized info text: {path}')
                continue
            if data.startswith((b'\xff\xfe', b'\xfe\xff')):
                text = data.decode('utf-16')
            else:
                try:
                    text = data.decode('utf-8-sig')
                except UnicodeDecodeError:
                    text = data.decode('cp1252', errors='replace')
            guess = parse_info(text)
            guess.files = [path]
            guesses.append(guess)
        except (OSError, UnicodeError) as exc:
            warnings.append(f'Could not read {path}: {exc}')
    # Prefer the richest info file; fill missing fields from the others, without
    # concatenating duplicate tracklists from multiple copies of the same notes.
    guesses.sort(key=lambda g: (len(g.fields), bool(g.titles)), reverse=True)
    result = InfoGuess(warnings=warnings)
    for guess in guesses:
        result.files.extend(guess.files)
        for key, value in guess.fields.items():
            result.fields.setdefault(key, value)
        if not result.titles:
            result.titles = guess.titles
    return result


def scan_folder(root: Path) -> tuple[list[Path], InfoGuess, list[ExtraFile]]:
    root = root.resolve()
    audio, texts, extras, warnings = [], [], [], []
    def linked(path):
        return path.is_symlink() or getattr(path, 'is_junction', lambda: False)()
    def scan_error(exc):
        warnings.append(f'Could not scan folder: {exc}')
    for current, dirs, files in os.walk(root, followlinks=False, onerror=scan_error):
        directory = Path(current)
        dirs[:] = [name for name in dirs if not linked(directory / name)]
        if directory != root and not dirs and not files:
            extras.append(ExtraFile(directory, directory.relative_to(root), None))
        for name in files:
            path = directory / name
            if linked(path):
                continue
            suffix = path.suffix.lower()
            if suffix in SUPPORTED:
                audio.append(path)
            elif suffix == '.txt':
                texts.append(path)
            elif suffix not in EXCLUDED_EXTRAS:
                extras.append(ExtraFile(path, path.relative_to(root), stamp(path)))
    info = read_info_files(texts)
    info.warnings.extend(warnings)
    return sorted(audio, key=natural_key), info, sorted(extras, key=lambda e: natural_key(e.relative))
