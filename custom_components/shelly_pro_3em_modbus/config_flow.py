"""Config flow for the Shelly Pro 3EM Modbus integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.helpers import selector

from .client import (
    ShellyDeviceInfo,
    ShellyModbusClient,
    ShellyModbusError,
    UnsupportedDeviceError,
    async_probe_device,
)
from .const import (
    CONF_CREATE_DIAGNOSTIC_ENTITIES,
    CONF_CREATE_ENERGY_ENTITIES,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_TIMEOUT,
    CONF_UNIT_ID,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    DEFAULT_UNIT_ID,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MAX_TIMEOUT,
    MIN_SCAN_INTERVAL,
    MIN_TIMEOUT,
)

HOST_SELECTOR = selector.TextSelector()
PORT_SELECTOR = selector.NumberSelector(
    selector.NumberSelectorConfig(
        min=1, max=65535, mode=selector.NumberSelectorMode.BOX
    )
)
UNIT_ID_SELECTOR = selector.NumberSelector(
    selector.NumberSelectorConfig(
        min=0, max=247, step=1, mode=selector.NumberSelectorMode.BOX
    )
)


def _connection_schema(
    host: str | None = None,
    port: int = DEFAULT_PORT,
    unit_id: int = DEFAULT_UNIT_ID,
) -> vol.Schema:
    """Return the schema of the connection settings."""
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=host): HOST_SELECTOR,
            vol.Required(CONF_PORT, default=port): PORT_SELECTOR,
            vol.Required(CONF_UNIT_ID, default=unit_id): UNIT_ID_SELECTOR,
        }
    )


def _options_schema(options: Mapping[str, Any]) -> vol.Schema:
    """Return the schema of the integration options."""
    return vol.Schema(
        {
            vol.Optional(
                CONF_SCAN_INTERVAL,
                default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_SCAN_INTERVAL,
                    max=MAX_SCAN_INTERVAL,
                    step=1,
                    unit_of_measurement="s",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                CONF_TIMEOUT,
                default=options.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_TIMEOUT,
                    max=MAX_TIMEOUT,
                    step=1,
                    unit_of_measurement="s",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                CONF_CREATE_ENERGY_ENTITIES,
                default=options.get(CONF_CREATE_ENERGY_ENTITIES, True),
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_CREATE_DIAGNOSTIC_ENTITIES,
                default=options.get(CONF_CREATE_DIAGNOSTIC_ENTITIES, True),
            ): selector.BooleanSelector(),
        }
    )


def _connection_data(user_input: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize the connection settings of the user input."""
    return {
        CONF_HOST: str(user_input[CONF_HOST]).strip(),
        CONF_PORT: int(user_input[CONF_PORT]),
        CONF_UNIT_ID: int(user_input[CONF_UNIT_ID]),
    }


async def _async_probe_connection(data: Mapping[str, Any]) -> ShellyDeviceInfo:
    """Connect to the device and read its information."""
    client = ShellyModbusClient(
        host=data[CONF_HOST],
        port=data[CONF_PORT],
        unit_id=data[CONF_UNIT_ID],
        timeout=DEFAULT_TIMEOUT,
    )
    try:
        return await async_probe_device(client)
    finally:
        await client.async_close()


class ShellyPro3EMConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow of a Shelly Pro 3EM device."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            data = _connection_data(user_input)
            try:
                device = await _async_probe_connection(data)
            except UnsupportedDeviceError:
                errors["base"] = "unsupported_device"
            except ShellyModbusError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(device.mac)
                self._abort_if_unique_id_configured()
                self._async_abort_entries_match(
                    {CONF_HOST: data[CONF_HOST], CONF_PORT: data[CONF_PORT]}
                )
                return self.async_create_entry(
                    title=device.name or f"{device.model} ({data[CONF_HOST]})",
                    data=data,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_connection_schema(),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguring the connection settings."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            data = _connection_data(user_input)
            try:
                device = await _async_probe_connection(data)
            except UnsupportedDeviceError:
                errors["base"] = "unsupported_device"
            except ShellyModbusError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=device.mac,
                    data_updates=data,
                    reason="reconfigure_successful",
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                _connection_schema(),
                user_input or dict(entry.data),
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> ShellyPro3EMOptionsFlow:
        """Return the options flow of the integration."""
        return ShellyPro3EMOptionsFlow()


class ShellyPro3EMOptionsFlow(OptionsFlowWithReload):
    """Handle the options of a Shelly Pro 3EM device."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the options step."""
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                    CONF_TIMEOUT: int(user_input[CONF_TIMEOUT]),
                    CONF_CREATE_ENERGY_ENTITIES: bool(
                        user_input[CONF_CREATE_ENERGY_ENTITIES]
                    ),
                    CONF_CREATE_DIAGNOSTIC_ENTITIES: bool(
                        user_input[CONF_CREATE_DIAGNOSTIC_ENTITIES]
                    ),
                },
            )

        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(self.config_entry.options),
        )
