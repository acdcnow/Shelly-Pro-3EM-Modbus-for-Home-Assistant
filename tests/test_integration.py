"""Tests of the integration running inside a real Home Assistant.

The tests start the simulated Shelly device of ``tests/modbus_server.py`` and set
the integration up through a real config entry, so the config flow, the
coordinator, the entity platforms and the options flow are all exercised.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.shelly_pro_3em_modbus.const import (
    CONF_CREATE_DIAGNOSTIC_ENTITIES,
    CONF_CREATE_ENERGY_ENTITIES,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_TIMEOUT,
    CONF_UNIT_ID,
    DOMAIN,
    PROFILE_MONOPHASE,
    PROFILE_TRIPHASE,
)
from tests.modbus_server import DEFAULT_MAC, FakeShellyDevice, FakeShellyServer


@pytest.fixture(autouse=True)
def allow_sockets(socket_enabled: None) -> None:
    """Allow the tests to talk to the simulated device over TCP.

    The Home Assistant test harness disables sockets by default, the simulated
    device listens on 127.0.0.1.
    """


@pytest.fixture(name="device")
def device_fixture() -> FakeShellyDevice:
    """Return a simulated triphase device."""
    return FakeShellyDevice()


@pytest.fixture(name="server")
async def server_fixture(device: FakeShellyDevice) -> AsyncGenerator[FakeShellyServer]:
    """Run a simulated device for the duration of a test."""
    server = FakeShellyServer(device)
    await server.start()
    yield server
    await server.stop()


@pytest.fixture(name="config_entry")
def config_entry_fixture(server: FakeShellyServer) -> MockConfigEntry:
    """Return a config entry that points to the simulated device."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Shelly Pro 3EM",
        unique_id=DEFAULT_MAC,
        data={CONF_HOST: "127.0.0.1", CONF_PORT: server.port, CONF_UNIT_ID: 1},
    )


def state_of(hass: HomeAssistant, suffix: str):
    """Return the single state whose entity id ends with the suffix."""
    matches = [
        state for state in hass.states.async_all() if state.entity_id.endswith(suffix)
    ]
    assert len(matches) == 1, f"expected one entity *{suffix}, got {len(matches)}"
    return matches[0]


def state_named(hass: HomeAssistant, name: str):
    """Return the state with the given complete friendly name."""
    matches = [
        state
        for state in hass.states.async_all()
        if state.attributes.get("friendly_name") == f"shellypro3em-f008d1d8b8b8 {name}"
    ]
    assert len(matches) == 1, f"expected one entity named '{name}', got {len(matches)}"
    return matches[0]


def active_entities(hass: HomeAssistant, suffix: str) -> list[str]:
    """Return the entity ids with the suffix that are not unavailable."""
    return [
        state.entity_id
        for state in hass.states.async_all()
        if state.entity_id.endswith(suffix) and state.state != "unavailable"
    ]


def energy_in_wh(state) -> float:
    """Return the energy of a state in Wh, independent of the display unit."""
    value = float(state.state)
    return value * 1000 if state.attributes["unit_of_measurement"] == "kWh" else value


