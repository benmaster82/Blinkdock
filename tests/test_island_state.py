import json
import os
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication, QLabel

import island
from config import DEFAULT_SETTINGS, STATES
from island import PRIORITY, effective_state


class StateTests(unittest.TestCase):
    def test_every_state_has_an_aggregation_priority(self):
        self.assertEqual(set(PRIORITY), set(STATES))
        self.assertGreater(PRIORITY['waiting'], PRIORITY['error'])
        self.assertGreater(PRIORITY['working'], PRIORITY['done'])

    def test_silent_activity_becomes_unknown(self):
        self.assertEqual(effective_state('working', 240, 240), 'working')
        self.assertEqual(effective_state('working', 241, 240), 'unknown')
        self.assertEqual(effective_state('waiting', 3599, 240), 'waiting')
        self.assertEqual(effective_state('waiting', 3601, 240), 'unknown')
        self.assertEqual(effective_state('background', 3601, 240), 'unknown')
        self.assertEqual(effective_state('error', 3601, 240), 'unknown')
        self.assertEqual(effective_state('idle', 3601, 240), 'unknown')

    def test_done_flash_returns_to_idle(self):
        self.assertEqual(effective_state('done', 2, 240), 'done')
        self.assertEqual(effective_state('done', 4, 240), 'idle')
        self.assertEqual(effective_state('done', 3601, 240), 'unknown')

    def test_inactive_sessions_remain_unknown_until_explicitly_forgotten(self):
        paths = []
        for timestamp in (10000 - 3601, 10000 - 10):
            with tempfile.NamedTemporaryFile(dir=Path(__file__).parent, suffix='.json',
                                             delete=False) as stream:
                path = Path(stream.name)
            self.addCleanup(lambda file=path: file.unlink(missing_ok=True))
            path.write_text(json.dumps({'state': 'idle', 'ts': timestamp}), encoding='utf-8')
            paths.append(path)

        widget = SimpleNamespace(_sessions_dir=Path(__file__).parent,
                                 settings={'working_timeout': 240},
                                 _read_sessions=mock.Mock(),
                                 _read_file_count=mock.Mock())
        with mock.patch.object(island.time, 'time', return_value=10000):
            sessions = island.Island._load_sessions(widget)
            self.assertEqual({s['state'] for s in sessions}, {'unknown', 'idle'})
            self.assertTrue(paths[0].exists())
            with mock.patch.object(island, 'remove_session') as remove:
                island.Island.forget_inactive_sessions(widget)
            remove.assert_called_once_with(paths[0].stem)
        self.assertFalse(paths[0].exists())
        self.assertTrue(paths[1].exists())
        widget._read_sessions.assert_called_once()
        widget._read_file_count.assert_called_once()

    def test_waiting_session_wins_without_repeated_chimes(self):
        paths = []
        for state, timestamp in (('working', 9998), ('waiting', 9999)):
            with tempfile.NamedTemporaryFile(dir=Path(__file__).parent, suffix='.json',
                                             delete=False) as stream:
                path = Path(stream.name)
            self.addCleanup(lambda file=path: file.unlink(missing_ok=True))
            path.write_text(json.dumps({'state': state, 'ts': timestamp,
                                        'project': 'repo', 'detail': 'approval' if state == 'waiting' else ''}),
                            encoding='utf-8')
            paths.append(path)

        widget = SimpleNamespace(_sessions_dir=Path(__file__).parent,
                                 settings={'working_timeout': 'invalid', 'chime': True},
                                 _waiting_ids=set(), _file_count=0, set_state=mock.Mock(),
                                 setToolTip=mock.Mock(), _chime=mock.Mock())
        widget._load_sessions = lambda: island.Island._load_sessions(widget)
        with mock.patch.object(island.time, 'time', return_value=10000):
            island.Island._read_sessions(widget)
            island.Island._read_sessions(widget)
        widget.set_state.assert_called_with('waiting', 'repo · approval')
        self.assertEqual(widget._session_count, 2)
        self.assertEqual([s['state'] for s in widget._sessions_snapshot],
                         ['waiting', 'working'])
        self.assertIn('2 sessions tracked', widget.setToolTip.call_args.args[0])
        widget._chime.assert_called_once()

    def test_unknown_session_is_counted_but_not_presented_as_confirmed_active(self):
        widget = SimpleNamespace(settings={'chime': False}, _waiting_ids=set(),
                                 _file_count=0,
                                 _load_sessions=lambda: [
                                     {'id': 'old', 'state': 'unknown', 'ts': 10,
                                      'project': 'repo', 'detail': ''}],
                                 set_state=mock.Mock(), setToolTip=mock.Mock())
        island.Island._read_sessions(widget)
        self.assertEqual(widget._session_count, 1)
        self.assertIn('status unknown', widget.setToolTip.call_args.args[0])
        widget.set_state.assert_called_once_with('unknown', 'repo')

    def test_badge_and_session_overview(self):
        app = QApplication.instance() or QApplication([])
        with mock.patch.object(island, 'sessions_dir', return_value=Path(__file__).parent), \
             mock.patch.object(island, 'load_settings', return_value=dict(DEFAULT_SETTINGS)):
            widget = island.Island()
        try:
            widget._poll.stop()
            token = 'a1b2c3d4e5f60708'
            widget._sessions_snapshot = [
                {'id': 'abcdef1234', 'state': 'waiting', 'project': 'repo',
                 'detail': 'approval', 'ts': time.time(), 'launch_id': token},
                {'id': '9876543210', 'state': 'unknown', 'project': 'repo',
                 'detail': '', 'ts': time.time() - 3700, 'launch_id': ''},
            ]
            widget._session_count = 2
            widget._file_count = 5
            widget.set_state('waiting', 'repo · approval', animate=False)
            widget.show()
            app.processEvents()
            self.assertLessEqual(widget._badge_rect().right(), widget.width())
            self.assertLess(widget._file_badge_rect().right(), widget._badge_rect().left())
            with mock.patch.object(island, 'count_files', return_value=7):
                widget._read_file_count()
            self.assertEqual(widget._file_count, 7)
            with mock.patch.object(island, 'find_session_terminal',
                                   side_effect=lambda value: 42 if value == token else None):
                widget._show_sessions_menu()
            app.processEvents()
            menu = widget._sessions_menu
            self.assertIsNotNone(menu)
            self.assertIn('2 sessions tracked · 1 unknown',
                          menu.actions()[0].defaultWidget().toolTip())
            rows = [action.defaultWidget() for action in menu.actions()[2:]]
            self.assertEqual(len(rows), 2)
            self.assertTrue(any(label.text() == 'abcdef12'
                                for label in rows[0].findChildren(QLabel)))
            self.assertTrue(any(label.text() == '98765432'
                                for label in rows[1].findChildren(QLabel)))
            self.assertIsInstance(rows[0], island.SessionRow)
            self.assertNotIsInstance(rows[1], island.SessionRow)
            with mock.patch.object(island, 'raise_session_terminal', return_value=True) as focus:
                rows[0].clicked.emit(token)
            focus.assert_called_once_with(token)
            menu.close()
            widget._drag_offset = QPointF(0, 0)
            widget._moved = False
            with mock.patch.object(widget, '_show_sessions_menu') as show, \
                 mock.patch.object(widget, '_focus_claude') as generic:
                widget.mouseReleaseEvent(SimpleNamespace(position=lambda: QPointF(75, 26)))
            show.assert_called_once()
            generic.assert_not_called()
            widget._drag_offset = QPointF(0, 0)
            with mock.patch.object(widget, '_show_files_panel') as show_files:
                widget.mouseReleaseEvent(SimpleNamespace(
                    position=lambda: widget._file_badge_rect().center()))
            show_files.assert_called_once()
        finally:
            widget.close()

    def test_single_instance_lock(self):
        settings = Path(__file__).parent / f'test-{uuid.uuid4().hex}.json'
        lock_path = settings.with_suffix('.lock')
        self.addCleanup(lambda: lock_path.unlink(missing_ok=True))
        with mock.patch.object(island, 'settings_path', return_value=settings):
            self.assertFalse(island.already_running())
            self.assertTrue(island.already_running())
            island.main._lock.unlock()
            del island.main._lock
            self.assertFalse(island.already_running())
            island.main._lock.unlock()
            del island.main._lock


if __name__ == '__main__':
    unittest.main()
