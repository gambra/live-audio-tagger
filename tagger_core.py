"""Audio packaging engine. Never modifies inputs during export."""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
import sys
from array import array
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from threading import Event
from typing import Callable

import soundfile as sf
from jinja2 import StrictUndefined, TemplateError
from jinja2.sandbox import SandboxedEnvironment
from mutagen.flac import FLAC
from mutagen.id3 import TIT2, TALB, TPE1, TDRC, TRCK, TCON, COMM, TXXX
from mutagen.mp3 import MP3

SUPPORTED = {'.flac', '.wav', '.aif', '.aiff', '.mp3'}
INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED = re.compile(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', re.I)
DEFAULT_FOLDER_PATTERN = '{{artist}} - {{date}} - {{venue}}, {{city}}, {{country}} ({{source}})'


class ValidationError(ValueError):
    pass


class Cancelled(Exception):
    pass


@dataclass(frozen=True)
class AudioFile:
    path: Path
    kind: str
    bits: int | None
    rate: int
    channels: int
    duration: float
    frames: int
    title: str
    bitrate: int | None
    stamp: tuple[int, int]


@dataclass(frozen=True)
class Show:
    artist: str
    date: str
    venue: str
    city: str
    country: str
    album: str
    source: str
    genre: str = 'Rock'
    taper: str = ''
    taping_location: str = ''
    show_notes: str = ''
    tech_notes: str = ''

    @property
    def prefix(self) -> str:
        return re.sub(r'[^a-z0-9]', '', self.artist.lower())


@dataclass(frozen=True)
class ExtraFile:
    source: Path
    relative: Path
    stamp: tuple[int, int] | None  # None denotes an empty directory.


@dataclass(frozen=True)
class Plan:
    show: Show
    files: tuple[AudioFile, ...]
    titles: tuple[str, ...]
    outer: Path
    inner_name: str
    stem: str
    names: tuple[str, ...]
    format: str
    template: str
    compression: int
    extras: tuple[ExtraFile, ...] = ()

    @property
    def folder(self) -> Path:
        return self.outer / self.inner_name


def natural_key(path: Path):
    return tuple((1, int(p)) if p.isdigit() else (0, p.casefold())
                 for p in re.split(r'(\d+)', str(path)))


def stamp(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns


def inspect_audio(path: Path) -> AudioFile:
    path = path.resolve()
    ext = path.suffix.lower()
    if ext not in SUPPORTED:
        raise ValidationError(f'Unsupported file: {path.name}')
    initial = stamp(path)
    title = ''
    if ext == '.mp3':
        audio = MP3(path)
        info = audio.info
        if info.channels not in (1, 2):
            raise ValidationError(f'{path.name}: only mono/stereo is supported.')
        if audio.tags and audio.tags.get('TIT2'):
            title = str(audio.tags['TIT2'])
        result = AudioFile(path, 'mp3', None, info.sample_rate, info.channels,
                           info.length, 0, title, info.bitrate, initial)
    else:
        info = sf.info(str(path))
        if info.subtype not in ('PCM_16', 'PCM_24'):
            raise ValidationError(f'{path.name}: {info.subtype} is unsupported; use 16-bit or 24-bit integer PCM.')
        if info.channels not in (1, 2):
            raise ValidationError(f'{path.name}: only mono/stereo is supported.')
        if info.format not in ('FLAC', 'WAV', 'WAVEX', 'RF64', 'AIFF'):
            raise ValidationError(f'{path.name}: unsupported audio container {info.format}.')
        if ext == '.flac':
            title = FLAC(path).get('title', [''])[0]
        result = AudioFile(path, 'flac' if ext == '.flac' else 'pcm',
                           int(info.subtype[-2:]), info.samplerate, info.channels,
                           info.duration, info.frames, title, None, initial)
    if result.duration <= 0:
        raise ValidationError(f'{path.name}: empty audio file.')
    if stamp(path) != initial:
        raise ValidationError(f'{path.name}: changed while being inspected.')
    return result


def validate_component(value: str, label: str) -> str:
    if not value or value != value.strip() or value.endswith('.') or INVALID.search(value):
        raise ValidationError(f'{label}: enter text without leading/trailing spaces, trailing dots, or <>:"/\\|?* characters.')
    if value in ('.', '..') or RESERVED.match(value):
        raise ValidationError(f'{label}: reserved filename.')
    if len(value.encode('utf-8')) > 240:
        raise ValidationError(f'{label}: filename is too long.')
    return value


def duration_text(seconds: float) -> str:
    seconds = round(seconds)
    hours, rem = divmod(seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    return f'{hours}:{minutes:02}:{seconds:02}' if hours else f'{minutes:02}:{seconds:02}'


def template_context(plan: Plan, sizes: list[int]) -> dict:
    context = vars(plan.show).copy()
    context.update(prefix=plan.show.prefix, source_label=plan.show.source, title=plan.show.album)
    bitrates = sorted({round(f.bitrate / 1000) for f in plan.files if f.bitrate})
    context.update(
        format=plan.format, bit_depth=plan.files[0].bits or '',
        sample_rate=plan.files[0].rate, channels=plan.files[0].channels,
        bitrate='/'.join(map(str, bitrates)) + ' kbps' if bitrates else '',
        total_duration=duration_text(sum(f.duration for f in plan.files)),
        total_size=f'{sum(sizes) / (1024 ** 2):.2f} MiB',
        total_tracks=len(plan.files),
        tracklist=[f'{i:02} - {title} [{duration_text(f.duration)}]'
                   for i, (title, f) in enumerate(zip(plan.titles, plan.files), 1)],
        tracks=[dict(number=i, title=title, duration=duration_text(f.duration), filename=name)
                for i, (title, f, name) in enumerate(zip(plan.titles, plan.files, plan.names), 1)],
    )
    return context


def render_info(plan: Plan, sizes: list[int]) -> str:
    env = SandboxedEnvironment(undefined=StrictUndefined, autoescape=False,
                               trim_blocks=True, lstrip_blocks=True,
                               keep_trailing_newline=True)
    return env.from_string(plan.template).render(**template_context(plan, sizes)).rstrip() + '\n'


def render_folder_name(plan: Plan, pattern: str) -> str:
    if not pattern.strip():
        raise ValidationError('Enter an outer folder pattern in Settings, or restore the default.')
    context = template_context(plan, [f.stamp[0] for f in plan.files])
    # Metadata punctuation must not become a path separator. Tags/info keep original text.
    context = {key: INVALID.sub('-', value) if isinstance(value, str) else value
               for key, value in context.items()}
    context['artist'] = INVALID.sub('', plan.show.artist).strip().rstrip('.')
    try:
        env = SandboxedEnvironment(undefined=StrictUndefined, autoescape=False)
        name = env.from_string(pattern).render(**context)
    except TemplateError as exc:
        raise ValidationError(f'Outer folder pattern in Settings: {exc}') from exc
    if plan.files[0].kind == 'mp3':
        name += ' (MP3)'
    return validate_component(name, 'Outer folder pattern result')


def make_plan(files: list[AudioFile], show: Show, titles: list[str], output: Path,
              template: str, compression: int = 5, extras: tuple[ExtraFile, ...] = (), *,
              folder_pattern: str = DEFAULT_FOLDER_PATTERN, etree_subfolder: bool = True) -> Plan:
    if not files:
        raise ValidationError('Import audio files first.')
    if len({f.path for f in files}) != len(files):
        raise ValidationError('The same input file appears more than once.')
    if len(titles) != len(files) or any(not t.strip() for t in titles):
        raise ValidationError(f'Enter exactly {len(files)} non-empty track titles, one per line.')
    if any('\n' in t or '\r' in t for t in titles):
        raise ValidationError('Each track title must occupy one line.')
    try:
        parsed = date.fromisoformat(show.date)
        if parsed.isoformat() != show.date:
            raise ValueError()
    except ValueError:
        raise ValidationError('Date must be a real date in YYYY-MM-DD format.') from None
    if not show.prefix:
        raise ValidationError('Artist must contain at least one letter a-z or digit for filenames.')
    for field in ('venue', 'city', 'country', 'source'):
        if not getattr(show, field).strip():
            raise ValidationError(f'{field.title()} is required.')
    if not show.album.strip() or not show.source.strip():
        raise ValidationError('Album title and Source are required.')
    if not 0 <= compression <= 8:
        raise ValidationError('FLAC compression must be between 0 and 8.')
    kinds = {f.kind == 'mp3' for f in files}
    if len(kinds) > 1:
        raise ValidationError('MP3 and lossless files cannot share a package.')
    if len({(f.bits, f.rate) for f in files}) > 1:
        raise ValidationError('All tracks must have the same bit depth and sample rate.')
    for f in files:
        if stamp(f.path) != f.stamp:
            raise ValidationError(f'{f.path.name} changed after import; import the files again.')
    mp3 = files[0].kind == 'mp3'
    suffix = 'mp3' if mp3 else f'flac{files[0].bits}'
    stem = f'{show.prefix}{show.date}'
    inner = f'{stem}.{suffix}' if etree_subfolder else ''
    if inner:
        validate_component(inner, 'Audio folder')
    output = output.expanduser().resolve()
    if not output.is_dir():
        raise ValidationError('Choose an existing output directory.')
    names = tuple(f'{stem}t{i:02}.{"mp3" if mp3 else "flac"}' for i in range(1, len(files) + 1))
    fmt = ('MP3 (original encoding)' if mp3 else f'FLAC {files[0].bits}-bit')
    fmt += f' / {files[0].rate} Hz'
    plan = Plan(show, tuple(files), tuple(t.strip() for t in titles), output,
                inner, stem, names, fmt, template, compression, tuple(extras))
    plan = replace(plan, outer=output / render_folder_name(plan, folder_pattern))
    if plan.outer.exists():
        raise ValidationError(f'Output already exists; it will not be overwritten:\n{plan.outer}')
    for name in names:
        validate_component(name, 'Track filename')
        if os.name == 'nt' and len(str(plan.folder / name)) >= 250:
            raise ValidationError('Output path is too long. Choose a shorter destination or shorter folder details.')
    validate_extras(plan)
    render_info(plan, [f.stamp[0] for f in files])  # Reject broken templates before writing.
    return plan


def validate_extras(plan: Plan):
    occupied = {name.casefold(): 'file' for name in (*plan.names, f'{plan.stem}.txt',
                f'{plan.stem}.md5', f'{plan.stem}.ffp')}
    for extra in plan.extras:
        if extra.relative.is_absolute() or not extra.relative.parts or '..' in extra.relative.parts:
            raise ValidationError(f'Invalid extra-file path: {extra.relative}')
        for component in extra.relative.parts:
            validate_component(component, 'Extra-file name')
        if os.name == 'nt' and len(str(plan.folder / extra.relative)) >= 250:
            raise ValidationError(f'Extra-file output path is too long: {extra.relative}')
        key = extra.relative.as_posix().casefold()
        kind = 'dir' if extra.stamp is None else 'file'
        if key in occupied and not (kind == occupied[key] == 'dir'):
            raise ValidationError(f'Extra-file name conflicts with another output: {extra.relative}')
        occupied[key] = kind
        for parent in extra.relative.parents:
            if parent == Path('.'):
                continue
            parent_key = parent.as_posix().casefold()
            if occupied.get(parent_key) == 'file':
                raise ValidationError(f'Extra folder conflicts with an output file: {parent}')
            occupied[parent_key] = 'dir'
        if any(p.is_symlink() or getattr(p, 'is_junction', lambda: False)()
               for p in (extra.source, *extra.source.parents)):
            raise ValidationError(f'Extra-file links cannot be copied: {extra.source}')
        if extra.stamp is None:
            if not extra.source.is_dir():
                raise ValidationError(f'Extra folder is missing: {extra.source}')
        elif not extra.source.is_file() or stamp(extra.source) != extra.stamp:
            raise ValidationError(f'Extra file changed or is missing; import the folder again: {extra.source}')


def copy_extras(plan: Plan, folder: Path, cancel: Event, log: Callable[[str], None]):
    for extra in plan.extras:
        check_cancel(cancel)
        target = folder / extra.relative
        log(f'Copying extra: {extra.relative}')
        if extra.stamp is None:
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.md5()
        with extra.source.open('rb') as inp, target.open('xb') as out:
            while data := inp.read(1024 * 1024):
                check_cancel(cancel)
                digest.update(data)
                out.write(data)
        if stamp(extra.source) != extra.stamp or digest.hexdigest() != file_md5(target, cancel):
            raise ValidationError(f'Extra-file verification failed: {extra.relative}')
        shutil.copystat(extra.source, target)


def check_cancel(cancel: Event):
    if cancel.is_set():
        raise Cancelled('Export cancelled. Original files were preserved.')


def file_md5(path: Path, cancel: Event) -> str:
    digest = hashlib.md5()
    with path.open('rb') as handle:
        while data := handle.read(1024 * 1024):
            check_cancel(cancel)
            digest.update(data)
    return digest.hexdigest()


def pcm_md5(path: Path, bits: int, cancel: Event) -> str:
    """FLAC fingerprint: signed, interleaved, little-endian PCM at source depth."""
    digest = hashlib.md5()
    with sf.SoundFile(str(path)) as audio:
        while True:
            raw = bytes(audio.buffer_read(65536, dtype='int16' if bits == 16 else 'int32'))
            if not raw:
                break
            check_cancel(cancel)
            if sys.byteorder != 'little':
                samples = array('h' if bits == 16 else 'i')
                samples.frombytes(raw)
                samples.byteswap()
                raw = samples.tobytes()
            if bits == 16:
                digest.update(raw)
            else:
                # libsndfile left-aligns 24-bit PCM in each 32-bit sample.
                # Drop its zero low byte; retain the three significant bytes.
                packed = bytearray(len(raw) // 4 * 3)
                packed[0::3], packed[1::3], packed[2::3] = raw[1::4], raw[2::4], raw[3::4]
                digest.update(packed)
    return digest.hexdigest()


def mp3_payload_md5(path: Path, cancel: Event) -> str:
    """Hash the unmodified MPEG payload, excluding leading ID3v2 and trailing ID3v1."""
    digest = hashlib.md5()
    with path.open('rb') as handle:
        head = handle.read(10)
        start = 0
        if head[:3] == b'ID3':
            if len(head) != 10 or any(x & 0x80 for x in head[6:10]):
                raise ValidationError(f'{path.name}: invalid ID3 header.')
            start = 10 + sum(x << shift for x, shift in zip(head[6:10], (21, 14, 7, 0)))
            if head[3] == 4 and head[5] & 0x10:
                start += 10
        end = path.stat().st_size
        if end >= 128:
            handle.seek(end - 128)
            if handle.read(3) == b'TAG':
                end -= 128
        if end <= start:
            raise ValidationError(f'{path.name}: missing MPEG audio payload.')
        handle.seek(start)
        remaining = end - start
        while remaining:
            check_cancel(cancel)
            data = handle.read(min(1024 * 1024, remaining))
            if not data:
                raise ValidationError('Unexpected end of MP3 file.')
            digest.update(data)
            remaining -= len(data)
    return digest.hexdigest()


def tag_file(path: Path, plan: Plan, index: int):
    show = plan.show
    number = f'{index + 1:02}'
    title = plan.titles[index]
    if path.suffix == '.flac':
        audio = FLAC(path)
        # Replace our managed fields; preserve unrelated tags and artwork.
        fields = dict(ARTIST=show.artist, ALBUM=show.album, DATE=show.date,
                      TITLE=title, TRACKNUMBER=number, TOTALTRACKS=str(len(plan.files)),
                      GENRE=show.genre, COMMENT=show.source, SOURCE=show.source,
                      VENUE=show.venue, LOCATION=f'{show.city}, {show.country}')
        for key, value in fields.items():
            audio[key] = value
        audio.save()
    else:
        audio = MP3(path)
        if audio.tags is None:
            audio.add_tags()
        tags = audio.tags
        for key in ('TIT2', 'TALB', 'TPE1', 'TDRC', 'TRCK', 'TCON', 'COMM', 'TDAT', 'TYER'):
            tags.delall(key)
        for cls, text in ((TIT2, title), (TALB, show.album), (TPE1, show.artist),
                          (TDRC, show.date), (TRCK, f'{number}/{len(plan.files)}'), (TCON, show.genre)):
            tags.add(cls(encoding=3, text=[text]))
        tags.add(COMM(encoding=3, lang='eng', desc='', text=[show.source]))
        tags.add(TXXX(encoding=3, desc='SOURCE', text=[show.source]))
        audio.save(v2_version=3)


def export_package(plan: Plan, cancel: Event, log: Callable[[str], None],
                   progress: Callable[[int], None]) -> Path:
    """Stage, verify, checksum, then publish. Source deletion is deliberately separate."""
    if plan.outer.exists():
        raise ValidationError('Output folder already exists.')
    validate_extras(plan)
    estimate = sum(f.stamp[0] if f.kind in ('flac', 'mp3') else
                   f.frames * f.channels * (f.bits // 8) for f in plan.files)
    estimate += sum(extra.stamp[0] for extra in plan.extras if extra.stamp is not None)
    if shutil.disk_usage(plan.outer.parent).free < estimate + 32 * 1024 * 1024:
        raise ValidationError('Not enough free disk space for a safely staged export.')
    stage = Path(tempfile.mkdtemp(prefix='.flac-tagger-', dir=plan.outer.parent))
    try:
        inner = stage / 'package'
        inner.mkdir()
        fingerprints, hashes, sizes = [], [], []
        for index, (source, name) in enumerate(zip(plan.files, plan.names)):
            check_cancel(cancel)
            if stamp(source.path) != source.stamp:
                raise ValidationError(f'{source.path.name} changed after import.')
            target = inner / name
            log(f'Preparing {name}')
            if source.kind == 'pcm':
                with sf.SoundFile(str(source.path)) as inp, sf.SoundFile(
                    str(target), mode='w', samplerate=source.rate, channels=source.channels,
                    format='FLAC', subtype=f'PCM_{source.bits}', compression_level=plan.compression / 8,
                ) as out:
                    while block := inp.buffer_read(65536, dtype='int32'):
                        check_cancel(cancel)
                        out.buffer_write(block, dtype='int32')
            else:
                with source.path.open('rb') as inp, target.open('xb') as out:
                    while data := inp.read(1024 * 1024):
                        check_cancel(cancel)
                        out.write(data)
            tag_file(target, plan, index)
            log(f'Verifying audio and checksums: {name}')
            if source.kind == 'mp3':
                if mp3_payload_md5(source.path, cancel) != mp3_payload_md5(target, cancel):
                    raise ValidationError(f'Audio payload verification failed: {name}')
            else:
                actual = sf.info(str(target))
                if (actual.frames, actual.samplerate, actual.channels, actual.subtype) != (
                    source.frames, source.rate, source.channels, f'PCM_{source.bits}'
                ):
                    raise ValidationError(f'Audio format verification failed: {name}')
                fingerprint = pcm_md5(target, source.bits, cancel)
                if fingerprint != pcm_md5(source.path, source.bits, cancel):
                    raise ValidationError(f'Audio sample verification failed: {name}')
                stored = f'{FLAC(target).info.md5_signature:032x}'
                if stored != fingerprint:
                    raise ValidationError(f'FLAC fingerprint verification failed: {name}')
                fingerprints.append(f'{name}:{fingerprint}\n')
            if stamp(source.path) != source.stamp:
                raise ValidationError(f'{source.path.name} changed during export.')
            hashes.append(f'{file_md5(target, cancel)}  {name}\n')
            sizes.append(target.stat().st_size)
            progress(round((index + 1) * 95 / len(plan.files)))
        (inner / f'{plan.stem}.md5').write_text(''.join(hashes), encoding='utf-8', newline='\n')
        if fingerprints:
            (inner / f'{plan.stem}.ffp').write_text(''.join(fingerprints), encoding='utf-8', newline='\n')
        (inner / f'{plan.stem}.txt').write_text(render_info(plan, sizes), encoding='utf-8', newline='\n')
        copy_extras(plan, inner, cancel, log)
        check_cancel(cancel)
        # Reserve destination atomically so an existing folder can never be replaced.
        plan.outer.mkdir(exist_ok=False)
        try:
            if plan.inner_name:
                inner.rename(plan.folder)
            else:
                # Publish directly into the exclusively reserved outer folder.
                for child in inner.iterdir():
                    child.rename(plan.outer / child.name)
        except Exception:
            shutil.rmtree(plan.outer)
            raise
        progress(100)
        log(f'Complete: {plan.folder}')
        return plan.folder
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def delete_converted_sources(plan: Plan) -> list[str]:
    """Called only after a completed export and explicit confirmation in the GUI."""
    errors = []
    for f in plan.files:
        if f.kind != 'pcm':
            continue
        try:
            if stamp(f.path) != f.stamp:
                raise ValidationError('file changed since import; left untouched')
            f.path.unlink()
        except Exception as exc:
            errors.append(f'{f.path}: {exc}')
    return errors
