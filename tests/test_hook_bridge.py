import json
import os
import sys
import unittest
import uuid
from pathlib import Path
from unittest import mock

import hook_bridge
from config import ACTIONABLE_NOTIFICATIONS


class NotificationTests(unittest.TestCase):
    def run_notification(self, event):
        with mock.patch.object(sys, 'argv', ['hook_bridge.py', 'waiting']), \
             mock.patch.object(hook_bridge, 'read_event', return_value=event), \
             mock.patch.object(hook_bridge, 'write_session') as write:
            hook_bridge.main()
        return write

    def test_actionable_notifications_set_waiting(self):
        for notification_type in ACTIONABLE_NOTIFICATIONS:
            with self.subTest(notification_type=notification_type):
                event = {'session_id': 'session-1', 'cwd': 'C:/work/project',
                         'notification_type': notification_type, 'message': 'Action needed'}
                self.run_notification(event).assert_called_once_with(
                    'waiting', 'Action needed', 'session-1', 'project',
                    cwd='C:/work/project', pending_file='')

    def test_informational_and_unknown_notifications_are_ignored(self):
        for notification_type in ('idle_prompt', 'auth_success', 'agent_completed', 'unknown'):
            with self.subTest(notification_type=notification_type):
                self.run_notification({'session_id': 'session-1',
                                       'notification_type': notification_type}).assert_not_called()
        self.run_notification({'session_id': 'session-1'}).assert_not_called()

    def test_missing_stdin_uses_installed_matcher(self):
        self.run_notification({}).assert_called_once_with(
            'waiting', '', 'default', '', cwd='', pending_file='')

    def test_recovery_and_failure_notifications(self):
        for notification_type, state in (
            ('elicitation_complete', 'working'),
            ('elicitation_response', 'working'),
            ('quota_auto_resume_fired', 'working'),
            ('quota_auto_resume_disabled', 'error'),
        ):
            with self.subTest(notification_type=notification_type):
                event = {'session_id': 'session-1', 'notification_type': notification_type}
                self.run_notification(event).assert_called_once_with(
                    state, '', 'session-1', '', cwd='', pending_file='')

    def test_permission_request_and_background_stop(self):
        self.assertEqual(hook_bridge.state_for_event('waiting', {
            'hook_event_name': 'PermissionRequest', 'tool_name': 'Bash'}), 'waiting')
        self.assertIsNone(hook_bridge.state_for_event('waiting', {
            'hook_event_name': 'PermissionRequest', 'agent_id': 'subagent-1'}))
        event = {'hook_event_name': 'Stop', 'background_tasks': [{'id': 'task-1'}]}
        self.assertEqual(hook_bridge.state_for_event('done', event), 'background')
        self.assertEqual(hook_bridge.detail_for('background', event), '1 task')
        self.assertEqual(hook_bridge.state_for_event('done', {'hook_event_name': 'Stop'}), 'done')

    def test_interrupted_tool_does_not_claim_work_is_continuing(self):
        event = {'hook_event_name': 'PostToolUseFailure', 'is_interrupt': True}
        self.assertEqual(hook_bridge.state_for_event('working', event), 'unknown')

    def test_error_detail_uses_structured_code(self):
        self.assertEqual(hook_bridge.detail_for('error', {
            'hook_event_name': 'StopFailure', 'error': 'rate_limit'}), 'rate limit')


class LifecycleTests(unittest.TestCase):
    def test_launcher_id_is_attached_only_when_valid(self):
        event = {'hook_event_name': 'SessionStart', 'session_id': 'launched',
                 'cwd': 'C:/work/project'}
        session_id = 'launch-' + uuid.uuid4().hex
        event['session_id'] = session_id
        path = Path(__file__).parent / f'{session_id}.json'
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        with mock.patch.object(hook_bridge, 'sessions_dir', return_value=path.parent), \
             mock.patch.object(hook_bridge, 'read_event', return_value=event), \
             mock.patch.object(sys, 'argv', ['hook_bridge.py', 'idle']):
            with mock.patch.dict(os.environ, {'CLAUDE_ISLAND_LAUNCH_ID': 'a1b2c3d4e5f60708'}):
                hook_bridge.main()
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['launch_id'],
                             'a1b2c3d4e5f60708')
            with mock.patch.dict(os.environ, {'CLAUDE_ISLAND_LAUNCH_ID': '../wrong'}):
                hook_bridge.main()
            self.assertNotIn('launch_id', json.loads(path.read_text(encoding='utf-8')))

    def test_session_transitions_and_end(self):
        session_id = 'test-' + uuid.uuid4().hex
        path = Path(__file__).parent / f'{session_id}.json'
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        events = (
            ('SessionStart', 'idle', 'idle'),
            ('UserPromptSubmit', 'working', 'working'),
            ('PreToolUse', 'working', 'working'),
            ('PermissionRequest', 'waiting', 'waiting'),
            ('PostToolUse', 'working', 'working'),
            ('Elicitation', 'waiting', 'waiting'),
            ('ElicitationResult', 'working', 'working'),
            ('PostToolUseFailure', 'working', 'working'),
            ('StopFailure', 'error', 'error'),
            ('UserPromptSubmit', 'working', 'working'),
            ('Stop', 'done', 'done'),
        )
        with mock.patch.object(hook_bridge, 'sessions_dir', return_value=path.parent):
            for name, requested, expected in events:
                with self.subTest(event=name):
                    event = {'hook_event_name': name, 'session_id': session_id,
                             'cwd': 'C:/work/project'}
                    if name == 'StopFailure':
                        event['error'] = 'rate_limit'
                    with mock.patch.object(sys, 'argv', ['hook_bridge.py', requested]), \
                         mock.patch.object(hook_bridge, 'read_event', return_value=event):
                        hook_bridge.main()
                    data = json.loads(path.read_text(encoding='utf-8'))
                    self.assertEqual(data['state'], expected)
                    self.assertEqual(data['project'], 'project')

            unchanged = path.read_text(encoding='utf-8')
            notification = {'hook_event_name': 'Notification', 'session_id': session_id,
                            'notification_type': 'idle_prompt'}
            with mock.patch.object(sys, 'argv', ['hook_bridge.py', 'waiting']), \
                 mock.patch.object(hook_bridge, 'read_event', return_value=notification):
                hook_bridge.main()
            self.assertEqual(path.read_text(encoding='utf-8'), unchanged)

            with mock.patch.object(sys, 'argv', ['hook_bridge.py', 'offline']), \
                 mock.patch.object(hook_bridge, 'read_event', return_value={
                     'hook_event_name': 'SessionEnd', 'session_id': session_id}):
                hook_bridge.main()
            self.assertFalse(path.exists())


if __name__ == '__main__':
    unittest.main()
