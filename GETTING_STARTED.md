# Running Live Audio Tagger

For the latest development changes, run `run_tagger.bat` or the Python command below.
The portable release is `distribution/LiveAudioTagger-Windows-x64.zip`.
Extract it and open `LiveAudioTagger.exe`; no Python installation is needed.
It includes the selected Option A microphone icon and the latest interface changes,
with just four files in the release folder. Executables are rebuilt only when requested.
Create a virtual environment and install the dependencies to run from source.

Requires Python 3.11 or newer. From this folder on Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe flac_tagger.py
```

After setup, you can also double-click `run_tagger.bat`.

On macOS/Linux, use `.venv/bin/python` instead of `.venv\Scripts\python.exe`.
The SoundFile wheels supply libsndfile on supported platforms; a system libsndfile
installation may be needed where a wheel is unavailable. No separate FLAC or FFmpeg
executable is required by the application.

## Workflow

The interface has three tabs: **Main**, **Tools** and **Settings**. File management is at
the top of the main tab, with recording details and editable track titles underneath.
Preview and log windows are available from the buttons at the bottom.

1. Add files or drop files/a folder into the audio list (folders are scanned recursively). Imports sort naturally.
   Each new selection/drop starts a fresh package: previous files, details, track titles,
   extras and preview are cleared. Saved Settings remain unchanged. Select all files/folders
   for one package together. Cancelling the file picker does not clear the current package.
   Review the order; move tracks up/down if necessary. Moving/removing files moves/removes
   their corresponding title lines as well.
2. Enter recording details. Filenames automatically use Artist in lowercase with
   all characters except `a-z` and digits removed: `Nine Inch Nails` becomes
   `nineinchnails`, and `Sunn O)))` becomes `sunno`. There is no separate artist code.
3. Enter one track title per line, or import a Setlist.fm result using your own API key.
   Titles remain editable. Paste titles without numbering; numbering is generated.
4. In Settings, select the text template (defaults to `template_example.txt`). Edit
   it manually in your preferred text editor. The app reads it fresh for every preview
   and export, so external edits take effect without restarting. There is no template editor in the app.
5. Set an existing default export directory in Settings, preview exact paths, and create the package.
   The preview's file-size total is an estimate; the exported text uses actual sizes.

The README gives an overview; this document describes the implemented behaviour in detail.

## Importing a recording folder

Dropping a folder or using **Add folder** scans existing `.txt` files for recording
details. This is a local, best-effort parser: it recognises common labels, loose
Artist/Venue/City/Date headers, several date formats, and numbered tracklists.
Review the guesses in the normal editable fields. Each import starts with cleared
recording details; the untouched default `AUD` may be replaced by a guessed Source.
Long source/equipment chains go into Technical notes. The richest info file takes
priority, with other text files filling gaps. Ambiguous numeric dates use day-first
order when both interpretations are valid.

Tracklist guesses fill generic/blank titles only when their count matches the audio
files in that folder; otherwise a message in **View log** explains the mismatch.
UTF-8, UTF-16 with a byte-order mark, and legacy Windows text encodings are supported.
Text files larger than 2 MiB are skipped and logged.

The app also asks whether to copy extra files such as artwork. Accepted extras go
inside the new audio folder, keeping their original names and relative subfolder
paths; empty folders are preserved too. The scan excludes FLAC, MP3, FFP, MD5 and
TXT at every folder level, and excludes WAV/AIFF because those are processed as
audio inputs. Links/junctions are not followed. **Extra files…** lets you remove
accepted extras from the current selection; **Clear** resets it. Extras are not
remembered between runs.

The output preview lists selected extras. Copying and verification happen before
the package is published; a changed/missing extra or a filename collision stops
export rather than silently renaming or overwriting files. Extra files are copied
only, never deleted by the original-audio deletion option. Audio checksum manifests
continue to cover audio files only.

## Folder patterns and exact audio naming

Settings has an **Outer folder pattern** field and a **Create an Etree named
subfolder** checkbox. Both are saved between runs. The default pattern preserves
the original layout, and the checkbox starts checked. **Restore default** resets
the outer pattern. Main's Preview shows the complete resulting path.

Use the same placeholders as the info template. `{{title}}` and `{{album}}` both
mean the **File Title** field on Main (also used for the album tag). Examples:

```text
{{artist}} - {{date}} - {{title}} ({{source}})
{{date}} - {{artist}} - {{venue}}
```

The pattern must produce one valid folder name, not a path. Unknown placeholders,
empty names, reserved names and invalid literal filename characters are reported
before export. Invalid characters in substituted text become hyphens; Artist keeps
the previous rule of removing invalid filename characters. Tags/info retain their
text. MP3 packages still receive the automatic ` (MP3)` suffix.

With the checkbox checked, the inner folder always uses strict Etree naming. With
it unchecked, audio, MD5/FFP, info text and extras go directly in the named outer
folder. Audio and checksum filenames remain strict in either case, and existing
outer folders are never overwritten. For folder patterns using `total_size`, the
value is the input-size estimate fixed when the export plan is prepared; info text
still uses the final audio sizes.

For artist `Example Band`, date `2026-09-25`, venue `The Hall`, city
`Dublin`, country `Ireland`, Source `AUD`, and 24-bit audio, the default is:

```text
Example Band - 2026-09-25 - The Hall, Dublin, Ireland (AUD)/
  exampleband2026-09-25.flac24/
    exampleband2026-09-25t01.flac
    exampleband2026-09-25t02.flac
    exampleband2026-09-25.md5
    exampleband2026-09-25.ffp
    exampleband2026-09-25.txt
