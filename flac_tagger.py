"""Run with: python flac_tagger.py"""
from __future__ import annotations

import json
from datetime import datetime
import sys
from pathlib import Path
from threading import Event
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from PySide6.QtCore import QObject, QThread, Signal, Slot, Qt, QUrl, QSettings
from PySide6.QtGui import QDesktopServices, QIcon, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPlainTextEdit, QPushButton, QLabel, QComboBox, QSpinBox,
    QCheckBox, QTabWidget, QFileDialog, QMessageBox, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QDialog,
    QListWidget, QDialogButtonBox, QSplitter, QScrollArea,
)
from tagger_core import (
    SUPPORTED, Show, ValidationError, Cancelled, inspect_audio, natural_key,
    duration_text, make_plan, render_info, export_package, delete_converted_sources, DEFAULT_FOLDER_PATTERN,
)
from folder_import import scan_folder
from tools_tab import ToolsTab

ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
ASSETS = Path(__file__).resolve().parent / 'assets'
APP_NAME = 'Live Audio Tagger'
GENRES = ('Alternative|Ambient|Avantgarde|Bass|Blues|Classical|'
          'Country|Dance|Disco|Dubstep|Electronic|Experimental|'
          'Folk|Funk|Garage|Gospel|Hardcore|Hip-Hop|House|'
          'Industrial|Instrumental|Instrumental Metal|Instrumental Rock|'
          'Jazz|Jungle|Metal|Noise|Opera|Pop|Psychedelic Rock|'
          'Psychedelic|Punk|R&B|Rap|Reggae|Rock|Soul|Techno|Trance|').split('|')


class Worker(QObject):
    done = Signal(object)
    failed = Signal(str)
    log = Signal(str)
    progress = Signal(int)
    finished = Signal()

    def __init__(self, function):
        super().__init__()
        self.function = function

    @Slot()
    def run(self):
        try:
            self.done.emit(self.function(self))
        except Cancelled as exc:
            self.log.emit(str(exc))
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()


def lookup_setlists(artist: str, show_date: str, api_key: str):
    query = {'artistName': artist, 'date': '-'.join(reversed(show_date.split('-')))}
    request = Request('https://api.setlist.fm/rest/1.0/search/setlists?' + urlencode(query),
                      headers={'x-api-key': api_key, 'Accept': 'application/json',
                               'User-Agent': 'LiveAudioTagger/0.1'})
    try:
        with urlopen(request, timeout=25) as response:
            return json.load(response).get('setlist', [])
    except HTTPError as exc:
        if exc.code == 404:
            return []
        if exc.code in (401, 403):
            raise ValidationError('Setlist.fm rejected the API key or access request.') from None
        if exc.code == 429:
            raise ValidationError('Setlist.fm rate limit reached. Please try again later.') from None
        raise ValidationError(f'Setlist.fm returned HTTP {exc.code}.') from None


class AudioTable(QTableWidget):
    paths_dropped = Signal(object)

    def __init__(self):
        super().__init__(0, 5)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.paths_dropped.emit([Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()])
        event.acceptProposedAction()


