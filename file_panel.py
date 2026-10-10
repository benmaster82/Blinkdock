"""On-demand file activity view for the selected Claude Code session."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QPoint, QProcess, Qt, QTimer
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QScrollArea,
                               QStyle, QToolButton, QVBoxLayout, QWidget)

from file_activity import count_files, recent_files


def parse_git_status(output: bytes) -> list[tuple[str, str, str]]:
    """Parse porcelain v1 -z, including the extra path on rename/copy records."""
    fields = output.split(b'\0')
    entries = []
    index = 0
    while index < len(fields) and fields[index]:
        field = fields[index]
        index += 1
        if len(field) < 4 or field[2:3] != b' ':
            continue
        status = field[:2].decode('ascii', errors='replace')
        path = field[3:].decode('utf-8', errors='replace')
        previous = ''
        if 'R' in status or 'C' in status:
            if index < len(fields):
                previous = fields[index].decode('utf-8', errors='replace')
                index += 1
        entries.append((status, path, previous))
    return entries


def _age(timestamp: float) -> str:
    seconds = max(0, int(time.time() - timestamp))
    if seconds < 60:
        return 'now'
    if seconds < 3600:
        return f'{seconds // 60}m'
    return f'{seconds // 3600}h'


def _display_path(path: str, cwd: str) -> str:
    if not cwd:
        return path
    try:
        return str(Path(path).relative_to(Path(cwd)))
    except ValueError:
        return path


class FilePanel(QFrame):
    def __init__(self, sessions_provider: Callable[[], list[dict]], parent: QWidget) -> None:
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self._sessions_provider = sessions_provider
        self._sessions: list[dict] = []
        self._choice_signature: list[tuple[str, str]] = []
        self._git_process: QProcess | None = None
        self._git_generation = 0
        self._git_session = ''
        self._git_entries: list[tuple[str, str, str]] | str = 'Checking Git status...'
        self.setObjectName('filePanel')
        self.setStyleSheet('''
            QFrame#filePanel { background: #191d22; color: #e8edf2;
                border: 1px solid #454b52; border-radius: 6px; }
            QLabel { color: #e8edf2; border: 0; background: transparent; }
            QComboBox { background: #262c32; color: #e8edf2; border: 1px solid #454b52;
                border-radius: 4px; padding: 5px 8px; min-height: 24px; }
            QComboBox QAbstractItemView { background: #262c32; color: #e8edf2;
                selection-background-color: #344e59; }
            QScrollArea { border: 0; background: transparent; }
            QToolButton { border: 0; background: transparent; padding: 3px; }
            QToolButton:hover { background: #303740; border-radius: 4px; }
        ''')

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(8)
        title_row = QHBoxLayout()
        title = QLabel('File activity', self)
        title.setFont(QFont('Segoe UI', 11, QFont.DemiBold))
        title_row.addWidget(title)
        title_row.addStretch()
        close = QToolButton(self)
        close.setIcon(self.style().standardIcon(QStyle.SP_DialogCloseButton))
        close.setToolTip('Close file activity')
        close.clicked.connect(self.hide)
        title_row.addWidget(close)
        outer.addLayout(title_row)

        self.session_picker = QComboBox(self)
        self.session_picker.setToolTip('Select Claude Code session')
        self.session_picker.currentIndexChanged.connect(self._selected_session_changed)
        outer.addWidget(self.session_picker)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.viewport().setStyleSheet('background: #191d22;')
        self._content = QWidget(scroll)
        self._content.setStyleSheet('background: #191d22;')
        self._scroll = scroll
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 2, 0, 2)
        self._content_layout.setSpacing(0)
        scroll.setWidget(self._content)
        outer.addWidget(scroll)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(2000)
        self._refresh_timer.timeout.connect(self.refresh)
        self.setFixedWidth(430)
        self.setFixedHeight(390)

    def show_below(self, anchor: QWidget) -> None:
        screen = anchor.screen()
        area = screen.availableGeometry()
        self.setFixedWidth(min(430, max(280, area.width() - 16)))
        self.setFixedHeight(min(390, max(260, area.height() - 32)))
        self.refresh()
        x = min(max(anchor.x() + anchor.width() - self.width(), area.left()),
                area.right() - self.width() + 1)
        y = anchor.y() + anchor.height() + 6
        if y + self.height() > area.bottom() + 1:
            y = anchor.y() - self.height() - 6
        self.move(QPoint(x, y))
        self.show()
        self.raise_()
        self._refresh_timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        self._refresh_timer.stop()
        self._stop_git()
        super().hideEvent(event)

    def _stop_git(self) -> None:
        self._git_generation += 1
        if self._git_process is not None:
            if self._git_process.state() != QProcess.NotRunning:
                self._git_process.kill()
            self._git_process = None

    def _selected_session(self) -> dict | None:
        session_id = self.session_picker.currentData()
        return next((s for s in self._sessions if s['id'] == session_id), None)

    def _selected_session_changed(self) -> None:
        self._stop_git()
        self._refresh_activity()
        self._start_git()

    def refresh(self) -> None:
        sessions = self._sessions_provider()
        previous = self.session_picker.currentData()
        choices = [(s['id'], s.get('project', '')) for s in sessions]
        if choices != self._choice_signature:
            self._stop_git()
            self.session_picker.blockSignals(True)
            self.session_picker.clear()
            for session in sessions:
                label = session.get('project') or 'Unnamed session'
                self.session_picker.addItem(f'{label}  [{session["id"][:8]}]', session['id'])
            selected = self.session_picker.findData(previous)
            self.session_picker.setCurrentIndex(selected if selected >= 0 else 0)
            self.session_picker.blockSignals(False)
            self._choice_signature = choices
        self._sessions = sessions
        self._refresh_activity()
        if self._git_process is None:
            self._start_git()

    def _clear_content(self) -> None:
        position = self._scroll.verticalScrollBar().value()
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        QTimer.singleShot(0, lambda: self._scroll.verticalScrollBar().setValue(position))

    def _section(self, title: str) -> None:
        label = QLabel(title, self._content)
        label.setFont(QFont('Segoe UI', 8, QFont.DemiBold))
        label.setStyleSheet('color: #8f9aa5; padding-top: 9px; padding-bottom: 5px;')
        self._content_layout.addWidget(label)

    def _message(self, text: str) -> None:
        label = QLabel(text, self._content)
        label.setStyleSheet('color: #9ea8b2; padding: 7px 0 9px 0;')
        label.setWordWrap(True)
        self._content_layout.addWidget(label)

    def _file_row(self, path: str, detail: str, marker: str = '',
                  color: str = '#8f9aa5', marker_hint: str = '',
                  full_path: str = '') -> None:
        row = QWidget(self._content)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(2, 5, 2, 5)
        layout.setSpacing(8)
        name = QLabel(row)
        name.setFont(QFont('Segoe UI', 9, QFont.DemiBold))
        name.setText(QFontMetrics(name.font()).elidedText(
            path, Qt.ElideMiddle, self.width() - 155))
        name.setToolTip(full_path or path)
        layout.addWidget(name, 1)
        if marker:
            status = QLabel(marker, row)
            status.setFixedWidth(27)
            status.setAlignment(Qt.AlignCenter)
            status.setFont(QFont('Consolas', 8, QFont.DemiBold))
            status.setStyleSheet(f'color: {color};')
            status.setToolTip(marker_hint or path)
            layout.addWidget(status)
        suffix = QLabel(detail if len(detail) < 12 else 'renamed', row)
        suffix.setStyleSheet('color: #87919d;')
        suffix.setFont(QFont('Segoe UI', 8))
        suffix.setToolTip(full_path or path)
        layout.addWidget(suffix)
        row.setToolTip(full_path or path)
        self._content_layout.addWidget(row)

    def _refresh_activity(self) -> None:
        self._clear_content()
        session = self._selected_session()
        if session is None:
            self._message('No sessions detected')
            return
        session_id = session['id']
        files = recent_files(session_id)
        total = count_files([session_id])
        self._section(f'SESSION ACTIVITY  {total}')
        cwd = session.get('cwd', '')
        pending = session.get('pending_file', '')
        if pending and session.get('state') == 'working':
            self._file_row(_display_path(pending, cwd), 'pending',
                           color='#f2b705', full_path=pending)
        if files:
            for path, tool_name, timestamp in files:
                self._file_row(_display_path(path, cwd), _age(timestamp),
                               tool_name[:1], '#4ebbb7', f'{tool_name} completed', path)
            if total > len(files):
                self._message(f'Showing the latest {len(files)} files')
        elif not pending:
            self._message('No successful Edit or Write yet')
        self._section('PROJECT GIT STATUS  (SHARED)')
        if self._git_session != session_id:
            self._message('Checking Git status...')
        elif isinstance(self._git_entries, str):
            self._message(self._git_entries)
        elif not self._git_entries:
            self._message('Working tree clean')
        else:
            for status, path, previous in self._git_entries[:100]:
                code = status.strip() or '?'
                color = ('#ef7976' if 'D' in status else '#35c488' if 'A' in status or status == '??'
                         else '#f2b705' if 'M' in status else '#8fb2d5')
                detail = 'from ' + previous if previous else ''
                self._file_row(path, detail, code, color,
                               f'Git status: {status.replace(" ", "-")}',
                               f'{path}\nfrom {previous}' if previous else path)
            if len(self._git_entries) > 100:
                self._message(f'Showing 100 of {len(self._git_entries)} changes')
        self._content_layout.addStretch()

    def _start_git(self) -> None:
        session = self._selected_session()
        if session is None:
            return
        cwd = session.get('cwd', '')
        changed_session = self._git_session != session['id']
        self._git_session = session['id']
        if not cwd or not Path(cwd).is_dir():
            self._git_entries = 'Project folder unavailable'
            self._refresh_activity()
            return
        if changed_session:
            self._git_entries = 'Checking Git status...'
            self._refresh_activity()
        process = QProcess(self)
        self._git_process = process
        self._git_generation += 1
        generation = self._git_generation
        process.setWorkingDirectory(cwd)
        process.finished.connect(
            lambda code, _status: self._git_finished(process, generation, code))
        process.errorOccurred.connect(
            lambda _error: self._git_failed(process, generation))
        process.start('git', ['--no-optional-locks', 'status', '--porcelain=v1', '-z',
                              '--untracked-files=normal'])
        QTimer.singleShot(10000, lambda: self._git_timeout(process, generation))

    def _git_finished(self, process: QProcess, generation: int, code: int) -> None:
        if generation != self._git_generation:
            process.deleteLater()
            return
        self._git_process = None
        entries = (parse_git_status(bytes(process.readAllStandardOutput()))
                   if code == 0 else 'Git status unavailable for this folder')
        process.deleteLater()
        if entries != self._git_entries:
            self._git_entries = entries
            self._refresh_activity()

    def _git_failed(self, process: QProcess, generation: int) -> None:
        if generation == self._git_generation:
            self._git_generation += 1
            self._git_process = None
            self._git_entries = 'Git is not available'
            if self.isVisible():
                self._refresh_activity()
        process.deleteLater()

    def _git_timeout(self, process: QProcess, generation: int) -> None:
        if generation == self._git_generation and process.state() != QProcess.NotRunning:
            self._git_generation += 1
            process.kill()
            self._git_process = None
            self._git_entries = 'Git status timed out'
            if self.isVisible():
                self._refresh_activity()