```

16-bit uses `.flac16`. MP3 uses `.mp3` for the inner folder and track extension,
with ` (MP3)` appended to the outer folder name. Track numbering has a minimum of
two digits (track 100 is `t100`). The normalized artist and date are concatenated without a
separator. There are no disc numbers or automatic artist abbreviations.

**Source** is a single field used in the folder name, tags and info text, such as
`AUD` or `SBD`. Filename-unsafe Source characters (`<>:"/\\|?*` and control
characters) are replaced with `-` only in generated folder names.
For example, `AUD/SBD: Mic > DAT?` becomes `AUD-SBD- Mic - DAT-` in the folder
name; the original text remains in the editable field, tags and info text.
Put equipment and transfer/lineage details in **Technical notes**,
which can contain characters such as `>`. Artist tags and info text retain the original
artist name; the outer folder retains it too except for characters forbidden in Windows
filenames. Other metadata fields likewise retain their text; unsafe characters are
replaced only when substituted into folder names. Existing output folders are refused.

## Saved settings

Settings automatically persist the Setlist.fm API key, default export destination,
template path, outer folder pattern, Etree subfolder checkbox, compression level
and original-deletion preference. They are stored in
`settings.ini` beside the script (including the API key as plain text); this file is
excluded from version control. Recording details, track titles and input files are not remembered.

## Audio and integrity

- WAV/AIFF: only 16/24-bit integer PCM, mono/stereo, converted losslessly to FLAC.
- FLAC: 16/24-bit mono/stereo, copied and tagged without re-encoding.
- MP3: copied and tagged without re-encoding; never put in a lossless package.
- All tracks in a package must share sample rate and bit depth. WAV/AIFF/FLAC inputs
  may be combined when they produce the same output format. Mono and stereo tracks
  may coexist; neither is changed.
- No resampling, bit-depth changes, gain adjustment, EQ, track splitting or audio editing.
- Each lossless output is decoded and checked against the original PCM samples.
  Its stored FLAC fingerprint is independently checked against decoded PCM.
- `.ffp` contains FLAC PCM MD5 fingerprints (`filename:hash`). `.md5` contains
  whole-file MD5 hashes (`hash  filename`) after tagging. Both are mandatory for FLAC.
  MP3 has mandatory MD5 only: an FFP is not defined for MP3.
- MP3 verification compares its MPEG payload before/after tagging, excluding ID3 tags;
  it does not certify that the original MP3 is free of decoding errors.
- Checksums cover audio files, not the info text, so the generated `.txt` remains
  freely editable after export. Editing audio tags afterward requires new file MD5s.
- Files are built in a temporary folder, verified, then published. Failed/cancelled jobs
  remove their staging folder and preserve originals. A power failure can leave a
  `.flac-tagger-*` staging folder, which can be removed once the app is closed.
- The optional deletion setting offers a final confirmation listing original WAV/AIFF
  paths after successful export. It permanently deletes only those converted sources,
  never input FLAC/MP3. The default is off.

FLAC uses standard Vorbis-comment `ALBUM`; MP3 uses ID3 `TALB`. Both contain the
Album title field. Existing unrelated tags/artwork are preserved. Genre has standard
suggestions and accepts typed text. No input history or projects are saved.

Setlist.fm needs internet access and a user-supplied API key; the rest works offline.
The lookup previews results and links to their source. Review current API terms for
your intended use. The initial search displays the first page of matching results.
If a matching show has venue information but no songs, accepting it imports the
available venue, city and country and generates `YYYY-MM-DD T01` titles for all
loaded tracks. These titles remain editable.

## Standalone Tools

Tools has its own file list, output folder and results. It does not change the Main
package, apply its naming rules, create an info text, or use its deletion setting.
Drop files/folders or use Add files/folder. A grouped action popup lets you choose
the operation. If Tools already has files, choose **Clear the current list and use
these files** or **Add these files to the current list**; duplicates are skipped.
Cancel leaves the previous files, operation and results unchanged. Empty imports
also preserve the existing list. Nothing runs until you press the Run button.
Folder scans include supported audio
and MD5/FFP manifests; Add files with the All files filter also accepts other files
for MD5 hashing. Clear list starts a new list.
Unrelated file types are reported as Skipped for the selected operation.

- **Audio properties** displays technical details and tags.
- **Check audio integrity** decodes the entire file and compares FLAC audio against
  its embedded fingerprint. Missing FLAC fingerprints report Unverified; WAV/AIFF/MP3
  report Readable when decoding succeeds, which is not proof of an undamaged original.
