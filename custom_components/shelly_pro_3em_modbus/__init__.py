"""The Shelly Pro 3EM Modbus integration."""

from __future__ import annotations

from typing import Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .client import ShellyModbusClient, ShellyModbusError, async_probe_device
from .const import (
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_TIMEOUT,
    CONF_UNIT_ID,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
)
from .coordinator import ShellyPro3EMCoordinator

PLATFORMS: Final = [Platform.BINARY_SENSOR, Platform.SENSOR]

type ShellyPro3EMConfigEntry = ConfigEntry[ShellyPro3EMCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: ShellyPro3EMConfigEntry) -> bool:
    """Set up a Shelly Pro 3EM device from a config entry."""
    client = ShellyModbusClient(
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        unit_id=entry.data[CONF_UNIT_ID],
        timeout=entry.options.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
    )

    try:
        device = await async_probe_device(client)
    except ShellyModbusError as err:
        await client.async_close()
        raise ConfigEntryNotReady(
            f"Error communicating with the Shelly device: {err}"
        ) from err

    coordinator = ShellyPro3EMCoordinator(
        hass,
        entry,
        client,
        device,
        entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: ShellyPro3EMConfigEntry
) -> bool:
    """Unload a Shelly Pro 3EM config entry."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False

    await entry.runtime_data.client.async_close()
    return True
