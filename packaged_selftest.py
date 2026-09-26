"""Headless smoke test of the actual bundled executable, using temporary audio."""
import json
import os
import tempfile
import traceback
import random
import math
from array import array
from pathlib import Path
from threading import Event


def require(condition, message):
    # Assertions are stripped by the optimized release build.
    if not condition:
        raise RuntimeError(message)


def run(report_path):
    report = {'ok': False, 'checks': []}
    try:
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
        import soundfile as sf
        from PySide6.QtWidgets import QApplication
        from flac_tagger import MainWindow, ROOT
        from tagger_core import Show, inspect_audio, make_plan, export_package
        from audio_tools import run_tools
        from mutagen.flac import FLAC
        from tools_tab import OperationDialog
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory(prefix='flac-tagger-selftest-') as temp:
            base = Path(temp)
            window = MainWindow(settings_path=base / 'test-settings.ini')
            window.show()
            app.processEvents()
            require(window.windowTitle() == 'Live Audio Tagger' and window.heading.text() == 'Live Audio Tagger', 'Wrong application name')
            require(not window.windowIcon().isNull(), 'Bundled icon missing')
            require(window.tag_button.text() == 'Tag Files', 'Wrong export button label')
            require([window.tabs.tabText(i) for i in range(3)] == ['Main', 'Tools', 'Settings'], 'Wrong tabs')
            require(window.template_path.text() == str(ROOT / 'template_example.txt'), 'Wrong template path')
            template = window.read_template()
            report['checks'].append('GUI starts; external template loads beside executable')
            rng = random.Random(42)
            for bits in (16, 24):
                for extension in ('wav', 'aiff', 'flac'):
                    path = base / f'input{bits}.{extension}'
                    samples = array('i', [rng.randint(-2147483648, 2147483647) for _ in range(8192)])
                    with sf.SoundFile(str(path), mode='w', samplerate=48000, channels=2, subtype=f'PCM_{bits}') as audio:
                        audio.buffer_write(samples, dtype='int32')
                    show = Show('Test Artist', '2026-09-25', 'Hall', 'Dublin', 'Ireland', 'Test', f'{extension}{bits}/AUD')
                    plan = make_plan([inspect_audio(path)], show, ['Test Track'], base, template)
                    folder = export_package(plan, Event(), lambda _: None, lambda _: None)
                    require((folder / f'{plan.stem}.ffp').is_file(), 'Missing FFP')
                    require((folder / f'{plan.stem}.md5').is_file(), 'Missing MD5')
                    report['checks'].append(f'{bits}-bit {extension}: export, tags, decoded PCM and both checksums verified')
            mp3 = base / 'input.mp3'
            with sf.SoundFile(str(mp3), mode='w', samplerate=44100, channels=1, format='MP3') as audio:
                audio.buffer_write(array('f', [math.sin(i * .05) * .2 for i in range(44100)]), dtype='float32')
            show = Show('Test Artist', '2026-09-25', 'Hall', 'Dublin', 'Ireland', 'Test', 'MP3')
            plan = make_plan([inspect_audio(mp3)], show, ['Test Track'], base, template)
            folder = export_package(plan, Event(), lambda _: None, lambda _: None)
            require((folder / f'{plan.stem}.md5').is_file(), 'Missing MP3 MD5')
            report['checks'].append('MP3: ID3 tagging, preserved MPEG payload and MD5 verified')
            show = Show('Test Artist', '2026-09-25', 'Hall', 'Dublin', 'Ireland', 'Live > Session', 'Mic > DAT / FLAC')
            flat = make_plan([inspect_audio(base / 'input24.flac')], show, ['Intro > Song'], base,
                             '{{title}}\nSource: {{source}}', folder_pattern='{{date}} - {{title}} ({{source}})',
                             etree_subfolder=False)
            folder = export_package(flat, Event(), lambda _: None, lambda _: None)
            require(folder == flat.outer and flat.inner_name == '', 'Unexpected Etree subfolder')
            require(folder.name == '2026-09-25 - Live - Session (Mic - DAT - FLAC)', 'Folder sanitization failed')
            tags = FLAC(folder / flat.names[0])
            require(tags['SOURCE'] == [show.source] and tags['ALBUM'] == [show.album], 'Tags lost original punctuation')
            require((folder / f'{flat.stem}.txt').read_text(encoding='utf-8') == 'Live > Session\nSource: Mic > DAT / FLAC\n', 'Info text lost original punctuation')
            require((folder / f'{flat.stem}.ffp').is_file() and (folder / f'{flat.stem}.md5').is_file(), 'Direct-folder checksums missing')
            report['checks'].append('Custom folder pattern and direct-folder export; punctuation preserved in tags and info text')
            def tool(operation, paths, destination, **options):
                rows = run_tools(operation, paths, destination, Event(), lambda _: None, lambda _: None, **options)
                require(bool(rows) and all(r.status not in ('Error', 'Checksum mismatch', 'File missing') for r in rows), str(rows))
                return rows
            source = base / 'input24.flac'
            for kind in ('md5', 'ffp'):
                tool(kind, [source], base / 'unused-output-folder')
                rows = tool('verify', [base / f'checksums.{kind}'], base)
                require(rows[0].status == 'Checksum verified', 'Standalone checksum failed')
            for operation in ('flac', 'wav', 'aiff', 'recompress', 'mp3', 'wav_header'):
                destination = base / f'tool-{operation}'
                destination.mkdir()
                tool(operation, [base / 'input16.wav' if operation == 'wav_header' else source], destination)
            for operation in ('check', 'properties'):
                tool(operation, [source], base)
            cd = base / 'cd.wav'
            with sf.SoundFile(str(cd), mode='w', samplerate=44100, channels=2, subtype='PCM_16') as audio:
                audio.buffer_write(array('h', [i % 2000 for i in range(3000)]), dtype='int16')
            destination = base / 'sectors'
            destination.mkdir()
            tool('fix_sectors', [cd], destination, pad_final=True)
            require(tool('sectors', [destination / cd.name], base)[0].status == 'Aligned', 'Sector fix failed')
            report['checks'].append('All 13 standalone operations completed successfully')
            window.tabs.setCurrentWidget(window.tools_tab)
            window.tools_tab.inputs_ready([source])
            window.tools_tab.finished(tool('properties', [source], base))
            app.processEvents()
            require(window.tools_tab.table.rowCount() == 1 and not window.files, 'Tools state isolation failed')
            report['checks'].append('Tools interface displays results independently of Main')
            dialog = OperationDialog(window.tools_tab, 'properties', True, [base / 'checksums.ffp'])
            require(dialog.selection() == ('verify', 'replace'), 'Import action chooser failed')
            dialog.append.setChecked(True)
            require(dialog.selection() == ('verify', 'add'), 'Add-to-list option failed')
            require('source_analysis' not in dialog.buttons, 'Removed analysis tool still present')
            dialog.close()
            window.folder_pattern.setText('{{date}} - {{title}}')
            window.etree_subfolder.setChecked(False)
            window.close()
            reopened = MainWindow(settings_path=base / 'test-settings.ini')
            require(reopened.folder_pattern.text() == '{{date}} - {{title}}' and not reopened.etree_subfolder.isChecked(), 'Folder settings not saved')
            reopened.close()
            report['checks'].append('Action chooser, Add/Replace options and saved folder settings verified')
            require('Live Audio Tagger started.' in window.log_path.read_text(encoding='utf-8'), 'Persistent log missing')
        report['ok'] = True
    except Exception:
        report['error'] = traceback.format_exc()
    Path(report_path).write_text(json.dumps(report, indent=2), encoding='utf-8')
    return 0 if report['ok'] else 1
