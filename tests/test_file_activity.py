import json
import os
import sys
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication, QLabel

import file_activity
import file_panel
import hook_bridge


class ActivityStoreTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(__file__).parent
        self.session_id = 'session-' + uuid.uuid4().hex
        self.path_patch = mock.patch.object(file_activity, 'activity_root',
                                            return_value=self.folder)
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)

    def test_activity_is_per_session_and_tracks_latest_tool(self):
        one, two = self.session_id + '-one', self.session_id + '-two'
        self.addCleanup(lambda: file_activity.remove_session(two))
        file_activity.record_file(one, 'C:/work/src/Main.py', 'Edit')
        file_activity.record_file(one, 'c:/work/src/main.py', 'Write')
        file_activity.record_file(two, 'C:/work/src/Main.py', 'Edit')
        self.assertEqual(file_activity.count_files([one]), 1)
        self.assertEqual(file_activity.count_files([one, two]), 1)
        self.assertEqual(file_activity.recent_files(one)[0][1], 'Write')
        file_activity.remove_session(one)
        self.assertEqual(file_activity.count_files([one]), 0)
        self.assertEqual(file_activity.count_files([two]), 1)

    def test_only_successful_direct_edits_are_attributed(self):
        path = self.folder / f'{self.session_id}.json'
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        source = str(self.folder / 'note.md')
        events = [
            ('PreToolUse', 'Edit'),
            ('PostToolUseFailure', 'Edit'),
            ('PreToolUse', 'Write'),
            ('PostToolUse', 'Write'),
            ('PostToolUse', 'Bash'),
        ]
        with mock.patch.object(hook_bridge, 'sessions_dir', return_value=self.folder):
            for name, tool in events:
                event = {'hook_event_name': name, 'session_id': self.session_id,
                         'cwd': str(self.folder), 'tool_name': tool,
                         'tool_input': {'file_path': source}}
                with mock.patch.object(hook_bridge, 'read_event', return_value=event), \
                     mock.patch.object(sys, 'argv', ['hook_bridge.py', 'working']):
                    hook_bridge.main()
                data = json.loads(path.read_text(encoding='utf-8'))
                self.assertEqual(data.get('pending_file', ''),
                                 source if name == 'PreToolUse' and tool in ('Edit', 'Write') else '')
                self.assertEqual(data['cwd'], str(self.folder))
        self.assertEqual(file_activity.count_files([self.session_id]), 1)
        self.assertEqual(file_activity.recent_files(self.session_id)[0][1], 'Write')
        with mock.patch.object(hook_bridge, 'sessions_dir', return_value=self.folder), \
             mock.patch.object(hook_bridge, 'read_event', return_value={
                 'hook_event_name': 'SessionEnd', 'session_id': self.session_id}), \
             mock.patch.object(sys, 'argv', ['hook_bridge.py', 'offline']):
            hook_bridge.main()
        self.assertFalse(path.exists())
        self.assertEqual(file_activity.count_files([self.session_id]), 0)

    def test_invalid_file_paths_are_not_recorded(self):
        self.assertEqual(hook_bridge.safe_id('..'), 'default')
        self.assertEqual(file_activity.count_files(['../invalid']), 0)
        for value in ('relative.md', '', 3, None):
            event = {'tool_name': 'Edit', 'tool_input': {'file_path': value}}
            self.assertEqual(hook_bridge.file_path_for_event(event), '')
        self.assertEqual(hook_bridge.file_path_for_event({'tool_name': 'Bash',
                          'tool_input': {'file_path': 'C:/work/file.py'}}), '')

    def test_parallel_session_writes_do_not_overwrite_each_other(self):
        sessions = [f'{self.session_id}-{index}' for index in range(8)]
        self.addCleanup(lambda: [file_activity.remove_session(value) for value in sessions])

        def record(index):
            file_activity.record_file(sessions[index], f'C:/work/file-{index}.py', 'Edit')

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(record, range(8)))
        self.assertEqual(file_activity.count_files(sessions), 8)

    def test_parallel_edits_to_one_file_leave_one_valid_record(self):
        self.addCleanup(lambda: file_activity.remove_session(self.session_id))
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: file_activity.record_file(
                self.session_id, 'C:/work/shared.py', 'Edit'), range(8)))
        self.assertEqual(file_activity.count_files([self.session_id]), 1)
        self.assertEqual(file_activity.recent_files(self.session_id)[0][0],
                         'C:/work/shared.py')

    def test_similar_session_ids_do_not_share_or_delete_activity(self):
        first = self.session_id
        second = self.session_id + '-child'
        self.addCleanup(lambda: file_activity.remove_session(first))
        self.addCleanup(lambda: file_activity.remove_session(second))
        file_activity.record_file(first, 'C:/work/one.py', 'Edit')
        file_activity.record_file(second, 'C:/work/two.py', 'Write')
        self.assertEqual(file_activity.count_files([first]), 1)
        self.assertEqual(file_activity.recent_files(first)[0][0], 'C:/work/one.py')
        file_activity.remove_session(first)
        self.assertEqual(file_activity.count_files([second]), 1)
        self.assertEqual(file_activity.recent_files(second)[0][0], 'C:/work/two.py')


