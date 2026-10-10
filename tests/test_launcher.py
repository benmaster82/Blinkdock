import os
import sys
import unittest
from pathlib import Path
from unittest import mock

import launch_claude
import winfocus


LAUNCH_ID = 'a1b2c3d4e5f60708'


class FocusTests(unittest.TestCase):
    def test_terminal_title_requires_a_valid_launch_id(self):
        self.assertEqual(winfocus.terminal_title(LAUNCH_ID),
                         f'Claude Code [{LAUNCH_ID}]')
        with self.assertRaises(ValueError):
            winfocus.terminal_title('../wrong')

    def test_session_terminal_must_be_unique_and_a_windows_terminal(self):
        windows = [(10, winfocus.TERMINAL_CLASS, f'Claude Code [{LAUNCH_ID}]'),
                   (11, 'CabinetWClass', f'Claude Code [{LAUNCH_ID}]'),
                   (12, winfocus.TERMINAL_CLASS, 'another session')]

        def enumerate_matching(predicate):
            return [hwnd for hwnd, cls, title in windows if predicate(hwnd, cls, title)]

        with mock.patch.object(winfocus, '_enumerate', side_effect=enumerate_matching):
            self.assertEqual(winfocus.find_session_terminal(LAUNCH_ID), 10)
            windows.append((13, winfocus.TERMINAL_CLASS,
                            f'Claude Code [{LAUNCH_ID}] duplicate'))
            self.assertIsNone(winfocus.find_session_terminal(LAUNCH_ID))
            self.assertIsNone(winfocus.find_session_terminal('../wrong'))


class LauncherTests(unittest.TestCase):
    def test_child_passes_launch_id_to_claude(self):
        with mock.patch.object(launch_claude, 'find_claude', return_value=['claude.exe']), \
             mock.patch.object(launch_claude.subprocess, 'call', return_value=0) as call:
            result = launch_claude._run_child(LAUNCH_ID, Path('C:/work'))
        self.assertEqual(result, 0)
        self.assertEqual(call.call_args.args[0], ['claude.exe'])
        self.assertEqual(call.call_args.kwargs['env']['CLAUDE_ISLAND_LAUNCH_ID'], LAUNCH_ID)
        self.assertEqual(call.call_args.kwargs['cwd'], 'C:\\work')
        self.assertNotIn('CLAUDE_ISLAND_LAUNCH_ID', os.environ)

    def test_launcher_opens_a_named_window_and_records_only_its_match(self):
        workdir = Path(__file__).parent.resolve()
        with mock.patch.object(sys, 'argv', ['launch_claude.py', str(workdir)]), \
             mock.patch.object(launch_claude, 'find_claude', return_value=['claude.exe']), \
             mock.patch.object(launch_claude.shutil, 'which', return_value='wt.exe'), \
             mock.patch.object(launch_claude.secrets, 'token_hex', return_value=LAUNCH_ID), \
             mock.patch.object(launch_claude.subprocess, 'Popen') as popen, \
             mock.patch.object(launch_claude, 'find_session_terminal', return_value=42), \
             mock.patch.object(launch_claude, 'record_terminal_hwnd') as record, \
             mock.patch.object(launch_claude.time, 'sleep'):
            self.assertEqual(launch_claude.main(), 0)
        argv = popen.call_args.args[0]
        self.assertEqual(argv[:4], ['wt.exe', '-w', 'new', 'new-tab'])
        self.assertEqual(argv[argv.index('--title') + 1],
                         f'Claude Code [{LAUNCH_ID}]')
        self.assertIn('--suppressApplicationTitle', argv)
        self.assertEqual(argv[argv.index('--child') + 1], LAUNCH_ID)
        record.assert_called_once_with(42)


if __name__ == '__main__':
    unittest.main()
