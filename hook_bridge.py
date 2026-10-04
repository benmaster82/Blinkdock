"""Called by Claude Code hooks. Translates one lifecycle event into one state.

Usage (from a Claude Code hook command):
    python hook_bridge.py <state> [detail]

The matching Claude event JSON is read from stdin when present; for PreToolUse
we pull the tool name out of it to show what Claude is doing. Writing is atomic
so the island never reads a half-written file.
"""
from __future__ import annotations
import json
import sys
import time
import uuid
from pathlib import Path

from config import STATES, status_path


def write_status(state: str, detail: str = '') -> Path:
    if state not in STATES:
        state = 'idle'
    path = status_path()
    payload = json.dumps({'state': state, 'detail': detail[:200], 'ts': time.time()},
                         ensure_ascii=False)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(payload, encoding='utf-8')
    temporary.replace(path)
    return path


def detail_from_event(state: str) -> str:
    # Claude Code passes the event payload on stdin; use it to enrich 'working'.
    if sys.stdin is None or sys.stdin.isatty():
        return ''
    raw = sys.stdin.read()
    if not raw.strip():
        return ''
    try:
        event = json.loads(raw)
    except (ValueError, TypeError):
        return ''
    if not isinstance(event, dict):
        return ''
    if state == 'working':
        tool = event.get('tool_name') or event.get('tool') or ''
        labels = {'Bash': 'running a command', 'Edit': 'editing a file',
                  'Write': 'writing a file', 'Read': 'reading a file',
                  'Grep': 'searching the code', 'Glob': 'finding files',
                  'WebFetch': 'fetching the web', 'Task': 'coordinating a subagent'}
        return labels.get(tool, tool)
    if state in ('waiting', 'error'):
        return str(event.get('message', ''))[:200]
    return ''


def main() -> None:
    state = sys.argv[1] if len(sys.argv) > 1 else 'idle'
    detail = sys.argv[2] if len(sys.argv) > 2 else detail_from_event(state)
    write_status(state, detail)


if __name__ == '__main__':
    main()