class FilePanelTests(unittest.TestCase):
    def test_porcelain_parser_handles_renames_and_untracked_files(self):
        payload = (b' M src/main.py\0?? notes/today.md\0R  new name.py\0old name.py\0'
                   b'A  src/new.py\0')
        self.assertEqual(file_panel.parse_git_status(payload), [
            (' M', 'src/main.py', ''),
            ('??', 'notes/today.md', ''),
            ('R ', 'new name.py', 'old name.py'),
            ('A ', 'src/new.py', ''),
        ])

    def test_panel_shows_session_and_project_sections(self):
        app = QApplication.instance() or QApplication([])
        sessions = [{'id': 'session-one', 'project': 'repo', 'cwd': '',
                     'state': 'working', 'pending_file': 'C:/repo/current.py'}]
        with mock.patch.object(file_panel, 'recent_files', return_value=[
                 ('C:/repo/changed.py', 'Edit', 1000.0)]), \
             mock.patch.object(file_panel, 'count_files', return_value=1), \
             mock.patch.object(file_panel.time, 'time', return_value=1001.0):
            panel = file_panel.FilePanel(lambda: sessions, None)
            try:
                panel.refresh()
                app.processEvents()
                text = [label.text() for label in panel.findChildren(QLabel)]
                self.assertIn('SESSION ACTIVITY  1', text)
                self.assertIn('PROJECT GIT STATUS  (SHARED)', text)
                self.assertTrue(any(value.endswith('current.py') for value in text))
                self.assertTrue(any(value.endswith('changed.py') for value in text))
            finally:
                panel.close()

    def test_git_status_runs_outside_the_hook(self):
        app = QApplication.instance() or QApplication([])
        sessions = [{'id': 'session-one', 'project': 'repo',
                     'cwd': str(Path(__file__).parent.parent), 'state': 'working'}]
        with mock.patch.object(file_panel, 'recent_files', return_value=[]), \
             mock.patch.object(file_panel, 'count_files', return_value=0), \
             mock.patch.object(file_panel, 'QProcess') as process_type:
            panel = file_panel.FilePanel(lambda: sessions, None)
            try:
                panel.refresh()
                process = process_type.return_value
                process.setWorkingDirectory.assert_called_once_with(sessions[0]['cwd'])
                process.start.assert_called_once_with('git', [
                    '--no-optional-locks', 'status', '--porcelain=v1', '-z',
                    '--untracked-files=normal'])
                process.readAllStandardOutput.return_value = b' M src/main.py\0'
                panel._git_finished(process, panel._git_generation, 0)
                self.assertEqual(panel._git_entries, [(' M', 'src/main.py', '')])
                app.processEvents()
            finally:
                panel.close()


if __name__ == '__main__':
    unittest.main()
