"""Standalone audio utilities. No packaging names, show metadata or input deletion."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import struct
import tempfile
from dataclasses import dataclass, asdict
from pathlib import Path, PureWindowsPath

import soundfile as sf
from mutagen import File as MetadataFile
from mutagen.flac import FLAC, CueSheet
from mutagen.id3 import ID3, TIT2, TALB, TPE1, TDRC, TRCK, TCON, COMM, APIC

from tagger_core import (SUPPORTED, ValidationError, Cancelled, check_cancel,
                         file_md5, pcm_md5, inspect_audio, stamp, natural_key)

OPERATIONS = {
    'properties': 'Audio properties', 'check': 'Check audio integrity',
    'md5': 'Create MD5', 'ffp': 'Create FFP', 'verify': 'Verify MD5 / FFP',
    'flac': 'Convert to FLAC', 'wav': 'Convert to WAV', 'aiff': 'Convert to AIFF',
    'recompress': 'Recompress FLAC', 'mp3': 'Create MP3 listening copies',
    'sectors': 'Check CD sector boundaries', 'fix_sectors': 'Fix CD sector boundaries',
    'wav_header': 'Rewrite WAV headers',
}
WRITES = {'md5', 'ffp', 'flac', 'wav', 'aiff', 'recompress', 'mp3', 'fix_sectors', 'wav_header'}


@dataclass
class Result:
    file: str
    status: str
    detail: str
    output: str = ''


def scan_inputs(paths):
    files = set()
    for path in map(Path, paths):
        if path.is_dir():
            for folder, dirs, names in os.walk(path, followlinks=False):
                dirs[:] = [n for n in dirs if not (Path(folder) / n).is_symlink()
                           and not getattr(Path(folder) / n, 'is_junction', lambda: False)()]
                files.update((Path(folder) / n).resolve() for n in names
                             if Path(n).suffix.lower() in SUPPORTED | {'.md5', '.ffp'}
                             and not (Path(folder) / n).is_symlink())
        elif path.is_file():
            files.add(path.resolve())
    return sorted(files, key=natural_key)


def lossless(path):
    info = inspect_audio(path)
    if info.kind == 'mp3':
        raise ValidationError('This operation accepts lossless input only; MP3 is not converted to another format.')
    return info


def decode_count(path, cancel):
    with sf.SoundFile(str(path)) as audio:
        count = 0
        while data := audio.buffer_read(65536, dtype='int32'):
            check_cancel(cancel)
            count += len(data) // (4 * audio.channels)
        if count != audio.frames:
            raise ValidationError('Decoded sample count differs from the header.')
        return count


def integrity(path, cancel):
    info = inspect_audio(path)
    decode_count(path, cancel)
    if info.kind == 'flac':
        expected = FLAC(path).info.md5_signature
        actual = pcm_md5(path, info.bits, cancel)
        if not expected:
            return Result(str(path), 'Unverified', 'Decoded successfully; no embedded FLAC MD5 is available.')
        if actual != f'{expected:032x}':
            raise ValidationError(f'Decoded audio does not match the embedded FLAC fingerprint.\nExpected: {expected:032x}\nCalculated: {actual}')
        return Result(str(path), 'Audio integrity verified', f'Full decode completed: {info.frames:,} sample frames, {info.bits}-bit, {info.rate:,} Hz, {info.channels} channel(s).\nEmbedded FLAC fingerprint: {expected:032x}\nDecoded audio fingerprint: {actual}\nThe fingerprints match.')
    return Result(str(path), 'Readable', 'Full decode completed. No embedded integrity checksum is available for this format.')


def properties(path):
    info = inspect_audio(path)
    metadata = MetadataFile(path, easy=True)
    tags = dict(metadata.tags or {}) if metadata else {}
    values = dict(format=path.suffix[1:].upper(), bits=info.bits, sample_rate=info.rate,
                  channels=info.channels, duration_seconds=round(info.duration, 3),
                  frames=info.frames, size_bytes=info.stamp[0], bitrate=info.bitrate,
                  tags={str(k): str(v) for k, v in tags.items()})
    return Result(str(path), 'Info', json.dumps(values, ensure_ascii=False, indent=2))


def manifest_entries(path):
    data = path.read_bytes()
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = data.decode('cp1252')
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith(('#', ';')):
            continue
        escaped = False
        if path.suffix.lower() == '.ffp':
            match = re.fullmatch(r'(.+):\s*([a-fA-F0-9]{32})\s*', line)
            if match:
                yield line_number, match[1], match[2].lower()
                continue
        else:
            if line.startswith('\\'):
                line, escaped = line[1:], True
            match = re.fullmatch(r'([a-fA-F0-9]{32}) [ *](.+)', line)
            if not match:
                # Tolerate tools that use a single whitespace separator.
                match = re.fullmatch(r'([a-fA-F0-9]{32})\s+\*?(.+)', line)
            if match:
                name = match[2]
                if escaped:
                    name = re.sub(r'\\([\\nr])', lambda m: {'\\': '\\', 'n': '\n', 'r': '\r'}[m[1]], name)
                yield line_number, name, match[1].lower()
                continue
            match = re.fullmatch(r'MD5\s*\((.+)\)\s*=\s*([a-fA-F0-9]{32})\s*', line, re.I)
            if match:
                yield line_number, match[1], match[2].lower()
                continue
        yield line_number, None, None


def manifest_target(manifest, name):
    # Manifests may contain Windows separators even on other platforms.
    normalized = name.replace('\\', '/')
    relative = Path(normalized)
    if relative.is_absolute() or PureWindowsPath(name).drive or '..' in relative.parts:
        raise ValidationError('Manifest entry must stay inside its own folder.')
    base = manifest.parent.resolve()
    target = (base / relative).resolve()
    if not target.is_relative_to(base):
        raise ValidationError('Manifest entry resolves outside its folder.')
    return target


def verify_manifest(path, cancel):
    if path.suffix.lower() not in ('.md5', '.ffp'):
        raise ValidationError('Select an MD5 or FFP manifest.')
    results = []
    for number, name, expected in manifest_entries(path):
        check_cancel(cancel)
        if name is None:
            results.append(Result(f'{path.name}: line {number}', 'Error', 'Unrecognised checksum entry.'))
            continue
        try:
            target = manifest_target(path, name)
            if not target.is_file():
                results.append(Result(str(target), 'File missing', f'Could not find this file.\nManifest: {path}\nExpected location: {target}'))
                continue
            before = stamp(target)
            if path.suffix.lower() == '.ffp':
                info = lossless(target)
                if info.kind != 'flac':
                    raise ValidationError('FFP entries must refer to FLAC files.')
                actual = pcm_md5(target, info.bits, cancel)
            else:
                actual = file_md5(target, cancel)
            if stamp(target) != before:
                raise ValidationError('File changed while being checked.')
            results.append(Result(str(target), 'Checksum verified' if actual == expected else 'Checksum mismatch',
                                  f'{path.suffix[1:].upper()} verification\nManifest: {path}\nFile: {target}\nExpected checksum:   {expected}\nCalculated checksum: {actual}\n'
                                  + ('The checksums match.' if actual == expected else 'The checksums differ. The file may have changed or be damaged.')))
        except Cancelled:
            raise
        except Exception as exc:
            results.append(Result(name, 'Error', str(exc)))
    if not results:
        results.append(Result(str(path), 'Error', 'Manifest contains no checksum entries.'))
    return results


def publish(stage, target):
    """Create, never replace. Same-volume hard links are atomic; copying is fallback."""
    try:
        os.link(stage, target)
    except FileExistsError:
        raise ValidationError(f'Output already exists: {target}') from None
    except OSError:
        created = False
        try:
            with target.open('xb') as out, stage.open('rb') as inp:
                created = True
                shutil.copyfileobj(inp, out, 1024 * 1024)
        except Exception:
            if created:
                target.unlink(missing_ok=True)
            raise


def create_manifest(paths, output, kind, cancel):
    if output.exists():
        raise ValidationError(f'Checksum file already exists: {output}\nEnter a different checksum filename to keep the existing file.')
    lines, details = [], []
    for path in paths:
        check_cancel(cancel)
        try:
            relative = path.resolve().relative_to(output.parent.resolve()).as_posix()
        except ValueError:
            raise ValidationError('Save the checksum beside the input files or in a common parent folder.') from None
        if '\n' in relative or '\r' in relative:
            raise ValidationError('Checksum filenames cannot contain newlines.')
        before = stamp(path)
        if kind == 'ffp':
            info = lossless(path)
            if info.kind != 'flac':
                raise ValidationError('FFP creation accepts FLAC files only.')
            digest = pcm_md5(path, info.bits, cancel)
            lines.append(f'{relative}:{digest}\n')
        else:
            digest = file_md5(path, cancel)
            lines.append(f'{digest}  {relative}\n')
        details.append(f'{relative}\n  {digest}')
        if stamp(path) != before:
            raise ValidationError(f'Input changed while hashing: {path}')
    with tempfile.TemporaryDirectory(prefix='.audio-tools-', dir=output.parent) as temp:
        stage = Path(temp) / output.name
        stage.write_text(''.join(lines), encoding='utf-8', newline='\n')
        check_cancel(cancel)
        publish(stage, output)
    return Result(str(output), f'{kind.upper()} checksum file created',
                  f'Saved {len(paths)} {kind.upper()} checksum(s) beside the input files.\nManifest: {output}\n\n'
                  + '\n'.join(details), str(output))


def copy_tags(source, target):
    """Preserve FLAC comments/pictures and common tags across supported containers."""
    metadata = MetadataFile(source, easy=True)
    tags = dict(metadata.tags or {}) if metadata else {}
    if target.suffix.lower() == '.flac':
        result = FLAC(target)
        if source.suffix.lower() == '.flac':
            original = FLAC(source)
            result.clear()
            result.update(original)
            for picture in original.pictures:
                result.add_picture(picture)
            if original.cuesheet:
                # Recompression preserves samples, so cue offsets remain valid.
                result.cuesheet = original.cuesheet
        else:
            mapping = {'TIT2': 'title', 'TALB': 'album', 'TPE1': 'artist', 'TDRC': 'date', 'TRCK': 'tracknumber', 'TCON': 'genre'}
            for key, value in tags.items():
                name = mapping.get(key, key.lower())
                if ':' not in name and isinstance(value, (str, list)):
                    result[name] = value if isinstance(value, list) else [str(value)]
                elif key in mapping:
                    result[name] = [str(value)]
        result.save()
    else:
        result = MetadataFile(target)
        if result is None:
            return
        if result.tags is None:
            result.add_tags()
        mapping = {'title': TIT2, 'album': TALB, 'artist': TPE1, 'date': TDRC,
                   'tracknumber': TRCK, 'genre': TCON}
        if source.suffix.lower() == '.flac':
            original = FLAC(source)
            for key, cls in mapping.items():
                if key in original:
                    result.tags.add(cls(encoding=3, text=original[key]))
            if 'comment' in original:
                result.tags.add(COMM(encoding=3, lang='eng', desc='', text=original['comment']))
            for pic in original.pictures:
                result.tags.add(APIC(encoding=3, mime=pic.mime, type=pic.type, desc=pic.desc, data=pic.data))
        else:
            original = MetadataFile(source)
            if original and isinstance(original.tags, ID3):
                result.tags.update(original.tags)
        result.save()


def convert(path, target, operation, compression, mp3_quality, cancel):
    info = lossless(path)
    if operation == 'recompress' and info.kind != 'flac':
        raise ValidationError('Recompression accepts FLAC input only.')
    fmt = {'flac': 'FLAC', 'recompress': 'FLAC', 'wav': 'WAV', 'aiff': 'AIFF', 'mp3': 'MP3'}[operation]
    if fmt == 'MP3' and info.rate not in (8000, 11025, 12000, 16000, 22050, 24000, 32000, 44100, 48000):
        raise ValidationError('MP3 cannot preserve this sample rate. Resample externally to 44.1 or 48 kHz first.')
    with sf.SoundFile(str(path)) as inp, sf.SoundFile(str(target), mode='w', samplerate=info.rate,
            channels=info.channels, format=fmt, subtype='MPEG_LAYER_III' if fmt == 'MP3' else f'PCM_{info.bits}',
            compression_level=mp3_quality if fmt == 'MP3' else compression / 8 if fmt == 'FLAC' else None,
            bitrate_mode='VARIABLE' if fmt == 'MP3' else None) as out:
        while block := inp.buffer_read(65536, dtype='int32'):
            check_cancel(cancel)
            out.buffer_write(block, dtype='int32')
    copy_tags(path, target)
    if fmt == 'MP3':
        count = decode_count(target, cancel)
        decoded = sf.info(str(target))
        if decoded.samplerate != info.rate or decoded.channels != info.channels or abs(count - info.frames) > 2304:
            raise ValidationError('MP3 output format or duration verification failed.')
        detail = 'MP3 listening copy; lossy VBR encoding. Sample rate and channels preserved.'
    else:
        decoded = sf.info(str(target))
        if (decoded.frames, decoded.samplerate, decoded.channels, decoded.subtype) != (info.frames, info.rate, info.channels, f'PCM_{info.bits}'):
            raise ValidationError('Output format verification failed.')
        if pcm_md5(path, info.bits, cancel) != pcm_md5(target, info.bits, cancel):
            raise ValidationError('Output samples differ from the original.')
        if fmt == 'FLAC':
            integrity(target, cancel)
        detail = f'Verified identical {info.bits}-bit audio samples; tags copied where supported.'
    if stamp(path) != info.stamp:
        raise ValidationError('Input changed during conversion.')
    return detail


def cd_info(path):
    info = lossless(path)
    if (info.bits, info.rate, info.channels) != (16, 44100, 2):
        raise ValidationError('CD sector tools require 16-bit, 44.1 kHz stereo lossless audio.')
    return info


def check_sectors(path):
    info = cd_info(path)
    remainder = info.frames % 588
    return Result(str(path), 'Aligned' if remainder == 0 else 'Not aligned',
                  f'{info.frames} sample frames; remainder {remainder} of 588 frames per CD sector.')


def fix_sectors(paths, targets, temp, pad_final, cancel, log):
    infos = [cd_info(path) for path in paths]
    boundaries, cumulative = [0], 0
    for info in infos[:-1]:
        cumulative += info.frames
        boundaries.append(cumulative // 588 * 588)
    total = sum(i.frames for i in infos)
    boundaries.append(total)
    if any(b <= a for a, b in zip(boundaries, boundaries[1:])):
        raise ValidationError('Tracks are too short to shift boundaries safely.')
    padding = (-total) % 588 if pad_final else 0
    digest_in, digest_out = hashlib.md5(), hashlib.md5()

    def input_blocks():
        for info in infos:
            with sf.SoundFile(str(info.path)) as inp:
                while block := inp.buffer_read(65536, dtype='int16'):
                    check_cancel(cancel)
                    raw = bytes(block)
                    digest_in.update(raw)
                    yield raw
    stream = iter(input_blocks())
    pending = b''
    stages = []
    try:
        for index, (path, target) in enumerate(zip(paths, targets)):
            log(f'Adjusting CD track boundary: {path.name}')
            stage = temp / target.name
            frames = boundaries[index + 1] - boundaries[index]
            fmt = 'FLAC' if path.suffix.lower() == '.flac' else 'AIFF' if path.suffix.lower() in ('.aif', '.aiff') else 'WAV'
            with sf.SoundFile(str(stage), mode='w', samplerate=44100, channels=2, format=fmt, subtype='PCM_16') as out:
                remaining = frames * 4
                while remaining:
                    check_cancel(cancel)
                    if not pending:
                        pending = next(stream)
                    chunk, pending = pending[:remaining], pending[remaining:]
                    out.buffer_write(chunk, dtype='int16')
                    remaining -= len(chunk)
                if index == len(paths) - 1 and padding:
                    out.buffer_write(b'\0' * (padding * 4), dtype='int16')
            copy_tags(path, stage)
            # Existing embedded cue sheets describe old track boundaries.
            if fmt == 'FLAC':
                tags = FLAC(stage)
                tags.metadata_blocks = [block for block in tags.metadata_blocks if not isinstance(block, CueSheet)]
                tags.cuesheet = None
                if 'cuesheet' in tags:
                    del tags['cuesheet']
                tags.save()
            with sf.SoundFile(str(stage)) as check:
                if check.frames != frames + (padding if index == len(paths) - 1 else 0):
                    raise ValidationError('Sector-fix length verification failed.')
                remaining = frames
                while remaining:
                    check_cancel(cancel)
                    chunk = check.buffer_read(min(remaining, 65536), dtype='int16')
                    if not chunk:
                        raise ValidationError('Unexpected end of adjusted track.')
                    digest_out.update(chunk)
                    remaining -= len(chunk) // 4
            stages.append(stage)
        # Complete the generator so all input handles close before publishing.
        if pending or next(stream, None) is not None or digest_in.digest() != digest_out.digest():
            raise ValidationError('Joined audio verification failed after shifting track boundaries.')
    finally:
        stream.close()
    if any(stamp(i.path) != i.stamp for i in infos):
        raise ValidationError('An input changed while adjusting boundaries.')
    check_cancel(cancel)
    published = []
    try:
        for stage, target in zip(stages, targets):
            publish(stage, target)
            published.append(target)
    except Exception:
        for target in published:
            target.unlink(missing_ok=True)
        raise
    return [Result(str(path), 'Created', f'CD boundaries shifted backward; combined original samples verified. Final padding: {padding} frames. Embedded FLAC cue sheets removed where present.', str(target))
            for path, target in zip(paths, targets)]


def rewrite_wav(path, target, cancel):
    """Canonical PCM fmt header, retaining every non-fmt RIFF chunk byte-for-byte."""
    initial = stamp(path)
    size = initial[0]
    if path.suffix.lower() != '.wav':
        raise ValidationError('Select a WAV file.')
    chunks = []
    with path.open('rb') as inp:
        header = inp.read(12)
        if header[:4] != b'RIFF' or header[8:12] != b'WAVE':
            raise ValidationError('Only little-endian RIFF WAV is supported; RF64/RIFX require other tools.')
        position = 12
        while position < size:
            inp.seek(position)
            raw = inp.read(8)
            if len(raw) != 8:
                raise ValidationError('Truncated chunk header; cannot safely infer missing bytes.')
            kind, length = struct.unpack('<4sI', raw)
            end = position + 8 + length + (length % 2)
            if end > size:
                raise ValidationError('A chunk extends past the file. This is not a safely repairable header.')
            chunks.append((kind, position, length, end - position))
            position = end
        fmts = [c for c in chunks if c[0] == b'fmt ']
        audio = [c for c in chunks if c[0] == b'data']
        if len(fmts) != 1 or len(audio) != 1:
            raise ValidationError('Expected exactly one fmt and one data chunk.')
        inp.seek(fmts[0][1] + 8)
        fmt = inp.read(min(fmts[0][2], 40))
        if len(fmt) < 16:
            raise ValidationError('Incomplete WAV format header.')
        encoding, channels, rate, byte_rate, align, bits = struct.unpack('<HHIIHH', fmt[:16])
        if encoding == 65534:
            if len(fmt) < 40 or fmt[24:40] != bytes.fromhex('0100000000001000800000aa00389b71') or struct.unpack('<H', fmt[18:20])[0] != bits:
                raise ValidationError('Unsupported extensible WAV format.')
            mask = struct.unpack('<I', fmt[20:24])[0]
            if mask not in (0, 4 if channels == 1 else 3):
                raise ValidationError('Nonstandard channel layout cannot be represented by a canonical header.')
        elif encoding != 1:
            raise ValidationError('Only integer PCM WAV is supported.')
        if channels not in (1, 2) or bits not in (16, 24) or rate <= 0:
            raise ValidationError('Only 16/24-bit mono/stereo PCM is supported.')
        block = channels * bits // 8
        if audio[0][2] % block:
            raise ValidationError('Audio data is not aligned to complete samples.')
        canonical = struct.pack('<HHIIHH', 1, channels, rate, rate * block, block, bits)
        new_size = 12 + sum(24 if c[0] == b'fmt ' else c[3] for c in chunks)
        if new_size - 8 > 0xffffffff:
            raise ValidationError('File is too large for a canonical RIFF WAV header.')
        data_hash = hashlib.md5()
        with target.open('xb') as out:
            out.write(b'RIFF' + struct.pack('<I', new_size - 8) + b'WAVE')
            for kind, offset, length, whole in chunks:
                if kind == b'fmt ':
                    out.write(b'fmt ' + struct.pack('<I', 16) + canonical)
                    continue
                inp.seek(offset)
                remaining = whole
                while remaining:
                    check_cancel(cancel)
                    chunk = inp.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValidationError('Input ended unexpectedly.')
                    out.write(chunk)
                    remaining -= len(chunk)
                if kind == b'data':
                    inp.seek(offset + 8)
                    remaining = length
                    while remaining:
                        check_cancel(cancel)
                        chunk = inp.read(min(1024 * 1024, remaining))
                        data_hash.update(chunk)
                        remaining -= len(chunk)
    if pcm_md5(target, bits, cancel) != data_hash.hexdigest() or stamp(path) != initial:
        raise ValidationError('WAV audio verification failed.')
    return 'Canonical PCM header written; original audio and all extra RIFF chunks retained.'


def output_targets(paths, destination, operation):
    extension = {'flac': '.flac', 'recompress': '.flac', 'wav': '.wav', 'aiff': '.aiff', 'mp3': '.mp3'}
    targets = [destination / (p.stem + extension[operation] if operation in extension else p.name) for p in paths]
    seen = set()
    for target in targets:
        if target.name.casefold() in seen:
            raise ValidationError(f'Two inputs would produce {target.name}. Run them separately.')
        seen.add(target.name.casefold())
        if target.exists():
            raise ValidationError(f'Output already exists: {target}. Choose another output folder.')
    return targets


def run_tools(operation, paths, destination, cancel, log, progress, *, compression=5,
              mp3_quality=.2, manifest_name='checksums', pad_final=False):
    paths = [Path(p).resolve() for p in paths]
    if operation not in OPERATIONS or not paths:
        raise ValidationError('Choose an operation and add files first.')
    if len(paths) != len(set(paths)):
        raise ValidationError('The input list contains duplicate paths.')
    # A dropped folder often contains both audio and existing manifests.
    # Filter before output collision checks, and make every omission visible.
    allowed = {'.md5', '.ffp'} if operation == 'verify' else SUPPORTED
    skipped = []
    if operation != 'md5':
        skipped = [Result(str(p), 'Skipped', 'This file type is not used by the selected tool.')
                   for p in paths if p.suffix.lower() not in allowed]
        paths = [p for p in paths if p.suffix.lower() in allowed]
        if not paths:
            return skipped
    if not 0 <= compression <= 8 or not 0 <= mp3_quality <= 1:
        raise ValidationError('Invalid compression or MP3 quality setting.')
    if operation in ('md5', 'ffp'):
        if not re.fullmatch(r'[\w .-]+', manifest_name) or manifest_name in ('.', '..'):
            raise ValidationError('Enter a plain checksum filename, without a path.')
        name = manifest_name if manifest_name.lower().endswith('.' + operation) else manifest_name + '.' + operation
        # Portable checksum files belong beside the files they describe. Grouping
        # by input folder works across drives and never needs an H:-to-C: path.
        groups = {}
        for path in paths:
            groups.setdefault(path.parent, []).append(path)
        results = skipped
        for index, (folder, inputs) in enumerate(groups.items()):
            output = folder / name
            try:
                log(f'Creating {operation.upper()} checksum file: {output}')
                results.append(create_manifest(inputs, output, operation, cancel))
            except Cancelled:
                results.append(Result(str(output), 'Cancelled', 'Stopped. Completed checksum files are retained.'))
                break
            except PermissionError:
                results.append(Result(str(output), 'Error', f'Cannot write to {folder}. Check drive permissions or copy the input files to a writable folder.'))
            except Exception as exc:
                results.append(Result(str(output), 'Error', str(exc)))
            progress(round((index + 1) * 100 / len(groups)))
        return results
    destination = Path(destination).expanduser().resolve()
    if operation in WRITES and not destination.is_dir():
        raise ValidationError('Choose an existing output directory.')
    if operation in WRITES:
        targets = output_targets(paths, destination, operation)
    else:
        targets = [None] * len(paths)
    if operation == 'fix_sectors':
        with tempfile.TemporaryDirectory(prefix='.audio-tools-', dir=destination) as temp:
            result = fix_sectors(paths, targets, Path(temp), pad_final, cancel, log)
        progress(100)
        return skipped + result
    results = skipped
    for index, (path, target) in enumerate(zip(paths, targets)):
        try:
            check_cancel(cancel)
            log(f'{OPERATIONS[operation]}: {path.name}')
            before = stamp(path)
            if operation == 'verify':
                rows = verify_manifest(path, cancel)
            elif operation == 'check':
                rows = [integrity(path, cancel)]
            elif operation == 'properties':
                rows = [properties(path)]
            elif operation == 'sectors':
                rows = [check_sectors(path)]
            else:
                with tempfile.TemporaryDirectory(prefix='.audio-tools-', dir=destination) as temp:
                    stage = Path(temp) / target.name
                    if operation == 'wav_header':
                        detail = rewrite_wav(path, stage, cancel)
                    else:
                        detail = convert(path, stage, operation, compression, mp3_quality, cancel)
                    check_cancel(cancel)
                    publish(stage, target)
                    rows = [Result(str(path), 'Created', detail, str(target))]
            if stamp(path) != before:
                raise ValidationError('Input changed during this operation.')
            results.extend(rows)
        except Cancelled:
            results.append(Result(str(path), 'Cancelled', 'Stopped. Completed outputs are retained; unfinished temporary files are removed.'))
            break
        except Exception as exc:
            results.append(Result(str(path), 'Error', str(exc)))
        progress(round((index + 1) * 100 / len(paths)))
    return results


def save_report(results, path):
    path = Path(path)
    if path.suffix.lower() == '.json':
        path.write_text(json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2), encoding='utf-8')
    else:
        path.write_text('\n\n'.join(f'{r.status}: {r.file}\n{r.detail}' + (f'\nOutput: {r.output}' if r.output else '') for r in results) + '\n', encoding='utf-8')
