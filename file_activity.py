"""Atomic per-session records of files touched by successful file tools."""
from __future__ import annotations

import json
import math
import os
import re
import time
import uuid
from pathlib import Path

from config import sessions_dir


def activity_root() -> Path:
    return sessions_dir().parent


def _session_key(session_id: str) -> str:
    if not re.fullmatch(r'[A-Za-z0-9._-]{1,80}', session_id) or session_id in ('.', '..'):
        raise ValueError('invalid session id')
    return uuid.uuid5(uuid.NAMESPACE_URL, session_id).hex


def _session_files(session_id: str):
    return activity_root().glob(f'activity-{_session_key(session_id)}-*.json')


def record_file(session_id: str, path: str, tool_name: str) -> None:
    session_key = _session_key(session_id)
    key = uuid.uuid5(uuid.NAMESPACE_URL, os.path.normcase(os.path.normpath(path))).hex
    destination = activity_root() / f'activity-{session_key}-{key}.json'
    temporary = destination.with_name(destination.name + f'.{uuid.uuid4().hex}.tmp')
    payload = json.dumps({'path': path, 'tool_name': tool_name,
                          'touched_at': time.time()}, ensure_ascii=False)
    temporary.write_text(payload, encoding='utf-8')
    for attempt in range(3):
        try:
            temporary.replace(destination)
            return
        except PermissionError:
            if attempt == 2:
                temporary.unlink(missing_ok=True)
                raise
            time.sleep(0.002)
        except OSError:
            temporary.unlink(missing_ok=True)
            raise


def recent_files(session_id: str, limit: int = 100) -> list[tuple[str, str, float]]:
    entries = []
    try:
        files = list(_session_files(session_id))
    except (OSError, ValueError):
        return []
    for file in files:
        try:
            data = json.loads(file.read_text(encoding='utf-8'))
            path = data['path']
            tool_name = data['tool_name']
            timestamp = float(data['touched_at'])
            if isinstance(path, str) and tool_name in ('Edit', 'Write') and math.isfinite(timestamp):
                entries.append((path, tool_name, timestamp))
        except (OSError, ValueError, TypeError, KeyError):
            continue
    return sorted(entries, key=lambda item: item[2], reverse=True)[:limit]


def count_files(session_ids: list[str]) -> int:
    keys = set()
    for session_id in session_ids:
        try:
            keys.update(file.stem[-32:] for file in _session_files(session_id))
        except (OSError, ValueError):
            continue
    return len(keys)


def remove_session(session_id: str) -> None:
    for file in _session_files(session_id):
        file.unlink(missing_ok=True)
