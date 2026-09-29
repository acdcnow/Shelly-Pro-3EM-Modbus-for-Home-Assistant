"""Install the Unix module shims that the Home Assistant test harness needs.

Home Assistant and ``pytest-homeassistant-custom-component`` only support Linux
and macOS.  ``homeassistant.runner`` imports the Unix only modules ``fcntl`` and
``resource`` at module level, so importing the test harness fails on Windows with
``ModuleNotFoundError``.

This script writes minimal shims for both modules into the ``site-packages`` of
the active virtual environment.  They are no-ops, the tests still talk to the
simulated device over a real TCP connection.  Run it once on Windows only:

    python scripts/setup_windows_test_env.py
"""

from __future__ import annotations

import site
import sys
from pathlib import Path

FCNTL_SHIM = '''"""Minimal shim for the Unix only fcntl module (test environment only)."""

LOCK_SH = 1
LOCK_EX = 2
LOCK_NB = 4
LOCK_UN = 8


def flock(fd, operation):
    """Pretend to acquire a file lock."""
    return None
'''

RESOURCE_SHIM = '''"""Minimal shim for the Unix only resource module (test environment only)."""

RLIMIT_NOFILE = 7
RLIM_INFINITY = -1

_REPORTED_SOFT_LIMIT = 65536


def getrlimit(resource_id):
    """Return a soft and hard limit that does not need to be changed."""
    return (_REPORTED_SOFT_LIMIT, _REPORTED_SOFT_LIMIT)


def setrlimit(resource_id, limits):
    """Pretend to set a resource limit."""
    return None
'''

SHIMS = {"fcntl.py": FCNTL_SHIM, "resource.py": RESOURCE_SHIM}


def main() -> int:
    """Write the shims."""
    if sys.platform != "win32":
        print("This script is only needed on Windows.")
        return 0

    site_packages = site.getsitepackages()[-1]
    target_dir = Path(site_packages)
    if not target_dir.is_dir():
        print(f"site-packages not found: {target_dir}", file=sys.stderr)
        return 1

    for name, content in SHIMS.items():
        path = target_dir / name
        if path.exists():
            print(f"already present: {path}")
            continue
        path.write_text(content, encoding="utf-8")
        print(f"wrote {path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
