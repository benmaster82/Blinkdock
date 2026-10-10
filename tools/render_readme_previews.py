"""Capture README previews from the real widgets without using live session data."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['QT_SCALE_FACTOR'] = '2'
os.environ['QT_QPA_FONTDIR'] = str(Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts')
RUNTIME = Path(tempfile.mkdtemp(prefix='blinkdock-previews-'))
os.environ['LOCALAPPDATA'] = str(RUNTIME)

try:
    from PySide6.QtWidgets import QApplication

    from file_activity import record_file
    from island import Island

    app = QApplication([])
    island = Island()
    island._poll.stop()
    island._file_poll.stop()
    island._session_count = 2
    island._file_count = 3

    output = ROOT / 'docs' / 'images'
    output.mkdir(parents=True, exist_ok=True)

    def capture(widget, name: str) -> None:
        widget.show()
        app.processEvents()
        image = widget.grab()
        if image.isNull() or not image.save(str(output / name)):
            raise RuntimeError(f'Could not capture {name}')

    island._session_count = 1
    island._file_count = 0
    island.set_state('idle', animate=False)
    capture(island, 'widget-listening.png')

    island._session_count = 2
    island._file_count = 3
    island.set_state('working', 'editor - running tests', animate=False)
    capture(island, 'widget-working.png')
    island.set_state('waiting', 'editor - permission needed', animate=False)
    capture(island, 'widget-waiting.png')
    island.set_state('done', 'editor - turn complete', animate=False)
    capture(island, 'widget-done.png')

    cwd = str(ROOT)
    island._sessions_snapshot = [
        {'id': 'preview-editor', 'project': 'editor', 'state': 'waiting',
         'detail': 'permission needed', 'ts': time.time(),
         'cwd': cwd, 'pending_file': '', 'launch_id': ''},
        {'id': 'preview-api', 'project': 'api', 'state': 'working',
         'detail': 'editing files', 'ts': time.time(),
         'cwd': cwd, 'pending_file': '', 'launch_id': ''},
    ]
    record_file('preview-editor', str(ROOT / 'island.py'), 'Edit')
    record_file('preview-editor', str(ROOT / 'file_panel.py'), 'Edit')
    record_file('preview-editor', str(ROOT / 'README.md'), 'Write')

    island._show_files_panel()
    panel = island._files_panel
    if panel is None:
        raise RuntimeError('File panel did not open')
    panel._stop_git()
    panel._git_session = 'preview-editor'
    panel._git_entries = [(' M', 'README.md', ''), ('??', 'docs/images/widget-listening.png', '')]
    panel._refresh_activity()
    capture(panel, 'file-activity.png')
    panel.hide()

    island._show_sessions_menu()
    menu = island._sessions_menu
    if menu is None:
        raise RuntimeError('Sessions menu did not open')
    capture(menu, 'sessions.png')
    menu.close()
    island.close()
    app.quit()
finally:
    if RUNTIME.resolve().parent != Path(tempfile.gettempdir()).resolve():
        raise RuntimeError('Preview data path escaped the temporary directory')
    shutil.rmtree(RUNTIME)
