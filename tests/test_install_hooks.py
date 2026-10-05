import json
import tempfile
import unittest
from pathlib import Path

import install_hooks
from config import ACTIONABLE_NOTIFICATIONS


class InstallHooksTests(unittest.TestCase):
    def setUp(self):
        with tempfile.NamedTemporaryFile(dir=Path(__file__).parent, suffix='.json',
                                         delete=False) as stream:
            self.target = Path(stream.name)
        self.target.unlink()
        self.addCleanup(lambda: self.target.unlink(missing_ok=True))
        self.addCleanup(lambda: self.target.with_suffix('.json.bak').unlink(missing_ok=True))

    def test_merge_and_remove_preserve_other_hooks(self):
        other = {'type': 'command', 'command': 'other-tool.exe'}
        similarly_named = {'type': 'command', 'command': 'python "C:\\other\\hook_bridge.py" idle'}
        original = {
            'model': 'test-model',
            'hooks': {
                'PreToolUse': [
                    {'matcher': '*', 'hooks': [other, {'type': 'command',
                     'command': install_hooks.command('working')}]},
                    {'hooks': [similarly_named]},
                    {'hooks': []},
                ],
                'PostToolUse': [{'hooks': [other]}],
                'Notification': [
                    {'hooks': [{'type': 'command', 'command': install_hooks.command('waiting')}]},
                    {'hooks': [other]},
                ],
            },
        }
        original_text = json.dumps(original)
        self.target.write_text(original_text, encoding='utf-8')

        install_hooks.merge(self.target)
        self.assertEqual(self.target.with_suffix('.json.bak').read_text(encoding='utf-8'), original_text)
        installed = json.loads(self.target.read_text(encoding='utf-8'))
        self.assertEqual(installed['model'], 'test-model')
        self.assertEqual(installed['hooks']['PostToolUse'][0], original['hooks']['PostToolUse'][0])
        self.assertEqual(installed['hooks']['Notification'][0], original['hooks']['Notification'][1])
        self.assertEqual(installed['hooks']['Notification'][1]['matcher'],
                         '|'.join(ACTIONABLE_NOTIFICATIONS))
        self.assertEqual(installed['hooks']['PreToolUse'][:3], [
            {'matcher': '*', 'hooks': [other]}, {'hooks': [similarly_named]}, {'hooks': []},
        ])

        install_hooks.merge(self.target)
        installed_again = json.loads(self.target.read_text(encoding='utf-8'))
        for event in install_hooks.hooks_block():
            self.assertEqual(installed_again['hooks'][event], installed['hooks'][event])

        install_hooks.remove(self.target)
        cleaned = json.loads(self.target.read_text(encoding='utf-8'))
        self.assertEqual(cleaned, {
            'model': 'test-model',
            'hooks': {
                'PreToolUse': [
                    {'matcher': '*', 'hooks': [other]},
                    {'hooks': [similarly_named]},
                    {'hooks': []},
                ],
                'PostToolUse': [{'hooks': [other]}],
                'Notification': [{'hooks': [other]}],
            },
        })

    def test_invalid_settings_are_not_overwritten(self):
        for text in ('{broken', '[]', '{"hooks": []}', '{"hooks": {"Stop": {}}}'):
            with self.subTest(text=text):
                self.target.write_text(text, encoding='utf-8')
                with self.assertRaises(ValueError):
                    install_hooks.merge(self.target)
                self.assertEqual(self.target.read_text(encoding='utf-8'), text)
                with self.assertRaises(ValueError):
                    install_hooks.remove(self.target)
                self.assertEqual(self.target.read_text(encoding='utf-8'), text)
                self.assertFalse(self.target.with_suffix('.json.bak').exists())

    def test_merge_creates_settings_when_missing(self):
        install_hooks.merge(self.target)
        settings = json.loads(self.target.read_text(encoding='utf-8'))
        self.assertEqual(set(settings['hooks']), set(install_hooks.EVENTS) | {'Notification'})
        self.assertFalse(self.target.with_suffix('.json.bak').exists())

    def test_notification_matcher_selects_actionable_types(self):
        hooks = install_hooks.hooks_block()
        self.assertEqual(hooks['Notification'][0]['matcher'], '|'.join(ACTIONABLE_NOTIFICATIONS))
        self.assertEqual(hooks['PostToolUse'][0]['hooks'][0]['command'],
                         install_hooks.command('working'))
        self.assertEqual(hooks['PermissionRequest'][0]['hooks'][0]['command'],
                         install_hooks.command('waiting'))
        self.assertEqual(hooks['StopFailure'][0]['hooks'][0]['command'],
                         install_hooks.command('error'))
        self.assertEqual(hooks['Notification'][1]['matcher'],
                         'elicitation_complete|elicitation_response|quota_auto_resume_fired')
        self.assertEqual(hooks['Notification'][2]['matcher'], 'quota_auto_resume_disabled')


if __name__ == '__main__':
    unittest.main()
