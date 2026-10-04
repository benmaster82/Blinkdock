"""A desktop Dynamic Island for Claude Code.

A frameless, always-on-top pill docked to the top of the screen. It stays small
and calm while Claude works and expands to tap you on the shoulder when Claude is
waiting for input, has finished, or hit an error. State is driven entirely by a
JSON status file (written by hook_bridge.py), so the island itself is a pure
renderer and never talks to Claude directly.
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

from PySide6.QtCore import (Property, QEasingCurve, QPointF, QPropertyAnimation,
                            QRectF, Qt, QTimer)
from PySide6.QtGui import (QAction, QColor, QFont, QFontMetrics, QIcon, QPainter,
                           QPainterPath, QPixmap)
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

from config import (DEFAULT_STATE, STATES, load_settings, load_terminal_hwnd,
                    save_settings, sessions_dir)
from hook_bridge import write_session
from winfocus import find_terminals, raise_hwnd, raise_window

SINGLE_INSTANCE_KEY = 'claude-island-single-instance'
# When several sessions run at once, the island shows the most urgent one.
PRIORITY = {'offline': 0, 'idle': 1, 'done': 2, 'working': 3, 'error': 4, 'waiting': 5}

ASSETS = Path(__file__).with_name('assets')
COLLAPSED = (132, 52)
EXPANDED = (332, 60)
TOP_MARGIN = 12


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def clamp01(value: float) -> float:
    # Elastic easing (OutBack) and the pulse can overshoot past 1.0; alpha must not.
    return max(0.0, min(1.0, value))


class Island(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                            | Qt.Tool | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self.settings = load_settings()
        self.state = DEFAULT_STATE
        self.detail = ''
        self._applied: tuple | None = None
        self._expand = 0.0
        self._pulse = 0.0
        self._center_x: float | None = self.settings['center_x']
        self._drag_offset: QPointF | None = None
        self._press_pos: QPointF | None = None
        self._moved = False
        self._sessions_dir = sessions_dir()
        self._waiting_ids: set[str] = set()

        self.avatar = self._load_avatar()

        self._expand_anim = QPropertyAnimation(self, b'expand')
        self._expand_anim.setDuration(380)
        self._pulse_anim = QPropertyAnimation(self, b'pulse')
        self._pulse_anim.setDuration(1600)
        self._pulse_anim.setLoopCount(-1)
        self._pulse_anim.setKeyValueAt(0.0, 0.0)
        self._pulse_anim.setKeyValueAt(0.5, 1.0)
        self._pulse_anim.setKeyValueAt(1.0, 0.0)
        self._pulse_anim.setEasingCurve(QEasingCurve.InOutSine)

        self._poll = QTimer(self)
        self._poll.setInterval(150)
        self._poll.timeout.connect(self._read_sessions)
        self._poll.start()

        self._apply_geometry()
        self.set_state(DEFAULT_STATE, animate=False)
        self._setup_tray()

    def _setup_tray(self) -> None:
        icon = QIcon(str(ASSETS / 'clawd.png'))
        if icon.isNull():
            icon = self.style().standardIcon(self.style().StandardPixmap.SP_ComputerIcon)
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip('Claude Island')
        menu = QMenu()
        self._toggle_action = QAction('Hide', menu)
        self._toggle_action.triggered.connect(self.toggle_visibility)
        menu.addAction(self._toggle_action)
        quit_action = QAction('Quit', menu)
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self.toggle_visibility()

    def toggle_visibility(self) -> None:
        if self.isVisible():
            self.hide()
            self._toggle_action.setText('Show island')
        else:
            self._apply_geometry()
            self.show()
            self.raise_()
            self._toggle_action.setText('Hide')

    # --- animated properties -------------------------------------------------
    def _get_expand(self) -> float:
        return self._expand

    def _set_expand(self, value: float) -> None:
        self._expand = value
        self._apply_geometry()
        self.update()

    expand = Property(float, _get_expand, _set_expand)

    def _get_pulse(self) -> float:
        return self._pulse

    def _set_pulse(self, value: float) -> None:
        self._pulse = value
        self.update()

    pulse = Property(float, _get_pulse, _set_pulse)

    # --- geometry ------------------------------------------------------------
    def _apply_geometry(self) -> None:
        width = round(lerp(COLLAPSED[0], EXPANDED[0], self._expand))
        height = round(lerp(COLLAPSED[1], EXPANDED[1], self._expand))
        self.setFixedSize(width, height)
        screen = self.screen() or QApplication.primaryScreen()
        area = screen.availableGeometry()
        centre = self._center_x if self._center_x is not None else area.center().x()
        x = round(centre - width / 2)
        x = max(area.left(), min(x, area.right() - width))
        self.move(x, area.top() + int(self.settings.get('top_margin', TOP_MARGIN)))

    # --- state ---------------------------------------------------------------
    def set_state(self, state: str, detail: str = '', animate: bool = True) -> None:
        if state not in STATES:
            state = 'idle'
        if (state, detail) == self._applied:
            return  # polled every 150 ms: only react when something actually changed
        changed_state = self._applied is None or state != self.state
        self.state, self.detail = state, detail
        self._applied = (state, detail)
        spec = STATES[state]

        if changed_state:
            target = 1.0 if spec['expanded'] else 0.0
            if animate:
                self._expand_anim.stop()
                opening = target > self._expand
                self._expand_anim.setEasingCurve(QEasingCurve.OutBack if opening else QEasingCurve.InOutCubic)
                self._expand_anim.setStartValue(self._expand)
                self._expand_anim.setEndValue(target)
                self._expand_anim.start()
            else:
                self._set_expand(target)
            if spec['pulse']:
                if self._pulse_anim.state() != QPropertyAnimation.Running:
                    self._pulse_anim.start()
            else:
                self._pulse_anim.stop()
                self._set_pulse(0.0)
        self.update()

    def _chime(self) -> None:
        if sys.platform != 'win32':
            return
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except (ImportError, RuntimeError):
            pass

    def _load_sessions(self) -> list[dict]:
        now = time.time()
        timeout = float(self.settings.get('working_timeout', 240))
        sessions = []
        for file in self._sessions_dir.glob('*.json'):
            try:
                data = json.loads(file.read_text(encoding='utf-8'))
            except (OSError, ValueError, TypeError):
                continue
            if not isinstance(data, dict):
                continue
            ts = float(data.get('ts', 0) or 0)
            if now - ts > 3600:  # forget long-abandoned sessions
                file.unlink(missing_ok=True)
                continue
            state = str(data.get('state', 'idle'))
            if state not in STATES:
                state = 'idle'
            age = now - ts
            if state == 'working' and age > timeout:
                state = 'idle'  # a session gone silent is no longer busy (stuck guard)
            elif state == 'done' and age > STATES['done']['auto_idle']:
                state = 'idle'  # the green flash has passed
            sessions.append({'id': file.stem, 'state': state,
                             'detail': str(data.get('detail', '')),
                             'project': str(data.get('project', '')), 'ts': ts})
        return sessions

    def _read_sessions(self) -> None:
        sessions = self._load_sessions()

        waiting_now = {s['id'] for s in sessions if s['state'] == 'waiting'}
        if (waiting_now - self._waiting_ids) and self.settings.get('chime', True):
            self._chime()  # a new session just started waiting for you
        self._waiting_ids = waiting_now

        active = [s for s in sessions if s['state'] != 'offline']
        if not active:
            self.set_state('offline')
            return
        winner = max(active, key=lambda s: (PRIORITY[s['state']], s['ts']))
        pieces = [p for p in (winner['project'], winner['detail']) if p]
        text = ' · '.join(pieces)
        others = len(active) - 1
        if others:
            text = (text + ' ' if text else '') + f'(+{others})'
        self.set_state(winner['state'], text)

    # --- painting ------------------------------------------------------------
    def _load_avatar(self) -> QPixmap | None:
        path = ASSETS / 'clawd.png'
        if path.exists():
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                return pixmap
        return None

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0, 0, self.width(), self.height())
        radius = rect.height() / 2

        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        painter.fillPath(path, QColor(18, 20, 24, 235))
        painter.setPen(QColor(255, 255, 255, 22))
        painter.drawPath(path)

        accent = QColor(STATES[self.state]['accent'])
        pad = 8.0
        diameter = rect.height() - pad * 2
        avatar_rect = QRectF(pad, pad, diameter, diameter)

        # Status ring around the avatar; breathes when the state pulses.
        ring = QColor(accent)
        ring.setAlphaF(clamp01(0.4 + 0.6 * self._pulse) if STATES[self.state]['pulse'] else 0.95)
        pen = painter.pen()
        pen.setColor(ring)
        pen.setWidthF(2.4)
        painter.setPen(pen)
        painter.drawEllipse(avatar_rect.adjusted(-2.4, -2.4, 2.4, 2.4))

        # Avatar (circular clip) or a lettered fallback.
        painter.save()
        clip = QPainterPath()
        clip.addEllipse(avatar_rect)
        painter.setClipPath(clip)
        if self.avatar is not None:
            scaled = self.avatar.scaled(int(diameter), int(diameter),
                                        Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            painter.drawPixmap(avatar_rect.topLeft(), scaled)
        else:
            painter.fillRect(avatar_rect, QColor(40, 44, 52))
            painter.setPen(QColor(235, 242, 248))
            painter.setFont(QFont('Segoe UI', int(diameter * 0.45), QFont.Bold))
            painter.drawText(avatar_rect, Qt.AlignCenter, 'C')
        painter.restore()

        # Text appears only as the pill opens.
        text_alpha = clamp01((self._expand - 0.35) / 0.65)
        if text_alpha > 0.01:
            left = avatar_rect.right() + 12
            text_rect = QRectF(left, 0, rect.width() - left - 16, rect.height())
            title = QColor(235, 242, 248)
            title.setAlphaF(text_alpha)
            label_color = QColor(accent)
            label_color.setAlphaF(text_alpha)

            painter.setFont(QFont('Segoe UI', 10, QFont.DemiBold))
            metrics = QFontMetrics(painter.font())
            top = text_rect.center().y() - metrics.height() + 2
            painter.setPen(title)
            painter.drawText(QRectF(text_rect.left(), top, text_rect.width(), metrics.height()),
                             Qt.AlignVCenter | Qt.AlignLeft, 'claude code')

            painter.setFont(QFont('Segoe UI', 9))
            metrics = QFontMetrics(painter.font())
            second = STATES[self.state]['label']
            if self.detail:
                second += ' · ' + self.detail
            second = metrics.elidedText(second, Qt.ElideRight, int(text_rect.width()))
            painter.setPen(label_color)
            painter.drawText(QRectF(text_rect.left(), top + metrics.height(), text_rect.width(), metrics.height()),
                             Qt.AlignVCenter | Qt.AlignLeft, second)
        painter.end()

    # --- interaction ---------------------------------------------------------
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPosition() - QPointF(self.x(), self.y())
            self._press_pos = event.globalPosition()
            self._moved = False
        elif event.button() == Qt.RightButton:
            self._context_menu(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_offset is not None:
            if self._press_pos is not None and (event.globalPosition() - self._press_pos).manhattanLength() > 6:
                self._moved = True
            target = event.globalPosition() - self._drag_offset
            self.move(int(target.x()), int(target.y()))
            self._center_x = self.x() + self.width() / 2

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag_offset is not None and not self._moved:
            # A click (not a drag): jump to the terminal that needs you.
            self._focus_claude()
        elif self._moved:
            self.settings['center_x'] = self._center_x
            save_settings(self.settings)
        self._drag_offset = None
        self._press_pos = None

    def _focus_claude(self) -> bool:
        # 1) exact window the launcher opened; 2) any Windows Terminal window;
        # 3) a title match as a last resort.
        if raise_hwnd(load_terminal_hwnd()):
            return True
        terminals = find_terminals()
        if terminals and raise_hwnd(terminals[0]):
            return True
        return raise_window(str(self.settings.get('focus_title', 'Claude Code')))

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        # Hide to the tray rather than quit; reopen from the tray icon.
        self.toggle_visibility()

    def _context_menu(self, position) -> None:
        menu = QMenu()
        for state in STATES:
            action = QAction('Simulate: ' + STATES[state]['label'], menu)
            action.triggered.connect(lambda _=False, s=state: write_session(s, '', '_sim', 'simulate'))
            menu.addAction(action)
        menu.addSeparator()
        quit_action = QAction('Quit', menu)
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(quit_action)
        menu.exec(position)


def already_running() -> bool:
    probe = QLocalSocket()
    probe.connectToServer(SINGLE_INSTANCE_KEY)
    if probe.waitForConnected(150):
        probe.abort()
        return True
    QLocalServer.removeServer(SINGLE_INSTANCE_KEY)  # clear a stale socket
    server = QLocalServer()
    server.listen(SINGLE_INSTANCE_KEY)
    main._server = server  # keep it alive for the process lifetime
    return False


def main() -> None:
    app = QApplication(sys.argv)
    if already_running():
        print('Claude Island is already running.')
        return
    # The tray icon keeps the app alive while the pill is hidden.
    app.setQuitOnLastWindowClosed(False)
    island = Island()
    island.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