class MainWindow(QMainWindow):
    def __init__(self, settings_path=None, log_path=None):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(str(ASSETS / 'live_audio_tagger.png')))
        self.log_path = Path(log_path) if log_path else (Path(settings_path).parent if settings_path else ROOT) / 'LiveAudioTagger.log'
        self.log_write_failed = False
        self.resize(1150, 950)
        self.settings = QSettings(str(settings_path or ROOT / 'settings.ini'), QSettings.Format.IniFormat)
        self.setAcceptDrops(True)
        self.files = []
        self.extras = []
        self.import_hint = ''
        self.thread = None
        self.worker = None
        self.on_worker_done = None
        self.cancel_event = Event()
        self.completed_folder = None
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        header = QHBoxLayout()
        self.heading = QLabel(APP_NAME)
        heading_font = self.heading.font()
        heading_font.setPixelSize(21)
        heading_font.setWeight(QFont.Weight.DemiBold)
        self.heading.setFont(heading_font)
        self.heading.setContentsMargins(6, 6, 6, 6)
        header.addWidget(self.heading)
        header.addStretch()
        layout.addLayout(header)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.build_main_tab()
        self.build_settings_tab()
        self.tools_tab = ToolsTab(self)
        self.tabs.insertTab(1, self.tools_tab, 'Tools')
        self.preview_dialog, self.preview_box = self.text_dialog('Output preview')
        self.log_dialog, self.log_box = self.text_dialog('Activity log')
        self.log_location = QLabel(f'History is appended to: {self.log_path}')
        self.log_location.setWordWrap(True)
        self.log_dialog.layout().insertWidget(0, self.log_location)
        self.log_open_button = QPushButton('Open log file')
        self.log_open_button.clicked.connect(self.open_log_file)
        self.log_dialog.layout().insertWidget(2, self.log_open_button)
        footer = QHBoxLayout()
        self.status = QLabel('Import files or drop a folder here to begin.')
        footer.addWidget(self.status, 1)
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(220)
        footer.addWidget(self.progress)
        self.cancel_button = QPushButton('Cancel job')
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_event.set)
        footer.addWidget(self.cancel_button)
        layout.addLayout(footer)
        self.log_message(f'{APP_NAME} started.')

    def button(self, text, callback, layout):
        button = QPushButton(text)
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

    def text_dialog(self, title):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(850, 650)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        layout.addWidget(text)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        return dialog, text

    def build_main_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        sections = QSplitter(Qt.Orientation.Vertical)
        sections.addWidget(self.build_files_section())
        sections.addWidget(self.build_details_section())
        sections.setChildrenCollapsible(False)
        sections.setSizes([210, 600])
        layout.addWidget(sections, 1)
        self.destination_label = QLabel()
        self.destination_label.setWordWrap(True)
        layout.addWidget(self.destination_label)
        actions = QHBoxLayout()
        self.button('Preview filenames and info text', self.show_preview, actions)
        self.open_button = self.button('Open completed folder', self.open_completed, actions)
        self.open_button.setEnabled(False)
        self.button('View log', lambda: self.log_dialog.show(), actions)
        actions.addStretch(1)
        self.tag_button = self.button('Tag Files', self.start_export, actions)
        self.tag_button.setMinimumWidth(125)
        self.tag_button.setMinimumHeight(32)
        layout.addLayout(actions)
        self.tabs.addTab(page, 'Main')

    def build_files_section(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        hint = QLabel('Drop audio files or folders into the list below, or add them using the buttons.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        actions = QHBoxLayout()
        self.button('Add files…', self.pick_files, actions)
        self.button('Add folder…', self.pick_folder, actions)
        self.button('Remove selected', self.remove_files, actions)
        self.button('Move up', lambda: self.move_file(-1), actions)
        self.button('Move down', lambda: self.move_file(1), actions)
        self.button('Clear', self.clear_files, actions)
        self.button('Extra files…', self.review_extras, actions)
        layout.addLayout(actions)
        self.table = AudioTable()
        self.table.paths_dropped.connect(self.import_paths)
        self.table.setMinimumHeight(100)
        self.table.setHorizontalHeaderLabels(['Input file (export order)', 'Format', 'Sample rate', 'Channels', 'Duration'])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table, 1)
        self.summary = QLabel('No files imported.')
        layout.addWidget(self.summary)
        return page

    def build_details_section(self):
        splitter = QSplitter()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        details = QWidget()
        form = QFormLayout(details)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.fields = {}
        labels = [('artist', 'Artist:'), ('date', 'Date (YYYY-MM-DD):'),
                  ('venue', 'Venue:'), ('city', 'City:'), ('country', 'Country:'),
                  ('album', 'File Title:'), ('source', 'Source:'),
                  ('taper', 'Taper:'), ('taping_location', 'Taping Location:')]
        for key, label in labels:
            field = QLineEdit('AUD' if key == 'source' else '')
            self.fields[key] = field
            form.addRow(label, field)
        self.fields['artist'].setToolTip('Filenames use the artist in lowercase with spaces and special characters removed.')
        self.fields['source'].setToolTip('Used in the folder name, tags and info text. Put equipment and transfer details in Technical notes.')
        self.genre = QComboBox()
        self.genre.addItems(GENRES)
        self.genre.setEditable(True)
        self.genre.setCurrentText('Rock')
        form.addRow('Genre:', self.genre)
        for key, label in [('show_notes', 'Show Notes:'), ('tech_notes', 'Technical Notes:')]:
            field = QPlainTextEdit()
            field.setMaximumHeight(75)
            self.fields[key] = field
            form.addRow(label, field)
        scroll.setWidget(details)
        splitter.addWidget(scroll)
        track_page = QWidget()
        track_layout = QVBoxLayout(track_page)
        for text in ('Track titles — one line per input file, in the same order.',
                     'Paste titles only; track numbers are added automatically on export.'):
            label = QLabel(text)
            label.setWordWrap(True)
            track_layout.addWidget(label)
        self.tracks = QPlainTextEdit()
        self.tracks.setPlaceholderText('Introduction\nFirst song\nSecond song\nEncore')
        track_layout.addWidget(self.tracks, 1)
        self.track_count = QLabel()
        self.tracks.textChanged.connect(self.update_track_count)
        track_layout.addWidget(self.track_count)
        self.button('Fill blank titles with date + track number', self.generic_titles, track_layout)
        self.button('Find setlist by artist and date…', self.find_setlist, track_layout)
        splitter.addWidget(track_page)
        splitter.setSizes([550, 500])
        self.update_track_count()
        return splitter

    def build_settings_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel('Settings are saved automatically and restored the next time you open the app.'))
        form = QFormLayout()
        self.api_key = QLineEdit(self.settings.value('setlist_api_key', '', type=str))
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow('Setlist.fm API key', self.api_key)
        destination = QHBoxLayout()
        self.output = QLineEdit(self.settings.value('output_directory', str(ROOT), type=str))
        destination.addWidget(self.output, 1)
        self.button('Browse…', self.pick_output, destination)
        form.addRow('Default export destination', destination)
        template_row = QHBoxLayout()
        self.template_path = QLineEdit(self.settings.value('template_path', str(ROOT / 'template_example.txt'), type=str))
        template_row.addWidget(self.template_path, 1)
        self.button('Browse…', self.pick_template, template_row)
        form.addRow('Info text template', template_row)
        layout.addLayout(form)
        description = QLabel('Edit the template in your preferred text editor. The file is read again for each preview and export.')
        description.setWordWrap(True)
        layout.addWidget(description)
        naming = QFormLayout()
        pattern_row = QHBoxLayout()
        self.folder_pattern = QLineEdit(self.settings.value('folder_pattern', DEFAULT_FOLDER_PATTERN, type=str))
        pattern_row.addWidget(self.folder_pattern, 1)
        self.button('Restore default', lambda: self.folder_pattern.setText(DEFAULT_FOLDER_PATTERN), pattern_row)
        naming.addRow('Outer folder pattern', pattern_row)
        naming_help = QLabel('Use info-template placeholders, for example {{date}} - {{artist}} - {{venue}}. '
                             '{{title}} (or {{album}}) is the File Title from Main. Also available: '
                             '{{city}}, {{country}}, {{source}}, {{genre}}, {{taper}} and {{prefix}}. '
                             'Enter one folder name, without path separators. MP3 packages retain the (MP3) suffix.')
        naming_help.setWordWrap(True)
        naming.addRow(naming_help)
        self.etree_subfolder = QCheckBox('Create an Etree named subfolder')
        self.etree_subfolder.setChecked(self.settings.value('etree_subfolder', True, type=bool))
        naming.addRow(self.etree_subfolder)
        folder_hint = QLabel('Checked: audio and package files go in artistYYYY-MM-DD.flac16 / .flac24 / .mp3. '
                             'Unchecked: they go directly in the outer folder. Track filenames always keep Etree naming. '
                             'Use Preview on Main to check the complete output path before exporting.')
        folder_hint.setWordWrap(True)
        naming.addRow(folder_hint)
        layout.addLayout(naming)
        compression_row = QHBoxLayout()
        compression_row.addWidget(QLabel('FLAC compression (new conversions only)'))
        self.compression = QSpinBox()
        self.compression.setRange(0, 8)
        self.compression.setValue(self.settings.value('compression', 5, type=int))
        compression_row.addWidget(self.compression)
        compression_row.addStretch()
        layout.addLayout(compression_row)
        self.delete_originals = QCheckBox('Offer to delete converted WAV/AIFF originals after successful export')
        self.delete_originals.setChecked(self.settings.value('delete_originals', False, type=bool))
        layout.addWidget(self.delete_originals)
        layout.addStretch()
        self.settings_status = QLabel()
        self.settings_status.setWordWrap(True)
        layout.addWidget(self.settings_status)
        for field in (self.api_key, self.output, self.template_path, self.folder_pattern):
            field.textChanged.connect(self.save_settings)
        self.compression.valueChanged.connect(self.save_settings)
        self.delete_originals.toggled.connect(self.save_settings)
        self.etree_subfolder.toggled.connect(self.save_settings)
        self.update_destination()
        self.tabs.addTab(page, 'Settings')

    def update_destination(self):
        self.destination_label.setText(f'Export to: {self.output.text()}  (change in Settings)')

    def save_settings(self, *_):
        for key, value in [('setlist_api_key', self.api_key.text().strip()),
                           ('output_directory', self.output.text()),
                           ('template_path', self.template_path.text()),
                           ('folder_pattern', self.folder_pattern.text()),
                           ('etree_subfolder', self.etree_subfolder.isChecked()),
                           ('compression', self.compression.value()),
                           ('delete_originals', self.delete_originals.isChecked())]:
            self.settings.setValue(key, value)
        self.settings.sync()
        self.settings_status.setText('Settings saved.' if self.settings.status() == QSettings.Status.NoError
                                     else 'Could not save settings. Check write access to the application folder.')
        self.update_destination()

    def read_template(self):
        path = Path(self.template_path.text()).expanduser()
        try:
            return path.read_text(encoding='utf-8-sig')
        except (OSError, UnicodeError) as exc:
            raise ValidationError(f'Cannot read the text template. Check its path in Settings.\n{exc}') from exc

    def show_preview(self):
        if self.preview() is not None:
            self.preview_dialog.exec()

    @Slot(str)
    def log_message(self, text):
        self.log_box.appendPlainText(text)
        timestamp = datetime.now().astimezone().isoformat(timespec='seconds')
        try:
            with self.log_path.open('a', encoding='utf-8') as handle:
                for line in str(text).splitlines() or ['']:
                    handle.write(f'[{timestamp}] {line}\n')
        except OSError as exc:
            if not self.log_write_failed:
                self.log_box.appendPlainText(f'Could not save the external log: {exc}')
            self.log_write_failed = True
            self.log_location.setText(f'Log is not being saved. Check write access to: {self.log_path}')
        else:
            self.log_write_failed = False
            self.log_location.setText(f'History is appended to: {self.log_path}')

    def open_log_file(self):
        if self.log_path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.log_path.resolve())))
        else:
            QMessageBox.information(self, 'Log file unavailable', f'No saved log file is available at:\n{self.log_path}')

    @Slot(str)
    def error(self, text):
        self.log_message(f'ERROR: {text}')
        QMessageBox.warning(self, 'Please check', text)

    def start_worker(self, function, on_done, cancellable=False):
        if self.thread is not None:
            return
        self.cancel_event = Event()
        self.progress.setValue(0)
        self.tabs.setEnabled(False)
        self.cancel_button.setEnabled(cancellable)
        self.status.setText('Working…')
        self.thread = QThread(self)
        self.worker = Worker(function)
        self.on_worker_done = on_done
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self.log_message)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.done.connect(self.deliver_worker_result)
        self.worker.failed.connect(self.error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.worker_finished)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    @Slot(object)
    def deliver_worker_result(self, value):
        # A QObject-bound slot keeps callbacks (including lambdas) on the GUI thread.
        try:
            self.on_worker_done(value)
        except Exception as exc:
            self.error(str(exc))

    @Slot()
    def worker_finished(self):
        self.thread = None
        self.worker = None
        self.on_worker_done = None
        self.tabs.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.status.setText('Ready. Use View log for details of the last job.')

    def pick_files(self):
        names, _ = QFileDialog.getOpenFileNames(self, 'Select audio files', '', 'Audio (*.flac *.wav *.aif *.aiff *.mp3)')
        if names:
            self.import_paths([Path(n) for n in names])

    def pick_folder(self):
        name = QFileDialog.getExistingDirectory(self, 'Select audio folder')
        if name:
            self.import_paths([Path(name)])

    def import_paths(self, paths):
        if self.thread is not None or not paths:
            return
        self.clear_files()
        def inspect(worker):
            candidates = set()
            info_sets, extras = [], []
            for path in paths:
                if path.is_dir():
                    worker.log.emit(f'Scanning info text and extra files in {path}')
                    audio, info, folder_extras = scan_folder(path)
                    candidates.update(audio)
                    info_sets.append((audio, info))
                    extras.extend(folder_extras)
                elif path.suffix.lower() in SUPPORTED:
                    candidates.add(path.resolve())
            if not candidates and not info_sets:
                raise ValidationError('No new supported audio files found.')
            result = []
            for path in sorted(candidates, key=natural_key):
                worker.log.emit(f'Inspecting {path.name}')
                result.append(inspect_audio(path))
            return result, info_sets, extras
        self.start_worker(inspect, self.folder_imported)

    def folder_imported(self, result):
        files, info_sets, extras = result
        self.files_imported(files)
        guessed = []
        for audio, info in info_sets:
            for warning in info.warnings:
                self.log_message(warning)
            for path in info.files:
                self.log_message(f'Read info text: {path}')
            for key, value in info.fields.items():
                if key == 'genre':
                    if self.genre.currentText() == 'Rock' and not self.genre.lineEdit().isModified():
                        self.genre.setCurrentText(value)
                    continue
                field = self.fields.get(key)
                if field is None:
                    continue
                current = field.toPlainText() if isinstance(field, QPlainTextEdit) else field.text()
                default_source = key == 'source' and current == 'AUD' and not field.isModified()
                if not current.strip() or default_source:
                    if isinstance(field, QPlainTextEdit):
                        field.setPlainText(value)
                    else:
                        field.setText(value)
                    guessed.append(key.replace('_', ' '))
            if info.titles:
                if len(info.titles) == len(audio):
                    by_path = dict(zip(audio, info.titles))
                    titles = self.title_lines()
                    titles += [''] * max(0, len(self.files) - len(titles))
                    for index, f in enumerate(self.files):
                        if f.path in by_path and (not titles[index].strip() or titles[index] == f'Track {index + 1:02}'):
                            titles[index] = by_path[f.path]
                    self.tracks.setPlainText('\n'.join(titles))
                else:
                    self.log_message(f'Info text has {len(info.titles)} titles for {len(audio)} files; track titles were not applied. Review the original text.')
        if guessed:
            self.log_message('Guessed details (please review): ' + ', '.join(dict.fromkeys(guessed)))
            self.import_hint = ' · Review details guessed from info text'
        known = {extra.source for extra in self.extras}
        fresh = []
        for extra in extras:
            if extra.source not in known:
                fresh.append(extra)
                known.add(extra.source)
        if fresh and self.confirm_extras(fresh):
            self.extras.extend(fresh)
        self.update_extra_summary()

    def confirm_extras(self, extras):
        box = QMessageBox(self)
        box.setWindowTitle('Copy extra files and folders?')
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(f'Found {len(extras)} extra files or empty folders. Copy them into the new audio folder as well?')
        box.setInformativeText('Names and subfolder paths will be kept. Audio being processed and existing FFP, MD5 and TXT files are excluded.')
        box.setDetailedText('\n'.join(f'{extra.relative}{"/" if extra.stamp is None else ""}\n  From: {extra.source}' for extra in extras))
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        return box.exec() == QMessageBox.StandardButton.Yes

    def review_extras(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('Extra files to copy')
        dialog.resize(650, 450)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel('Uncheck any extras you no longer want included in this package.'))
        entries = QListWidget()
        for extra in self.extras:
            entries.addItem(str(extra.relative) + ('/' if extra.stamp is None else ''))
            item = entries.item(entries.count() - 1)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setToolTip(str(extra.source))
        layout.addWidget(entries)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.extras = [extra for i, extra in enumerate(self.extras) if entries.item(i).checkState() == Qt.CheckState.Checked]
            self.update_extra_summary()

    def update_extra_summary(self):
        self.table.setToolTip(f'{len(self.extras)} extra files/folders selected for export. Use Extra files to review.')
        self.summary.setText(f'{len(self.files)} audio files · {duration_text(sum(f.duration for f in self.files))} total · {len(self.extras)} extras selected' + self.import_hint)

    def title_lines(self):
        text = self.tracks.toPlainText()
        return text.splitlines() if text else []

    def files_imported(self, files):
        old_titles = self.title_lines()
        old_titles += [''] * max(0, len(self.files) - len(old_titles))
        self.files.extend(files)
        self.tracks.setPlainText('\n'.join(old_titles + [f.title or f'Track {i:02}' for i, f in enumerate(files, len(self.files) - len(files) + 1)]))
        self.refresh_table()

    def refresh_table(self):
        self.table.setRowCount(len(self.files))
        for row, f in enumerate(self.files):
            fmt = f'MP3 / {round(f.bitrate / 1000)} kbps' if f.kind == 'mp3' else f'{f.path.suffix[1:].upper()} / {f.bits}-bit'
            for col, value in enumerate([f.path.name, fmt, str(f.rate), 'Mono' if f.channels == 1 else 'Stereo', duration_text(f.duration)]):
                item = QTableWidgetItem(value)
                item.setToolTip(str(f.path))
                self.table.setItem(row, col, item)
        self.update_extra_summary()
        self.update_track_count()

    def remove_files(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        titles = self.title_lines()
        for row in rows:
            self.files.pop(row)
            if row < len(titles):
                titles.pop(row)
        self.tracks.setPlainText('\n'.join(titles))
        self.refresh_table()

    def move_file(self, delta):
        rows = {i.row() for i in self.table.selectedIndexes()}
        if len(rows) != 1:
            return
        row = rows.pop()
        other = row + delta
        if not 0 <= other < len(self.files):
            return
        titles = self.title_lines()
        titles += [''] * max(0, len(self.files) - len(titles))
        self.files[row], self.files[other] = self.files[other], self.files[row]
        titles[row], titles[other] = titles[other], titles[row]
        self.tracks.setPlainText('\n'.join(titles))
        self.refresh_table()
        self.table.selectRow(other)

    def clear_files(self):
        self.files = []
        self.extras = []
        self.import_hint = ''
        self.tracks.clear()
        for key, field in self.fields.items():
            if isinstance(field, QPlainTextEdit):
                field.clear()
            else:
                field.setText('AUD' if key == 'source' else '')
                field.setModified(False)
        self.genre.setCurrentText('Rock')
        self.genre.lineEdit().setModified(False)
        self.completed_folder = None
        self.open_button.setEnabled(False)
        self.preview_box.clear()
        self.preview_dialog.hide()
        self.log_box.clear()
        self.progress.setValue(0)
        self.refresh_table()

    def update_track_count(self):
        titles = self.title_lines()
        self.track_count.setText(f'{len(titles)} title lines / {len(self.files)} audio files')

    def generic_titles(self):
        titles = self.title_lines()
        if len(titles) > len(self.files):
            self.error('There are more title lines than files. Remove the extra lines first.')
            return
        titles += [''] * (len(self.files) - len(titles))
        show_date = self.fields['date'].text().strip() or 'YYYY-MM-DD'
        self.tracks.setPlainText('\n'.join(t if t.strip() and t != f'Track {i:02}' else f'{show_date} T{i:02}' for i, t in enumerate(titles, 1)))

    def get_plan(self):
        values = {key: field.toPlainText().strip() if isinstance(field, QPlainTextEdit) else field.text().strip()
                  for key, field in self.fields.items()}
        return make_plan(self.files, Show(**values, genre=self.genre.currentText().strip()),
                         self.title_lines(), Path(self.output.text()), self.read_template(), self.compression.value(), tuple(self.extras),
                         folder_pattern=self.folder_pattern.text(), etree_subfolder=self.etree_subfolder.isChecked())

    def preview(self):
        try:
            plan = self.get_plan()
            paths = '\n'.join(f'  {n}' for n in plan.names)
            paths += f'\n  {plan.stem}.md5'
            if plan.files[0].kind != 'mp3':
                paths += f'\n  {plan.stem}.ffp'
            paths += f'\n  {plan.stem}.txt'
            if plan.extras:
                paths += '\n\nEXTRAS (unchanged names)\n' + '\n'.join(f'  {extra.relative}' for extra in plan.extras)
            info = render_info(plan, [f.stamp[0] for f in plan.files])
            self.preview_box.setPlainText(f'{plan.folder}\n{paths}\n\nINFO TEXT (size is estimated until export)\n\n{info}')
            return plan
        except Exception as exc:
            self.error(str(exc))
            return None

    def start_export(self):
        plan = self.preview()
        if plan is None:
            return
        offer_delete = self.delete_originals.isChecked()
        self.start_worker(lambda worker: export_package(plan, self.cancel_event, worker.log.emit, worker.progress.emit),
                          lambda folder: self.export_finished(plan, folder, offer_delete), cancellable=True)

    def export_finished(self, plan, folder, offer_delete):
        self.completed_folder = folder
        self.open_button.setEnabled(True)
        converted = [f for f in plan.files if f.kind == 'pcm']
        if offer_delete and converted:
            box = QMessageBox(self)
            box.setWindowTitle('Verified package created — delete converted originals?')
            box.setIcon(QMessageBox.Icon.Warning)
            box.setText(f'The package was verified and saved to:\n{folder}\n\nPermanently delete {len(converted)} original WAV/AIFF files? This cannot be undone.')
            box.setDetailedText('\n'.join(str(f.path) for f in converted))
            box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            box.setDefaultButton(QMessageBox.StandardButton.No)
            if box.exec() == QMessageBox.StandardButton.Yes:
                errors = delete_converted_sources(plan)
                self.log_message(f'Original deletion finished: {len(errors)} errors.')
                if errors:
                    self.error('\n'.join(errors))
                # Deleted inputs are no longer usable; remove only those actually gone.
                remaining = [(f, title) for f, title in zip(self.files, self.title_lines()) if f.path.exists()]
                self.files = [f for f, _ in remaining]
                self.tracks.setPlainText('\n'.join(t for _, t in remaining))
                self.refresh_table()
        QMessageBox.information(self, 'Export complete', f'Audio verified; package ready:\n{folder}\n\nThe generated .txt file can be edited in any text editor.')

    def pick_output(self):
        path = QFileDialog.getExistingDirectory(self, 'Choose output directory', self.output.text())
        if path:
            self.output.setText(path)

    def pick_template(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Choose text template', self.template_path.text(), 'Text (*.txt);;All files (*)')
        if path:
            self.template_path.setText(path)

    def open_completed(self):
        if self.completed_folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.completed_folder)))

    def find_setlist(self):
        artist = self.fields['artist'].text().strip()
        show_date = self.fields['date'].text().strip()
        key = self.api_key.text().strip()
        if not artist or not key:
            self.error('Enter the artist and show date, and add your Setlist.fm API key in Settings.')
            return
        from datetime import date
        try:
            if date.fromisoformat(show_date).isoformat() != show_date:
                raise ValueError()
        except ValueError:
            self.error('Enter a real date in YYYY-MM-DD format.')
            return
        self.start_worker(lambda worker: lookup_setlists(artist, show_date, key), self.choose_setlist)

    def choose_setlist(self, results):
        if not results:
            QMessageBox.information(self, 'Setlist.fm', 'No matching setlists found.')
            return
        dialog = QDialog(self)
        dialog.setWindowTitle('Choose and review a setlist')
        dialog.resize(650, 550)
        layout = QVBoxLayout(dialog)
        choices = QListWidget()
        for result in results:
            venue = result.get('venue', {})
            choices.addItem(f"{result.get('artist', {}).get('name', '')} — {result.get('eventDate', '')} — {venue.get('name', '')}, {venue.get('city', {}).get('name', '')}")
        layout.addWidget(choices)
        preview = QPlainTextEdit()
        preview.setReadOnly(True)
        layout.addWidget(preview, 1)
        link = QLabel()
        link.setOpenExternalLinks(True)
        layout.addWidget(link)
        update_venue = QCheckBox('Also update venue, city and country')
        layout.addWidget(update_venue)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        def names(result):
            return [song.get('name', '') for group in result.get('sets', {}).get('set', []) for song in group.get('song', []) if song.get('name')]
        def selected(row):
            result = results[row]
            titles = names(result)
            if titles:
                preview.setPlainText('\n'.join(titles) + f'\n\n{len(titles)} songs / {len(self.files)} audio files.\nImported titles remain fully editable.')
            else:
                preview.setPlainText('This show has no song list. Venue details will be imported and generic date + track-number titles will be created for the audio files.')
                update_venue.setChecked(True)
            update_venue.setEnabled(bool(titles))
            from html import escape
            url = result.get('url', '')
            link.setText(f'<a href="{escape(url, quote=True)}">Source: setlist.fm — view original setlist</a>' if url.startswith('https://www.setlist.fm/') else 'Source: setlist.fm')
        choices.currentRowChanged.connect(selected)
        choices.setCurrentRow(0)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            result = results[choices.currentRow()]
            self.apply_setlist(result, names(result), update_venue.isChecked())

    def apply_setlist(self, result, titles, update_venue):
        self.tracks.setPlainText('\n'.join(titles))
        if update_venue or not titles:
            venue = result.get('venue', {})
            city = venue.get('city', {})
            for field, value in [('venue', venue.get('name', '')), ('city', city.get('name', '')), ('country', city.get('country', {}).get('name', ''))]:
                if value:
                    self.fields[field].setText(value)
        if not titles:
            self.generic_titles()
            self.log_message('Setlist.fm show has no songs: imported available venue details and generated generic track titles.')
        elif len(titles) != len(self.files):
            QMessageBox.information(self, 'Track count differs', f'Imported {len(titles)} songs for {len(self.files)} files. Edit the track titles to match before export.')

    def dragEnterEvent(self, event):
        if self.thread is None and event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if self.thread is None:
            paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
            if self.tabs.currentWidget() is self.tools_tab:
                self.tools_tab.add_paths(paths)
            else:
                self.import_paths(paths)
            event.acceptProposedAction()

    def closeEvent(self, event):
        if self.thread is not None:
            QMessageBox.information(self, 'Job running', 'Wait for the current job to finish, or cancel the export before closing.')
            event.ignore()
        else:
            self.save_settings()
            self.log_message(f'{APP_NAME} closed.')
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(QIcon(str(ASSETS / 'live_audio_tagger.png')))
    app.setStyle('Fusion')
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--self-test':
        from packaged_selftest import run
        sys.exit(run(sys.argv[2]))
    else:
        main()
