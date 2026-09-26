# Live Audio Tagger

**Portable Windows edition · Release 26 September 2026**

Prepare a live recording for sharing, or use individual audio tools. This guide assumes your recording has already been edited and split into tracks in your usual audio editor.

[Download the Windows release](https://github.com/gambra/live-audio-tagger/releases/latest)

## Contents

- [Quick start](#quick-start)
- [Finding your way around](#finding-your-way-around)
- [Preparing a recording in Main](#preparing-a-recording-in-main)
- [Settings and folder names](#settings-and-folder-names)
- [Using the standalone tools](#using-the-standalone-tools)
- [Troubleshooting](#troubleshooting)
- [Keeping or sharing the app](#keeping-or-sharing-the-app)
- [Appearance and saved log](#appearance-and-saved-log)

## Quick start

1. Download **LiveAudioTagger-Windows-x64.zip** from the release page.
2. Right-click the downloaded ZIP and choose **Extract All**.
3. Keep the extracted folder somewhere you can save files, such as Documents.
4. Open `LiveAudioTagger.exe`. The first launch may take a few seconds.
5. In **Settings**, choose your **Default export destination**.
6. In **Main**, add a recording folder, check the details and track titles, click **Preview filenames and info text**, then **Tag Files**.

There is nothing else to install. Python and the audio libraries are included. This release is for 64-bit Windows 10 and 11. It does not upload anything to DIME, Internet Archive or another site; you upload the finished folder yourself. Internet access is needed only if you choose to use Setlist.fm.

Windows may identify this unsigned app as an unrecognised publisher. Only open a copy obtained from a source you trust.

## Finding your way around

| Tab | What it does |
| --- | --- |
| **Main** | Prepare a complete recording package: renamed audio, tags, information text and checksums. |
| **Tools** | Convert, check or repair files without making a Main package. |
| **Settings** | Choose where to save, folder names, text template and preferences. |

For your first package, the default settings are suitable. You can change folder naming and other preferences later.

## Preparing a recording in Main

### Add the recording

Drop a recording folder into the file list, or use **Add files** / **Add folder**. Select all tracks for one recording together. Adding a new selection in Main starts a **new package** and clears the previous recording details and track list. Saved Settings are kept. Cancelling the file picker keeps the current package.

When you add a folder, the app looks through existing text files and makes its best guess at the artist, date, venue and other details. These are guesses: check them before exporting. Subfolders are searched too.

If pictures or other extras are found, you can choose to copy them into the new package. They keep their names and subfolder layout. Use **Extra files** to review or remove them. Old information text and old checksum files are not copied; the app creates fresh ones. Audio inputs are handled as tracks.

### Check the order

The file list is the order in which tracks will be numbered. Use **Move up** / **Move down** to correct it, or **Remove selected** to exclude a track. The matching track title moves with its file. Clear empties the current selection.

### Fill in the recording details

Artist, date, venue, city, country, **File Title** and Source are required. Use `YYYY-MM-DD` for the date, for example 2026-09-26.

- **File Title** is the album title stored in the audio tags. It is also what the `{{title}}` and `{{album}}` placeholders mean.
- Source can be AUD, SBD or a description of the recording source.
- Genre has suggestions, but you can type your own.
- Taper and **Taping Location** are optional.
- **Show Notes** are for information about the performance.
- **Technical Notes** are for equipment, transfer details and lineage.

Characters such as > are kept in the fields, audio tags and information text. Only file and folder names are made safe for Windows. For example, `Mic > DAT` becomes `Mic - DAT` in a folder name, while the text file still says `Mic > DAT`.

### Enter track titles

Enter one title per line, in the same order as the files. You can paste a setlist and edit it freely. Leave off track numbers: the app adds them. There must be one non-empty title for each file.

**Fill blank titles with date + track number** supplies generic titles when you do not know the songs. You can replace them later.

### Optional: find a show on Setlist.fm

Save your own Setlist.fm API key in Settings, then enter the artist and date on Main and choose **Find setlist by artist and date**. Select the matching show and review what is imported. This needs an internet connection.

If the show has venue information but no songs, the available venue details are brought in and generic track titles are created. If the number of songs differs from your files, edit the list so there is one title per track. You can always enter everything yourself without an API key.

### Preview and export

1. Click **Preview filenames and info text**.
2. Check the destination, folder name, track filenames, text and any extras. The size shown in this preview is an estimate.
3. Click **Tag Files**.
4. Wait for the success message, then use **Open completed folder**.

The app checks the audio before making the completed package available. The information text uses the final audio sizes. You can edit that text file afterward without invalidating the audio checksums.

Use **View log** for more detail if something fails. **Cancel job** stops processing; originals are preserved and unfinished temporary output is normally removed. An existing package is never overwritten. Choose another name or destination.

### What the package contains

- Audio files with consistent filenames and recording tags.
- An information .txt file made from your template.
- An .md5 file to check whether complete audio files have changed.
- An .ffp file for FLAC packages, to check the audio itself.
- Any extra files you chose to copy.

WAV and AIFF tracks are converted losslessly to FLAC. Existing FLAC tracks are copied and tagged. MP3 tracks form a separate MP3 package: they are copied and tagged without being re-encoded and have MD5, but not FFP.

Supported lossless recordings are 16-bit or 24-bit, mono or stereo. Tracks in one package must share the same sample rate and bit depth. Do not mix MP3 and lossless audio. Main does not change volume, EQ, sample rate or bit depth, join tracks or split a recording.

Originals are normally kept. If you enable the deletion option in Settings, you are asked again after a successful export before converted WAV/AIFF originals are permanently deleted. Original FLAC, MP3 and extras are kept.

## Settings and folder names

Settings are saved automatically. Recording details and file lists are not remembered after closing the app.

### Default export destination

Choose an existing folder where new Main packages will be saved. Tools has its own output box for conversions and repairs.

### Outer folder pattern

You can keep the default or arrange the details to suit your collection. Placeholders are words in double braces that the app fills in for you:

```text
{{artist}} - {{date}} - {{title}} ({{source}})
{{date}} - {{artist}} - {{venue}}
```

Useful placeholders:

| Placeholder | What it contains |
| --- | --- |
| `{{artist}}` | Artist as entered |
| `{{date}}` | Show date |
| `{{title}}` or `{{album}}` | **File Title** |
| `{{venue}}` | Venue |
| `{{city}}` | City |
| `{{country}}` | Country |
| `{{source}}` | Recording source |
| `{{genre}}` | Genre |
| `{{taper}}` | Taper |
| `{{prefix}}` | Artist simplified for filenames |

Enter a single folder name, not a path with slashes. The app reports unknown placeholders or invalid names before exporting. **Restore default** restores the original pattern. MP3 packages always have an extra (MP3) at the end.

### Create an Etree named subfolder

This is checked by default. The outer folder then contains a subfolder with the fixed artist/date/format name used for trading recordings. For example:

```text
Example Band - 2026-09-26 - The Hall, Dublin, Ireland (AUD)/
└── exampleband2026-09-26.flac24/
    ├── exampleband2026-09-26t01.flac
    ├── exampleband2026-09-26t02.flac
    ├── exampleband2026-09-26.ffp
    ├── exampleband2026-09-26.md5
    └── exampleband2026-09-26.txt
```

Uncheck this option to put those files directly in the outer folder. Either way, audio and checksum filenames keep the strict naming rules. 16-bit recordings use .flac16 for the subfolder; MP3 recordings use .mp3.

For audio filenames, the artist is lowercase with spaces and special characters removed: Nine Inch Nails becomes nineinchnails; Sunn O))) becomes sunno. Artist names in tags and information text remain as entered.

### Info text template

The supplied `template_example.txt` controls the information text layout. Leave it as supplied, or open it in Notepad to change wording and spacing. Make a copy first if you want to keep the original. You can choose a different template file in Settings.

The words in `{{double braces}}` are filled in automatically. Lines containing `{% ... %}` control optional sections and the track list; keep those intact unless you intend to change the template logic. The app reads the template again for each preview and export, so you do not need to restart after edits.

The folder placeholders also work in the information template. Other useful ones include `{{taping_location}}`, `{{show_notes}}`, `{{tech_notes}}`, `{{format}}`, `{{total_duration}}`, `{{total_size}}` and `{{total_tracks}}`. The supplied file shows how to include the track list. A simpler alternative is to leave the template alone and edit each finished recording's .txt file after export.

### FLAC compression

This controls file size and encoding time for new FLAC conversions. It does not change sound quality. A higher setting usually takes longer and produces a smaller file. Leave the default of 5 if you are unsure. To change the compression of existing FLAC files, use Recompress FLAC in Tools.

### Offer to delete converted originals

Leave this off to keep your WAV/AIFF originals. Turning it on only offers deletion after a successful Main export; it still asks for confirmation. Tools never deletes original files.

## Using the standalone tools

Tools works separately from Main. It does not change Main's recording details or use the package folder pattern. Original audio files are kept unchanged.

1. On Tools, add files or a folder, or drop them into the window.
2. In the popup, choose an action. If files are already listed, choose to replace the current list or add to it. Duplicates are skipped. Cancel leaves the previous selection alone.
3. Review the files at the bottom. Remove any you do not want to process. For sector-boundary repair, arrange them in playback order.
4. For conversions or repairs, choose an existing folder under **Save audio copies in**. For checksums, read the different saving rule below.
5. Choose any options shown, then click Run.
6. Read the report. Select a row for one file's details, or **Show full report** for the whole job. **Save report** creates a readable TXT or a structured JSON.

Drag the dividing bars to give the report or file list more room. **Open output folder** opens the selected result's destination, or the first output folder when no output is selected. If files went to several folders, their individual locations are shown in the report.

Conversions and repairs keep the original base filename, changing only the extension when needed. Existing files are never overwritten. Two inputs that would create the same filename need separate runs or output folders.

**Cancel job** stops processing. Already completed outputs are kept; unfinished temporary outputs are removed. Unrelated file types may appear as Skipped.

### Checksums: Create MD5 / Create FFP / Verify MD5 / FFP

A checksum is a fingerprint used to check whether a file has changed.

MD5 checks the entire file, including its tags. Changing a title or other tag changes its MD5, even if the sound is identical.

FFP checks decoded FLAC audio. Tag-only changes do not change its FFP. FFP is for FLAC files only. For a finished FLAC package, both are useful; Main creates both automatically.

To create checksums:

- Select the files and choose **Create MD5** or **Create FFP**.
- Choose a checksum filename, such as checksums or the show date.
- Run the tool. It saves one checksum file **beside the input files** in each input folder, including on external drives. The audio output destination is not used. You need permission to write in those input folders.
- If a checksum file already exists, enter a different checksum filename.

To verify checksums, select the .md5 or .ffp files and choose **Verify MD5 / FFP**. Keep each checksum file with the files it describes. Results include:

| Result | Meaning |
| --- | --- |
| **Checksum verified** | The expected and calculated fingerprints match. |
| **Checksum mismatch** | The file has changed, is damaged, or belongs to a different version of the recording. Review the details. |
| **File missing** | A file named in the checksum list could not be found. |
| **Error** | The file or checksum entry could not be processed. |

The report shows the expected and calculated checksums and file locations. A match confirms agreement with that checksum list, not the recording's source history. To hash artwork or other non-audio files, use **Add files** and choose the All files filter. Folder scans find audio and checksum files.

### Convert to FLAC / Convert to WAV / Convert to AIFF

Use these to make lossless copies in another supported format. Sample rate, bit depth and channels are kept. The app checks that the output audio samples match the input. Common tags are copied where the target format supports them. MP3 cannot be used as input for these conversions.

### Recompress FLAC

Make new FLAC copies with a different compression setting. Audio stays identical; existing FLAC comments and artwork are retained. Choose another output folder to avoid a filename collision with your originals.

### Create MP3 listening copies

Make smaller listening copies from lossless files. Select the quality option that suits you: highest quality/largest, high quality, or smaller file. MP3 is a lossy format, so keep your lossless originals for archival use. Inputs above 48 kHz must be resampled in a separate audio editor first. This app does not convert or re-encode MP3 input.

### Audio properties

Read a file's format, length, bit depth, sample rate, channels and tags. Nothing is changed.

### Check audio integrity

Read through the complete audio file to look for decoding problems. FLAC is also compared against its built-in audio fingerprint. A matching FLAC reports Audio integrity verified. A FLAC without a stored fingerprint reports Unverified even when it can be read.

Other formats report Readable when decoding finishes successfully. This means the app could read them, not that every possible fault is ruled out. Use MD5/FFP verification too when the recording came with checksum files.

### Check CD sector boundaries

This is mainly for people preparing gapless audio CDs. A CD uses fixed-size blocks of audio. This tool reports whether each track ends on a whole block. It requires 16-bit, 44.1 kHz stereo lossless files. Not aligned is not, by itself, evidence of damaged audio or a problem with ordinary file playback.

### Fix CD sector boundaries

Use the same CD-quality format and put tracks in their correct playback order. The tool slightly moves the internal track boundaries while keeping the combined original audio unchanged. It writes new copies to the chosen folder.

**Pad final track with silence** is optional and off by default. Enable it if you want the last track to end on a whole CD block too; otherwise the final track may remain unaligned. Embedded FLAC cue sheets are removed from the new copies because their track positions may no longer be correct.

### Rewrite WAV headers

A WAV header describes how the audio is stored. This tool rewrites headers that can be repaired safely, keeping the audio and other existing WAV chunks. It cannot recover missing audio or repair every damaged WAV file. Truncated or ambiguous files, and RF64/RIFX variants, are refused rather than guessed.

## Troubleshooting

### "Output already exists" or a checksum filename already exists

Choose a new package name, output folder or checksum filename. The app does not replace existing files. For audio conversion to the same format, select a different folder from the one containing your originals.

### Cannot write / cannot save settings

Put the app and outputs in folders you can write to. For checksum creation, check the input folder's permissions. Reconnect an external drive if needed.

### Template or placeholder error

Check the template path in Settings and the spelling inside `{{...}}`. Folder patterns must make a single valid folder name. Use **Restore default** for the folder pattern if you want to start again.

### Unsupported audio / different sample rates or bit depths

Use 16-bit or 24-bit mono/stereo lossless audio. Prepare matching tracks in your audio editor first. Keep MP3 and lossless packages separate.

### Track count differs from the setlist

Edit the titles until there is exactly one title per input file.

### Setlist.fm does not return the expected show

Check the artist, date, API key and internet connection. You can continue by entering the details and track list manually.

### Checksum mismatch

Review which file failed. Tag edits can explain an MD5 mismatch. Compare the FFP for FLAC audio or check against a known good copy before deciding whether the audio itself is damaged.

### Need more detail

Use **View log** for Main, or the result rows and **Save report** in Tools.

## Keeping or sharing the app

The download contains four files:

| File | Purpose |
| --- | --- |
| `LiveAudioTagger.exe` | The application, with its dependencies included |
| `template_example.txt` | The editable information-text template |
| `README.txt` | This guide |
| `THIRD_PARTY_LICENSES.txt` | Notices for the included software libraries |

Keep these together. There is no installer and no separate Python or audio converter to install. The app briefly unpacks its included components into a temporary folder when starting; allow a few seconds and about 70 MB of free temporary space. Closing normally removes that temporary folder.

After first use, `settings.ini` appears beside the app. It holds your preferences, local paths and Setlist.fm API key as readable text. Keep it private. Share the original ZIP, or the four release files above without your `settings.ini` or `LiveAudioTagger.log`. When moving the app, check saved destination and template paths in Settings. To reset preferences, close the app and rename `settings.ini` as a backup.

This version has no automatic update checking or Windows file associations. It does not support SHN, APE, MP2, MKW, old CFP/SFV/ST5 checksums, torrents or lossy-source analysis. Use other software for audio editing or those formats.

## Appearance and saved log

The app follows your Windows light/dark preference; dark mode is not fixed. The header shows only the name. The block-art microphone is the application icon.

The **Tag Files** button on the right of Main creates the full verified package.

**View log** shows this session's messages. **Open log file** opens `LiveAudioTagger.log` beside the app. Timestamped messages, errors and Tools results are appended across runs. Starting a new package may clear the on-screen log, but does not erase the saved history. If the file cannot be written, **View log** explains why. After closing the app, you can archive or delete the log to start a fresh one. Logs can contain recording details and local file paths; omit them when sharing the application.