async def test_setup_entry_creates_triphase_entities(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    server: FakeShellyServer,
    config_entry: MockConfigEntry,
) -> None:
    """Setting up the entry creates a device with all triphase entities."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.LOADED
    assert config_entry.runtime_data.profile == PROFILE_TRIPHASE

    voltage = state_of(hass, "phase_a_voltage")
    assert voltage.state == "230.1"
    assert voltage.attributes["unit_of_measurement"] == "V"
    assert voltage.attributes["device_class"] == "voltage"
    assert voltage.attributes["friendly_name"] == "shellypro3em-f008d1d8b8b8 Phase A voltage"

    assert state_of(hass, "total_current").state == "11.0"
    assert state_of(hass, "total_active_power").state == "2530.2"
    assert state_of(hass, "neutral_current").state == "1.5"
    assert state_of(hass, "phase_c_frequency").state == "49.99"
    assert state_of(hass, "phase_c_meter_error").state == "on"
    assert state_of(hass, "phase_a_meter_error").state == "off"
    assert state_of(hass, "phase_sequence_error").state == "on"
    assert state_of(hass, "phase_c_overcurrent").state == "on"

    energy = state_named(hass, "Total active energy")
    assert energy_in_wh(energy) == pytest.approx(1234567.0)
    assert energy.attributes["state_class"] == "total_increasing"
    assert energy_in_wh(state_named(hass, "Phase B total active energy")) == pytest.approx(
        100001.0
    )
    assert energy_in_wh(state_named(hass, "Phase A lagging reactive energy")) == (
        pytest.approx(1200.0)
    )

    assert state_of(hass, "last_update").state.startswith("20")

    entity_registry = er.async_get(hass)
    entry = entity_registry.async_get(voltage.entity_id)
    assert entry is not None
    assert entry.unique_id == f"{DEFAULT_MAC}_a_voltage"
    assert entry.device_id is not None

    diagnostic = entity_registry.async_get(state_of(hass, "phase_c_meter_error").entity_id)
    assert diagnostic is not None
    assert diagnostic.entity_category is not None
    assert diagnostic.entity_category.value == "diagnostic"

    disabled = entity_registry.async_get_entity_id(
        "sensor", DOMAIN, f"{DEFAULT_MAC}_a_total_act_energy_perpetual"
    )
    assert disabled is not None
    disabled_entry = entity_registry.async_get(disabled)
    assert disabled_entry is not None
    assert disabled_entry.disabled_by is not None

    device = dr.async_get(hass).async_get(entry.device_id)
    assert device is not None
    assert device.model == "ShellyPro3EM"
    assert device.serial_number == DEFAULT_MAC
    assert device.manufacturer == "Shelly"
    assert device.configuration_url == "http://127.0.0.1"


async def test_setup_entry_monophase_device(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """A device with the monophase profile gets channel entities."""
    device = FakeShellyDevice(profile="monophase", mac="EC62608A33A1")
    server = FakeShellyServer(device)
    await server.start()
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Shelly Pro EM",
        unique_id=device.mac,
        data={CONF_HOST: "127.0.0.1", CONF_PORT: server.port, CONF_UNIT_ID: 1},
    )
    entry.add_to_hass(hass)

    try:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert entry.runtime_data.profile == PROFILE_MONOPHASE
        assert state_of(hass, "channel_1_voltage").state == "230.0"
        assert state_of(hass, "channel_3_current").state == "3.0"
        assert state_of(hass, "channel_1_meter_error").state == "off"
        assert energy_in_wh(
            state_of(hass, "channel_2_total_active_energy")
        ) == pytest.approx(1001.0)
        assert not active_entities(hass, "phase_a_voltage")
    finally:
        await server.stop()


async def test_config_flow(
    hass: HomeAssistant, enable_custom_integrations: None, server: FakeShellyServer
) -> None:
    """The config flow creates an entry for a device it can reach."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "127.0.0.1", CONF_PORT: server.port, CONF_UNIT_ID: 1},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "shellypro3em-f008d1d8b8b8"
    assert result["data"] == {
        CONF_HOST: "127.0.0.1",
        CONF_PORT: server.port,
        CONF_UNIT_ID: 1,
    }
    assert result["result"].unique_id == DEFAULT_MAC
    await hass.async_block_till_done()


async def test_config_flow_cannot_connect(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """The config flow reports a connection error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "127.0.0.1", CONF_PORT: 1, CONF_UNIT_ID: 1},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_config_flow_unsupported_device(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """The config flow rejects devices that are not Shelly devices."""
    server = FakeShellyServer(FakeShellyDevice(model="SomethingElse"))
    await server.start()
    try:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "127.0.0.1", CONF_PORT: server.port, CONF_UNIT_ID: 1},
        )
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "unsupported_device"}
    finally:
        await server.stop()


async def test_config_flow_already_configured(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    server: FakeShellyServer,
    config_entry: MockConfigEntry,
) -> None:
    """A device that is already configured is not added twice."""
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "127.0.0.1", CONF_PORT: server.port, CONF_UNIT_ID: 1},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_flow(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    server: FakeShellyServer,
    config_entry: MockConfigEntry,
) -> None:
    """The connection settings can be changed."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reconfigure", "entry_id": config_entry.entry_id},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "127.0.0.1", CONF_PORT: server.port, CONF_UNIT_ID: 2},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()

    assert config_entry.data[CONF_UNIT_ID] == 2
    assert config_entry.state is ConfigEntryState.LOADED


async def test_options_flow(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    server: FakeShellyServer,
    config_entry: MockConfigEntry,
) -> None:
    """The options flow reloads the entry with the new options."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert active_entities(hass, "total_active_energy")

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_SCAN_INTERVAL: 5,
            CONF_TIMEOUT: 4,
            CONF_CREATE_ENERGY_ENTITIES: False,
            CONF_CREATE_DIAGNOSTIC_ENTITIES: False,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    assert config_entry.options[CONF_SCAN_INTERVAL] == 5
    assert config_entry.options[CONF_TIMEOUT] == 4
    assert config_entry.state is ConfigEntryState.LOADED
    assert active_entities(hass, "phase_a_voltage")
    assert not active_entities(hass, "total_active_energy")
    assert not active_entities(hass, "phase_c_meter_error")


async def test_unload_entry(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    server: FakeShellyServer,
    config_entry: MockConfigEntry,
) -> None:
    """Unloading the entry removes the entities and closes the connection."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert active_entities(hass, "phase_a_voltage")

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.NOT_LOADED
    assert not active_entities(hass, "phase_a_voltage")


async def test_entities_become_unavailable_when_device_is_gone(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    server: FakeShellyServer,
    config_entry: MockConfigEntry,
) -> None:
    """A lost device makes the entities unavailable."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert active_entities(hass, "phase_a_voltage")

    await server.stop()
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert not active_entities(hass, "phase_a_voltage")
    assert config_entry.runtime_data.last_update_success is False


async def test_setup_retries_when_device_is_offline(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """An unreachable device leads to a setup retry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Shelly Pro 3EM",
        unique_id="EC62608A33AA",
        data={CONF_HOST: "127.0.0.1", CONF_PORT: 1, CONF_UNIT_ID: 1},
    )
    entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY
