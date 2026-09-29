"""Data update coordinator for the Shelly Pro 3EM Modbus integration."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import (
    ShellyDeviceInfo,
    ShellyModbusClient,
    ShellyModbusError,
    async_probe_device,
)
from .const import DOMAIN, MANUFACTURER, PROFILE_BLOCKS

_LOGGER = logging.getLogger(__name__)

#: Amount of consecutive failed polls before the device profile is probed again.
PROFILE_RECHECK_FAILURES = 5


class ShellyPro3EMCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator reading all register blocks of the device."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: ShellyModbusClient,
        device: ShellyDeviceInfo,
        scan_interval: int,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {client.host}",
            update_interval=timedelta(seconds=scan_interval),
            config_entry=config_entry,
        )
        self.client = client
        self.device = device
        self.profile = device.profile
        #: Blocks whose registers could not be read during the last poll.
        self.unavailable_blocks: set[str] = set()
        self._failed_updates = 0

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device information of the meter."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.device.mac)},
            name=self.device.name or self.device.model,
            manufacturer=MANUFACTURER,
            model=self.device.model,
            serial_number=self.device.mac,
            configuration_url=f"http://{self.client.host}",
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Read all register blocks of the active profile."""
        blocks = PROFILE_BLOCKS[self.profile]
        data: dict[str, Any] = {}
        failed: set[str] = set()

        for block in blocks:
            try:
                data.update(await self.client.async_read_block(block))
            except ShellyModbusError as err:
                _LOGGER.debug("Unable to read the %s registers: %s", block.key, err)
                failed.add(block.key)

        if len(failed) == len(blocks):
            self.unavailable_blocks = failed
            self._failed_updates += 1
            await self._async_maybe_redetect_profile()
            raise UpdateFailed(
                f"unable to read the registers of {self.device.model}"
                f" at {self.client.host}: {sorted(failed)}"
            )

        self.unavailable_blocks = failed
        self._failed_updates = 0
        return data

    async def _async_maybe_redetect_profile(self) -> None:
        """Reload the config entry if the device switched its profile."""
        if self._failed_updates < PROFILE_RECHECK_FAILURES:
            return

        self._failed_updates = 0
        try:
            device = await async_probe_device(self.client)
        except ShellyModbusError:
            return

        if device.profile != self.profile:
            _LOGGER.warning(
                "Shelly device %s now uses the %s profile, reloading the integration",
                device.mac,
                device.profile,
            )
            self.hass.config_entries.async_schedule_reload(self.config_entry.entry_id)
