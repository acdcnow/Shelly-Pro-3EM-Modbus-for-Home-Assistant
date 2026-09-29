"""Diagnostics support for the Shelly Pro 3EM Modbus integration."""

from __future__ import annotations

from typing import Any, Final

from homeassistant.core import HomeAssistant

from . import ShellyPro3EMConfigEntry

TO_REDACT: Final[set[str]] = set()


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ShellyPro3EMConfigEntry
) -> dict[str, Any]:
    """Return diagnostics of a config entry."""
    coordinator = entry.runtime_data

    return {
        "entry": {
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
        "device": {
            "mac": coordinator.device.mac,
            "model": coordinator.device.model,
            "name": coordinator.device.name,
            "profile": coordinator.profile,
            "connected": coordinator.client.connected,
        },
        "last_update_success": coordinator.last_update_success,
        "unavailable_blocks": sorted(coordinator.unavailable_blocks),
        "data": dict(coordinator.data),
    }
