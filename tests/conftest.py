"""Test configuration of the Shelly Pro 3EM Modbus integration."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

import pytest_socket

REPO_ROOT = Path(__file__).parent.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


if sys.platform == "win32":
    # pytest_homeassistant_custom_component disables the creation of sockets for
    # every single test.  asyncio on Windows creates the event loop with a real
    # socket pair, so the event loop fixture of pytest-asyncio fails before any
    # fixture could enable sockets again.  Home Assistant does not support
    # Windows natively, this only keeps the test suite usable on Windows.
    # Continuous integration runs on Linux, where sockets stay disabled.
    def _keep_sockets_enabled(*args: Any, **kwargs: Any) -> None:
        """Do not disable the sockets."""

    pytest_socket.disable_socket = _keep_sockets_enabled  # type: ignore[assignment]
