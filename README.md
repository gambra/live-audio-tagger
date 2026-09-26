# Live Audio Tagger

Live Audio Tagger is a desktop app for preparing live recordings for sharing on sites such as DIME and Internet Archive. It brings tagging, file naming, recording information and checksums into one workflow, with a separate set of tools for everyday audio file tasks.

Start with a recording that has already been edited and split into tracks. The app helps organise and verify the finished files; it does not edit the sound or upload recordings for you.

[Download for Windows](https://github.com/gambra/live-audio-tagger/releases) · [Full user guide](docs/USER_GUIDE.md)

## What it does

- **Tags your tracks** with artist, show details, album title, track titles and other recording information.
- **Names files consistently** using strict Etree-style filenames, with a customisable outer folder and an optional Etree subfolder.
- **Creates a recording information sheet** from an editable text template.
- **Creates and verifies checksums:** both FFP and MD5 for FLAC packages, and MD5 for MP3 packages.
- **Helps fill in show details** from existing information files or an optional Setlist.fm lookup. Track titles remain freely editable.
- **Copies selected extras**, such as artwork, into the finished package without renaming them.
- **Provides standalone audio tools** for conversion, checksum verification, file inspection and selected repairs.

The app supports **16-bit and 24-bit mono or stereo FLAC, WAV and AIFF**, plus **separate MP3 packages**. WAV and AIFF recordings are converted losslessly to FLAC when packaging. Existing FLAC and MP3 tracks are tagged without re-encoding in the main workflow.

## Get started

1. Download **LiveAudioTagger-Windows-x64.zip** from [Releases](https://github.com/gambra/live-audio-tagger/releases).
2. Right-click the ZIP and choose **Extract All**.
3. Keep the extracted files together in a writable folder, then open **LiveAudioTagger.exe**.

The portable version runs on **64-bit Windows 10 and 11**. There is nothing else to install: Python and the audio libraries are included. The app is currently unsigned, so Windows may show an unrecognised-publisher warning.

## Prepare a recording

1. In **Settings**, choose your default export destination.
2. In **Main**, drop a recording folder or add its audio files. Check the track order and any automatically filled details.
3. Enter the artist, date, venue, location, File Title and Source. **File Title** becomes the album tag.
4. Enter one track title per line. You can paste a setlist, use generic titles, or look up the show on Setlist.fm with your own API key.
5. Choose **Preview filenames and info text**, check the result, then click **Tag Files**.

The app creates a new folder containing the tagged audio, information text, checksums and any selected extras. It verifies the audio before completing the package. Original files are kept by default, and existing output folders are not overwritten.

Each new file selection in Main starts a fresh package. Saved Settings remain in place.

## Use the standalone tools

The **Tools** tab works independently of the packaging workflow. Add files, choose an operation, review the options and click **Run**.

- Create or verify MD5 and FFP checksum files.
- Convert between supported lossless formats, recompress FLAC, or make MP3 listening copies from lossless audio.
- Inspect audio properties and check audio integrity.
- Check or fix CD sector boundaries, or rewrite safely repairable WAV headers.

Checksum files are created beside the input files, including on external drives. Conversions and repairs create copies in your chosen output folder. See the [full user guide](docs/USER_GUIDE.md#using-the-standalone-tools) for each tool's options and limitations.

## Make it your own

In **Settings**, customise the outer folder name and choose whether to include an Etree subfolder. Edit `template_example.txt` in a text editor to change the information sheet. The finished information text can also be edited after export.

The app preserves sample rate and bit depth. It does not apply EQ, change volume, resample, split tracks or convert MP3 to lossless audio. Keep MP3 and lossless recordings in separate packages.

## Documentation and source

- [Full user guide](docs/USER_GUIDE.md): detailed workflows, folder naming, templates, tool explanations and troubleshooting.
- [Running from Python and development notes](GETTING_STARTED.md): dependencies, source setup, tests and Windows builds.

Settings and activity logs are stored beside the app. They can contain personal paths, recording details and your Setlist.fm API key; share the original release ZIP rather than your used application folder.
