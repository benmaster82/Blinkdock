"""Called by Claude Code hooks. Translates one lifecycle event into one state.

Usage (from a Claude Code hook command):
    pythonw hook_bridge.py <state>

The matching Claude event JSON arrives on stdin. We use its `session_id` to track
each concurrent session separately and its `cwd` to label the session by project.
Every session writes its own file under the sessions directory, so parallel
sessions never clobber each other; the island aggregates them. Writing is atomic;
`offline` (SessionEnd) deletes the session's file.
"""
from __future__ import annotations
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path

from config import NOTIFICATION_STATES, STATES, sessions_dir


def safe_id(session_id: str) -> str:
    cleaned = re.sub(r'[^A-Za-z0-9._-]', '_', session_id)[:80]
    return cleaned or 'default'


def read_event() -> dict:
    # Claude Code pipes the event payload to the hook on stdin.
    if sys.stdin is None or sys.stdin.isatty():
        return {}
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        event = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return event if isinstance(event, dict) else {}


def detail_for(state: str, event: dict) -> str:
    if state == 'background':
        count = len(event.get('background_tasks') or [])
        return f'{count} task' + ('s' if count != 1 else '')
    if state == 'working':
        tool = event.get('tool_name') or event.get('tool') or ''
        labels = {'Bash': 'running a command', 'Edit': 'editing a file',
                  'Write': 'writing a file', 'Read': 'reading a file',
                  'Grep': 'searching the code', 'Glob': 'finding files',
                  'WebFetch': 'fetching the web', 'Task': 'coordinating a subagent'}
        return labels.get(tool, tool)
    if state == 'waiting':
        return str(event.get('message') or event.get('tool_name') or event.get('mcp_server_name') or '')[:200]
    if state == 'error':
        return str(event.get('error') or event.get('message') or '').replace('_', ' ')[:200]
    return ''


def state_for_event(state: str, event: dict) -> str | None:
    if 'notification_type' in event or event.get('hook_event_name') == 'Notification':
        notification_type = event.get('notification_type')
        return NOTIFICATION_STATES.get(notification_type) if isinstance(notification_type, str) else None
    if state == 'waiting' and event and not event.get('hook_event_name'):
        return None
    if event.get('hook_event_name') == 'PermissionRequest' and event.get('agent_id'):
        return None  # background subagents cannot always present a user prompt
    if event.get('hook_event_name') == 'PostToolUseFailure' and event.get('is_interrupt') is True:
        return 'unknown'
    if state == 'done' and event.get('background_tasks'):
        return 'background'
    return state


def write_session(state: str, detail: str = '', session_id: str = 'default',
                  project: str = '', launch_id: str = '') -> None:
    if state not in STATES:
        state = 'idle'
    path = sessions_dir() / (safe_id(session_id) + '.json')
    if state == 'offline':
        path.unlink(missing_ok=True)  # the session ended: forget it
        return
    data = {'state': state, 'detail': detail[:200],
            'project': project[:60], 'ts': time.time()}
    if re.fullmatch(r'[0-9a-f]{16}', launch_id):
        data['launch_id'] = launch_id
    payload = json.dumps(data, ensure_ascii=False)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(payload, encoding='utf-8')
    temporary.replace(path)


def main() -> None:
    state = sys.argv[1] if len(sys.argv) > 1 else 'idle'
    event = read_event()
    state = state_for_event(state, event)
    if state is None:
        return
    session_id = str(event.get('session_id') or 'default')
    cwd = str(event.get('cwd') or '')
    project = Path(cwd).name if cwd else ''
    launch_id = os.environ.get('CLAUDE_ISLAND_LAUNCH_ID', '')
    if re.fullmatch(r'[0-9a-f]{16}', launch_id):
        write_session(state, detail_for(state, event), session_id, project, launch_id)
    else:
        write_session(state, detail_for(state, event), session_id, project)


if __name__ == '__main__':
    main()
