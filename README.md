# Live Audio Tagger

Prepare live recordings for sharing on sites such as DIME and Internet Archive. Live Audio Tagger adds tags, applies consistent filenames, writes a recording information sheet, and creates verified checksums. Its separate Tools tab handles conversion, inspection and checksum jobs without creating a package.

Your recording should already be edited and split into tracks. The app does not apply EQ, change volume, split tracks or upload recordings.

## Download and run on Windows

1. Open [Releases](https://github.com/gambra/live-audio-tagger/releases/latest).
2. Download **LiveAudioTagger-Windows-x64.zip** from the release assets. The automatically generated “Source code” downloads are for the Python version.
3. Right-click the ZIP and choose **Extract All**.
4. Keep the extracted files together in a writable folder, then open **LiveAudioTagger.exe**.

The portable release supports 64-bit Windows 10 and 11. Python and the audio libraries are included; there is no installer or separate converter to install. The EXE is unsigned, so Windows may show an unrecognised-publisher warning. Download only from a source you trust.

The ZIP contains four files: the application, `template_example.txt`, `README.txt`, and third-party licence notices. The template stays outside the EXE so you can edit it in a text editor.

Read the [full user guide](DISTRIBUTION_README.txt) for explanations of every function and setting.

## Make a recording package

1. In **Settings**, select your default export destination.
2. In **Main**, drop a recording folder or add its audio files. Each new selection starts a fresh package.
3. Check the file order and recording details. Existing information text files are scanned for suggestions; review the guesses. You can also choose to copy artwork and other extras with their names intact.
4. Enter one track title per line. Paste and edit a setlist, generate generic titles, or look up the show on Setlist.fm using your own API key.
5. Choose **Preview filenames and info text** to review the result, then **Tag Files**.

The app creates a new folder and verifies the audio and checksums before finishing. Existing output folders are never overwritten. Original files are kept by default. An optional setting allows deletion of converted WAV/AIFF originals after a successful export and a final confirmation.

### Formats and audio quality

- **FLAC, WAV and AIFF:** 16-bit or 24-bit integer audio, mono or stereo. WAV/AIFF become FLAC; existing FLAC files are tagged without re-encoding in Main.
- **MP3:** tagged and copied without re-encoding, in separate MP3 packages.
- Tracks in a lossless package must share sample rate and bit depth. The app preserves sample rate, bit depth and channel count.
- FLAC packages include both **FFP** fingerprints of the decoded audio and **MD5** hashes of the final tagged files. MP3 packages include MD5.
- The generated information text remains editable; audio checksums do not cover that text file.

### File and folder names

Audio filenames always use the artist name reduced to lowercase letters and digits, the show date, and a track number. For example:

```text
Example Band - 2026-09-25 - The Hall, Dublin, Ireland (AUD)/
  exampleband2026-09-25.flac24/
    exampleband2026-09-25t01.flac
    exampleband2026-09-25t02.flac
    exampleband2026-09-25.ffp
    exampleband2026-09-25.md5
    exampleband2026-09-25.txt
```

In **Settings**, customise the outer folder with placeholders such as `{{artist}} - {{date}} - {{title}} ({{source}})` or `{{date}} - {{artist}} - {{venue}}`. The strict Etree subfolder is optional; track filenames stay strict either way.

Characters that cannot appear in filenames are sanitised only in generated paths. Original punctuation stays in the fields, tags and information text. **File Title** supplies the album tag; **Source** and **Technical notes** cover the recording source and lineage.

## Standalone Tools

Drop files or folders into **Tools** and choose an action. If files are already listed, choose whether to replace the list or add to it. Review the selection and options before running.

| Task | Available operations |
| --- | --- |
| Checksums | Create MD5, create FFP, verify MD5/FFP manifests |
| Conversion | Lossless to FLAC, WAV or AIFF; recompress FLAC; lossless to MP3 listening copies |
| Inspection | Show properties and tags; test audio decoding and FLAC fingerprints; check CD sector alignment |
| Repair | Fix CD sector boundaries; repair safely readable PCM WAV headers |

Checksum creation writes beside the input files, including on external drives. Conversion and repair operations create copies in the selected destination. The report identifies verified checksums, mismatches, missing files and errors.

MP3-to-lossless conversion is not supported. CD sector tools apply only to 16-bit, 44.1 kHz stereo audio. MP3 conversion does not resample; inputs above 48 kHz need external resampling first. See the [user guide](DISTRIBUTION_README.txt) for repair limitations and ordering requirements.

## Settings, templates and logs

- Settings persist, including folder preferences, export destination and the optional Setlist.fm API key.
- Edit `template_example.txt` in a text editor. The app reads it again for each preview/export. [GETTING_STARTED.md](GETTING_STARTED.md) lists the placeholders.
- Track titles and recording details remain editable and are cleared for a new package.
- The interface follows the Windows light/dark preference.
- **View log** shows current activity. **Open log file** opens `LiveAudioTagger.log`, which retains timestamped activity across sessions.

`settings.ini` stores local paths and the Setlist.fm API key in readable text. Logs can contain recording details and paths. Keep these files private; share the original release ZIP instead of your used application folder.

## Run the Python version

Use Python 3.11 or newer. Download the source or clone this repository, then run these commands from the project folder on Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe flac_tagger.py
```

After setup, you can also double-click `run_tagger.bat`. Keep the other Python modules, `assets/` and `template_example.txt` alongside the main script.

On macOS/Linux, use `.venv/bin/python` instead. The source uses cross-platform libraries, but the packaged release is tested on Windows. SoundFile wheels include libsndfile on supported platforms; systems without a suitable wheel may need libsndfile installed separately. No separate FLAC or FFmpeg executable is required.

## Development and Windows builds

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe build_windows.py
```

Build on Windows. The build creates `distribution/LiveAudioTagger-Windows-x64/` with the four portable release files. Existing release folders are not overwritten; use `--output-name LiveAudioTagger-Next` to create another build. Personal settings and logs are excluded.

See [GETTING_STARTED.md](GETTING_STARTED.md) for implementation details, exact naming rules and build notes.

## Scope

There is no audio editing, resampling, bit-depth conversion, 32-bit or multichannel support. SHN, APE, MP2, MKW, torrent tools, CFP/SFV/ST5 checksums, lossy-source detection, Explorer integration and automatic updates are not included.

