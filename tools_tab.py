"""Independent file selection and results for the offline Tools tab."""
import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem, QComboBox, QLineEdit, QSpinBox,
    QCheckBox, QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView,
    QPlainTextEdit, QSplitter, QAbstractItemView, QDialog, QDialogButtonBox,
    QGroupBox, QRadioButton, QButtonGroup, QGridLayout)

from audio_tools import OPERATIONS, WRITES, Result, scan_inputs, run_tools, save_report
from tagger_core import Cancelled

DESCRIPTIONS = {
    'properties': 'Read technical properties and tags. No files are changed.',
    'check': 'Decode all audio. FLAC also checks its embedded fingerprint. A missing fingerprint is reported as Unverified.',
    'md5': 'Create whole-file checksums beside the input files, with one MD5 file per input folder. Works on external drives too.',
    'ffp': 'Fingerprint decoded FLAC audio. Create one FFP file in each input folder, beside the FLAC files.',
    'verify': 'Select MD5/FFP files. Each referenced file is checked; the report shows matching checksums, mismatches and missing files.',
    'flac': 'Convert lossless input to FLAC, preserving sample rate, bit depth and channels. MP3 input is rejected.',
    'wav': 'Convert lossless input to WAV. Original samples and supported tags are preserved. MP3 input is rejected.',
    'aiff': 'Convert lossless input to AIFF. Original samples and supported tags are preserved. MP3 input is rejected.',
    'recompress': 'Re-encode FLAC with the chosen compression level. Preserve audio, comments and artwork.',
    'mp3': 'Create lossy listening copies from lossless input only. No resampling: inputs above 48 kHz must be resampled externally.',
    'sectors': 'CD alignment check: 16-bit, 44.1 kHz stereo only. A CD sector contains 588 sample frames.',
    'fix_sectors': 'ORDER MATTERS. Shift internal boundaries backward to CD sectors, preserving the joined audio. Optional silence padding applies only to the last track. Embedded FLAC cue sheets are removed because boundaries change.',
    'wav_header': 'Rewrite a safely readable PCM RIFF WAV header. Audio and extra RIFF chunks are retained. Truncated/ambiguous files are refused.',
}


