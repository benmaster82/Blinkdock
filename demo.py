"""Drive the island through its states without Claude, to tune look and motion.

Run `python island.py` in one terminal and `python demo.py` in another.
"""
from __future__ import annotations
import time

from hook_bridge import write_status

SEQUENCE = [
    ('idle', '', 2.5),
    ('working', 'reading a file', 2.0),
    ('working', 'running a command', 2.5),
    ('waiting', 'May I run npm test?', 4.0),
    ('working', 'editing a file', 2.5),
    ('done', '', 3.0),
    ('idle', '', 2.5),
    ('working', 'searching the code', 2.0),
    ('error', 'Command interrupted', 3.5),
]


def main() -> None:
    print('Demo running. Ctrl+C to stop.')
    try:
        while True:
            for state, detail, hold in SEQUENCE:
                write_status(state, detail)
                print(f'  {state:8} {detail}')
                time.sleep(hold)
    except KeyboardInterrupt:
        write_status('offline')
        print('\nDemo stopped.')


if __name__ == '__main__':
    main()