- **Create MD5 / Create FFP / Verify MD5 / FFP** operate independently of packaging.
  MD5 hashes whole files; FFP hashes decoded FLAC samples. New manifests are saved
  **beside the input files**, one per input folder, independent of the audio export
  directory. This works across drives and keeps the filenames portable. The selected
  checksum filename is used in each folder; existing manifests are never overwritten.
  The input folders must be writable. Verification shows **Checksum verified**,
  **Checksum mismatch**, **File missing** or **Error**, with expected/calculated hashes
  and full file locations. Paths outside the manifest folder are refused.
- **Convert to FLAC / WAV / AIFF**, **Recompress FLAC** and **Create MP3 listening
  copies** accept supported lossless input only. Lossless conversion verifies identical
  samples. FLAC recompression retains comments and artwork. Cross-format conversions
  copy supported tags. MP3 uses VBR; quality and FLAC compression controls appear as
  appropriate. Sample rates are preserved, so MP3 inputs above 48 kHz need external
  resampling first. MP3 is never converted to WAV, AIFF, FLAC or another MP3.
- **Check / Fix CD sector boundaries** require 16-bit, 44.1 kHz stereo. Arrange tracks
  in the intended playback order with Move up/down. Repair shifts internal boundaries
  backward to 588-frame sectors and verifies that joined audio is unchanged. Final-track
  silence padding is optional and off by default; without it the final track may remain
  unaligned. Existing embedded FLAC cue sheets are removed from repaired outputs because
  their offsets can become stale. These repairs run only when explicitly selected.
- **Rewrite WAV headers** writes canonical PCM headers, corrects safely inferable size
  and format fields, preserves audio and extra RIFF chunks, and refuses truncated or
  ambiguous files. RF64/RIFX are not supported by this repair tool.
Audio conversion and repair tools need an existing output folder. Audio basenames are retained (with the
new extension when converting); existing files and duplicate output names are refused.
Originals are never deleted or modified. Cancel stops work and removes unfinished
temporary files; completed outputs remain. The large report area shows the full job
report automatically; select a result row for one file's details, or Show full report
to return to the complete report. Save report exports TXT or JSON. The file list is
at the bottom and the dividing bars can be dragged to resize the sections.
SHN, APE, MP2, MKW, legacy checksums, torrent tools, Explorer integration and update
checking are not included. Lossy-source analysis has been removed for now.
No additional runtime dependency is needed for Tools.

## Template variables

`artist`, `prefix`, `date`, `venue`, `city`, `country`, `title`, `album`, `source`,
`source_label`, `genre`, `taper`, `taping_location`, `show_notes`, `tech_notes`,
`format`, `bit_depth`, `sample_rate`, `channels`, `bitrate`, `total_duration`,
`total_size`, `total_tracks`, `tracklist`, `tracks`.

`prefix` is the automatically normalized artist. `source_label` remains an alias of
`source` for compatibility with existing templates; it is not a separate input field.

`tracklist` contains formatted `01 - Title [MM:SS]` strings. `tracks` contains objects
with `number`, `title`, `duration`, and `filename` for more custom layouts. `channels`
is the first track's channel count. Sizes are audio-only MiB. Durations over an hour
use H:MM:SS. Unknown variables fail validation rather than silently creating blank text.
Jinja templates support loops, conditionals and filters. Use trusted templates only.

## Development checks

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

`tagger_core.py` owns validation, naming, conversion, tagging, verification and export.
`flac_tagger.py` owns the PySide6 interface and Setlist.fm lookup. `audio_tools.py`
implements standalone operations and `tools_tab.py` provides their interface. No packaging or
installer build is needed to change either file.

## Building a Windows distribution

On Windows, install `requirements-build.txt` in the virtual environment and run
`python build_windows.py` with that environment's Python. The result is a portable
`distribution/LiveAudioTagger-Windows-x64` folder containing just the EXE, editable template,
README and consolidated dependency notices. There are no source/test files or
separate runtime folders. Existing release folders are not overwritten; use
`python build_windows.py --output-name LiveAudioTagger-Next` for another build. Personal
`settings.ini` is never included by the build. `FLACTagger-Compact.spec` excludes
NumPy and unused Qt plugins/libraries. Lossless audio conversion and fingerprinting
use libsndfile's buffer API with standard Python byte operations instead of NumPy.

## Appearance and persistent activity log

The header shows only the app name. The window and executable use the generated
block-art microphone artwork in `assets/`.
The PNG is 256 × 256 with transparency; the ICO contains multiple Windows icon
sizes and is embedded in the EXE. The layout uses Qt's Fusion style with the
system palette, so the Windows light/dark preference determines the appearance.

**Tag Files** on the right of Main performs the same verified export as before.
**View log** includes an **Open log file** button. Messages, errors and Tools
results are appended with timestamps to `LiveAudioTagger.log` beside the script
or executable. Clearing Main's current package does not erase that file. Log
write failures appear in View log without stopping audio work. The log may contain
recording details and local paths; do not include it with shared releases. Close
the app before archiving/deleting the log if you want a fresh history.