class OperationDialog(QDialog):
    """One import decision: choose a task and how to handle the existing list."""
    def __init__(self, parent, current, has_files, incoming):
        super().__init__(parent)
        self.setWindowTitle('Choose an action')
        self.setMinimumWidth(620)
        layout = QVBoxLayout(self)
        heading = QLabel('What would you like to do with these files?')
        heading.setStyleSheet('font-size: 16px; font-weight: 600;')
        layout.addWidget(heading)
        layout.addWidget(QLabel(f'{len(incoming)} file(s) or folder(s) selected. Choose an action, then review the list before running.'))
        self.actions = QButtonGroup(self)
        self.buttons = {}
        grid = QGridLayout()
        groups = [('Checksums', ('verify', 'md5', 'ffp')),
                  ('Convert audio', ('flac', 'wav', 'aiff', 'recompress', 'mp3')),
                  ('Inspect audio', ('properties', 'check', 'sectors')),
                  ('Repair copies', ('fix_sectors', 'wav_header'))]
        for index, (title, keys) in enumerate(groups):
            group = QGroupBox(title)
            group_layout = QVBoxLayout(group)
            for key in keys:
                button = QRadioButton(OPERATIONS[key])
                button.setToolTip(DESCRIPTIONS[key])
                self.actions.addButton(button)
                self.buttons[key] = button
                group_layout.addWidget(button)
            grid.addWidget(group, index // 2, index % 2)
        layout.addLayout(grid)
        if incoming and all(Path(p).suffix.lower() in ('.md5', '.ffp') for p in incoming):
            current = 'verify'
        self.buttons[current].setChecked(True)
        self.hint = QLabel(DESCRIPTIONS[current])
        self.hint.setWordWrap(True)
        self.hint.setMinimumHeight(65)
        layout.addWidget(self.hint)
        for key, button in self.buttons.items():
            button.toggled.connect(lambda checked, k=key: self.hint.setText(DESCRIPTIONS[k]) if checked else None)
        self.replace = QRadioButton('Clear the current list and use these files')
        self.append = QRadioButton('Add these files to the current list (skip duplicates)')
        self.list_choice = QButtonGroup(self)
        self.list_choice.addButton(self.replace)
        self.list_choice.addButton(self.append)
        self.replace.setChecked(True)
        if has_files:
            group = QGroupBox('There are already files in Tools')
            choices = QVBoxLayout(group)
            choices.addWidget(self.replace)
            choices.addWidget(self.append)
            layout.addWidget(group)
        else:
            self.replace.hide()
            self.append.hide()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Use selected action')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selection(self):
        return next(key for key, button in self.buttons.items() if button.isChecked()), ('replace' if self.replace.isChecked() else 'add')


class DropList(QListWidget):
    paths_dropped = Signal(object)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.paths_dropped.emit([Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()])
        event.acceptProposedAction()


class ToolsTab(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.paths, self.results = [], []
        layout = QVBoxLayout(self)
        title = QLabel('Add files or drop a folder, choose an action, then run it. Your Main package stays separate.')
        title.setWordWrap(True)
        layout.addWidget(title)
        actions = QHBoxLayout()
        self.button('Add files…', self.pick_files, actions)
        self.button('Add folder…', self.pick_folder, actions)
        actions.addStretch()
        layout.addLayout(actions)
        self.files = DropList()
        self.files.setMinimumHeight(65)
        self.files.paths_dropped.connect(self.add_paths)
        self.count = QLabel('No files selected.')
        form = QFormLayout()
        self.operation = QComboBox()
        for key, name in OPERATIONS.items():
            self.operation.addItem(name, key)
        form.addRow('Operation', self.operation)
        self.description = QLabel()
        self.description.setWordWrap(True)
        form.addRow(self.description)
        self.output_controls = QWidget()
        output_row = QHBoxLayout(self.output_controls)
        output_row.setContentsMargins(0, 0, 0, 0)
        self.output = QLineEdit(window.output.text())
        output_row.addWidget(self.output, 1)
        self.browse_output = self.button('Browse…', self.pick_output, output_row)
        self.output_label = QLabel('Save audio copies in')
        form.addRow(self.output_label, self.output_controls)
        self.checksum_location = QLabel('Save beside input files — one checksum file per folder. Existing files are never overwritten.')
        self.checksum_location.setWordWrap(True)
        form.addRow(self.checksum_location)
        self.options = QWidget()
        options = QHBoxLayout(self.options)
        options.setContentsMargins(0, 0, 0, 0)
        self.compression_label = QLabel('FLAC compression')
        options.addWidget(self.compression_label)
        self.compression = QSpinBox()
        self.compression.setRange(0, 8)
        self.compression.setValue(window.compression.value())
        options.addWidget(self.compression)
        self.quality = QComboBox()
        self.quality.addItem('MP3 VBR: highest quality / largest', 0.0)
        self.quality.addItem('MP3 VBR: high quality', 0.2)
        self.quality.addItem('MP3 VBR: smaller file', 0.5)
        self.quality.setCurrentIndex(1)
        options.addWidget(self.quality)
        self.manifest_label = QLabel('Checksum filename')
        options.addWidget(self.manifest_label)
        self.manifest = QLineEdit('checksums')
        self.manifest.setPlaceholderText('Checksum filename')
        options.addWidget(self.manifest)
        self.pad = QCheckBox('Pad final track with silence to a full sector')
        options.addWidget(self.pad)
        options.addStretch()
        form.addRow(self.options)
        layout.addLayout(form)
        run_row = QHBoxLayout()
        self.run_button = self.button('Run selected tool', self.run, run_row)
        self.run_button.setMinimumHeight(32)
        self.save_button = self.button('Save report…', self.save_results, run_row)
        self.save_button.setEnabled(False)
        self.open_button = self.button('Open output folder', self.open_output, run_row)
        run_row.addStretch()
        layout.addLayout(run_row)
        self.summary = QLabel('Ready when you are. Tools never changes or deletes the original audio.')
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        sections = QSplitter(Qt.Orientation.Vertical)
        report = QGroupBox('Results and report')
        report_layout = QVBoxLayout(report)
        splitter = QSplitter(Qt.Orientation.Vertical)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(['File', 'Result', 'Details'])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.verticalHeader().hide()
        self.table.currentCellChanged.connect(self.show_detail)
        splitter.addWidget(self.table)
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMinimumHeight(150)
        self.detail.setPlaceholderText('The full report will appear here. Select a result above to inspect one file.')
        splitter.addWidget(self.detail)
        splitter.setSizes([150, 300])
        report_layout.addWidget(splitter)
        report_actions = QHBoxLayout()
        self.button('Show full report', self.show_report, report_actions)
        report_actions.addStretch()
        report_layout.addLayout(report_actions)
        sections.addWidget(report)
        file_group = QGroupBox('Files to process — drop files or folders here')
        file_layout = QVBoxLayout(file_group)
        file_actions = QHBoxLayout()
        file_actions.addWidget(self.count, 1)
        self.button('Remove selected', self.remove_selected, file_actions)
        self.button('Move up', lambda: self.move(-1), file_actions)
        self.button('Move down', lambda: self.move(1), file_actions)
        self.button('Clear list', self.clear, file_actions)
        file_layout.addLayout(file_actions)
        file_layout.addWidget(self.files)
        sections.addWidget(file_group)
        sections.setStretchFactor(0, 4)
        sections.setStretchFactor(1, 1)
        sections.setSizes([540, 150])
        layout.addWidget(sections, 1)
        self.operation.currentIndexChanged.connect(self.operation_changed)
        self.operation_changed()
        self.refresh()

    def button(self, text, callback, layout):
        button = QPushButton(text)
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

    def operation_changed(self):
        operation = self.operation.currentData()
        self.description.setText(DESCRIPTIONS[operation])
        checksum = operation in ('md5', 'ffp')
        audio_output = operation in WRITES and not checksum
        self.output_controls.setVisible(audio_output)
        self.output_label.setVisible(audio_output)
        self.checksum_location.setVisible(checksum)
        self.open_button.setVisible(operation in WRITES)
        self.run_button.setText('Run: ' + OPERATIONS[operation])
        self.compression.setVisible(operation in ('flac', 'recompress'))
        self.compression_label.setVisible(operation in ('flac', 'recompress'))
        self.quality.setVisible(operation == 'mp3')
        self.manifest.setVisible(checksum)
        self.manifest_label.setVisible(checksum)
        self.pad.setVisible(operation == 'fix_sectors')

    def pick_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, 'Select audio or checksum files', '',
            'Audio and checksums (*.flac *.wav *.aif *.aiff *.mp3 *.md5 *.ffp);;All files (*)')
        if files:
            self.add_paths(files)

    def pick_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Add a folder to Tools')
        if folder:
            self.add_paths([folder])

    def add_paths(self, paths):
        if self.window.thread is not None:
            return
        choice = self.choose_import(paths)
        if choice is None:
            return
        operation, mode = choice
        self.window.start_worker(lambda worker: scan_inputs(paths),
            lambda found: self.inputs_ready(found, mode, operation))

    def choose_import(self, paths):
        dialog = OperationDialog(self, self.operation.currentData(), bool(self.paths), paths)
        return dialog.selection() if dialog.exec() == QDialog.DialogCode.Accepted else None

    def inputs_ready(self, paths, mode='add', operation=None):
        if not paths:
            self.window.error('No supported audio or checksum files were found. The current list has been kept.')
            return
        if mode == 'replace':
            self.paths = []
        known = set(self.paths)
        for path in paths:
            path = Path(path).resolve()
            if path not in known:
                self.paths.append(path)
                known.add(path)
        self.reset_results()
        if operation is not None:
            self.operation.setCurrentIndex(self.operation.findData(operation))
        self.refresh()

    def refresh(self):
        self.files.clear()
        for path in self.paths:
            item = QListWidgetItem(str(path))
            item.setToolTip(str(path))
            self.files.addItem(item)
        self.count.setText(f'{len(self.paths)} files selected')
        self.run_button.setEnabled(bool(self.paths))

    def remove_selected(self):
        rows = {self.files.row(item) for item in self.files.selectedItems()}
        self.paths = [p for i, p in enumerate(self.paths) if i not in rows]
        self.reset_results()
        self.refresh()

    def move(self, delta):
        row = self.files.currentRow()
        other = row + delta
        if row >= 0 and 0 <= other < len(self.paths):
            self.paths[row], self.paths[other] = self.paths[other], self.paths[row]
            self.reset_results()
            self.refresh()
            self.files.setCurrentRow(other)

    def clear(self):
        self.paths = []
        self.reset_results()
        self.refresh()

    def reset_results(self):
        self.results = []
        self.table.setRowCount(0)
        self.detail.clear()
        self.save_button.setEnabled(False)
        self.summary.setText('Review the files below, then run the selected action.')

    def pick_output(self):
        folder = QFileDialog.getExistingDirectory(self, 'Choose output directory', self.output.text())
        if folder:
            self.output.setText(folder)

    def run(self):
        operation, paths = self.operation.currentData(), tuple(self.paths)
        destination = self.output.text()
        options = dict(compression=self.compression.value(), mp3_quality=self.quality.currentData(),
                       manifest_name=self.manifest.text().strip(), pad_final=self.pad.isChecked())
        self.reset_results()
        self.summary.setText('Running… Use Cancel job below to stop.')
        def job(worker):
            try:
                return run_tools(operation, paths, destination, self.window.cancel_event,
                                 worker.log.emit, worker.progress.emit, **options)
            except Cancelled:
                return [Result(OPERATIONS[operation], 'Cancelled', 'Stopped; unfinished temporary files removed.')]
            except Exception as exc:
                return [Result(OPERATIONS[operation], 'Error', str(exc))]
        self.window.start_worker(job, self.finished, cancellable=True)

    def finished(self, results):
        self.results = results
        self.save_button.setEnabled(bool(results))
        self.table.setRowCount(len(results))
        counts = {}
        for row, result in enumerate(results):
            self.window.log_message(self.report_entry(result))
            counts[result.status] = counts.get(result.status, 0) + 1
            brief = result.output or self.readable_detail(result).splitlines()[0]
            for col, value in enumerate((Path(result.file).name, result.status, brief)):
                item = QTableWidgetItem(value)
                item.setToolTip(result.file if col == 0 else self.readable_detail(result))
                self.table.setItem(row, col, item)
        self.summary.setText(' · '.join(f'{key}: {value}' for key, value in counts.items()) or 'No results.')
        self.show_report()

    @staticmethod
    def readable_detail(result):
        if result.status == 'Info':
            try:
                info = json.loads(result.detail)
                labels = {'format': 'Format', 'bits': 'Bit depth', 'sample_rate': 'Sample rate (Hz)',
                          'channels': 'Channels', 'duration_seconds': 'Duration (seconds)',
                          'frames': 'Sample frames', 'size_bytes': 'Size (bytes)', 'bitrate': 'Bitrate (bits/second)'}
                text = '\n'.join(f'{label}: {info[key] if info[key] is not None else "Not available"}' for key, label in labels.items())
                return text + '\n\nTags:\n' + ('\n'.join(f'{k}: {v}' for k, v in info['tags'].items()) or 'No tags found.')
            except (ValueError, KeyError, TypeError):
                pass
        return result.detail

    def report_entry(self, result):
        return f'{result.status}\nFile: {result.file}\n\n{self.readable_detail(result)}' + (f'\n\nSaved to: {result.output}' if result.output else '')

    def show_report(self):
        self.detail.setPlainText(('\n\n' + '-' * 64 + '\n\n').join(self.report_entry(r) for r in self.results))

    def show_detail(self, row, *_):
        if 0 <= row < len(self.results):
            result = self.results[row]
            self.detail.setPlainText(self.report_entry(result))

    def save_results(self):
        if not self.results:
            self.window.error('Run a tool before saving its results.')
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Save tool results', 'tool-results.txt', 'Text (*.txt);;JSON (*.json)')
        if path:
            try:
                if Path(path).suffix.lower() == '.json':
                    save_report(self.results, path)
                else:
                    Path(path).write_text(self.summary.text() + '\n\n' + '\n\n'.join(self.report_entry(r) for r in self.results) + '\n', encoding='utf-8')
            except Exception as exc:
                self.window.error(str(exc))

    def open_output(self):
        row = self.table.currentRow()
        outputs = [r.output for r in self.results if r.output]
        selected = self.results[row].output if 0 <= row < len(self.results) else ''
        if selected or outputs:
            path = Path(selected or outputs[0]).parent
        elif self.operation.currentData() in ('md5', 'ffp') and self.paths:
            path = self.paths[0].parent
        else:
            path = Path(self.output.text()).expanduser()
        if path.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))
