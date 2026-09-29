"""Tests of the Modbus client against a simulated Shelly Pro 3EM device."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
import functools
from typing import Any

import pytest

from custom_components.shelly_pro_3em_modbus.client import (
    ShellyModbusClient,
    ShellyModbusError,
    UnsupportedDeviceError,
    async_probe_device,
)
from custom_components.shelly_pro_3em_modbus.const import (
    EM_BLOCK,
    EM_DATA_BLOCK,
    EM1_BLOCK,
    EM1_DATA_BLOCK,
    PROFILE_MONOPHASE,
    PROFILE_TRIPHASE,
)
from tests.modbus_server import DEFAULT_MAC, DEFAULT_MODEL, FakeShellyDevice, FakeShellyServer


def async_test(
    function: Callable[..., Coroutine[Any, Any, None]],
) -> Callable[..., None]:
    """Run an async test coroutine without an async test plugin."""

    @functools.wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> None:
        asyncio.run(function(*args, **kwargs))

    return wrapper


async def _setup(device: FakeShellyDevice) -> tuple[FakeShellyServer, ShellyModbusClient]:
    """Start a server and return it next to a connected client."""
    server = FakeShellyServer(device)
    await server.start()
    client = ShellyModbusClient("127.0.0.1", server.port, 1, 3)
    return server, client


@async_test
async def test_probe_triphase_device() -> None:
    """A triphase device is detected and its information is read."""
    device = FakeShellyDevice()
    server, client = await _setup(device)
    try:
        info = await async_probe_device(client)
    finally:
        await client.async_close()
        await server.stop()

    assert info.mac == DEFAULT_MAC
    assert info.model == DEFAULT_MODEL
    assert info.name == "shellypro3em-f008d1d8b8b8"
    assert info.profile == PROFILE_TRIPHASE
    assert device.requests[0] == (0, 48)


@async_test
async def test_probe_monophase_device() -> None:
    """A device with the monophase profile is detected by the EM1 registers."""
    device = FakeShellyDevice(profile="monophase")
    server, client = await _setup(device)
    try:
        info = await async_probe_device(client)
    finally:
        await client.async_close()
        await server.stop()

    assert info.profile == PROFILE_MONOPHASE


@async_test
async def test_probe_rejects_other_devices() -> None:
    """A reachable device without an energy meter is rejected."""
    device = FakeShellyDevice(model="NotAShelly", profile="monophase")
    server, client = await _setup(device)
    try:
        with pytest.raises(UnsupportedDeviceError):
            await async_probe_device(client)
    finally:
        await client.async_close()
        await server.stop()


@async_test
async def test_probe_rejects_device_without_energy_meter() -> None:
    """A Shelly device without an energy meter component is rejected."""
    device = FakeShellyDevice(profile="none")
    server, client = await _setup(device)
    try:
        with pytest.raises(ShellyModbusError):
            await async_probe_device(client)
    finally:
        await client.async_close()
        await server.stop()


@async_test
async def test_read_em_block() -> None:
    """The EM registers are read from the documented address range."""
    device = FakeShellyDevice()
    server, client = await _setup(device)
    try:
        values = await client.async_read_block(EM_BLOCK)
    finally:
        await client.async_close()
        await server.stop()

    assert device.requests == [(1000, 76)]
    assert values["em_timestamp"] > 0
    assert values["a_voltage"] == pytest.approx(230.1, abs=1e-3)
    assert values["b_current"] == pytest.approx(3.9, abs=1e-3)
    assert values["c_act_power"] == pytest.approx(685.1, abs=1e-2)
    assert values["c_aprt_power"] == pytest.approx(690.0, abs=1e-2)
    assert values["a_pf"] == pytest.approx(0.998, abs=1e-6)
    assert values["c_freq"] == pytest.approx(49.99, abs=1e-3)
    assert values["total_current"] == pytest.approx(11.0, abs=1e-3)
    assert values["total_act_power"] == pytest.approx(2530.2, abs=1e-2)
    assert values["total_aprt_power"] == pytest.approx(2590.4, abs=1e-2)
    assert values["neutral_current"] == pytest.approx(1.5, abs=1e-3)
    assert values["phase_c_meter_error"] is True
    assert values["phase_sequence_error"] is True
    assert values["neutral_current_mismatch"] is True
    assert values["phase_a_meter_error"] is False
    assert values["c_overcurrent"] is True
    assert values["a_overpower"] is False


@async_test
async def test_read_em_data_block() -> None:
    """The EMData registers are read from the documented address range."""
    device = FakeShellyDevice()
    server, client = await _setup(device)
    try:
        values = await client.async_read_block(EM_DATA_BLOCK)
    finally:
        await client.async_close()
        await server.stop()

    assert device.requests == [(1160, 67)]
    assert values["emdata_timestamp"] > 0
    assert values["total_act_energy"] == pytest.approx(1234567.0)
    assert values["total_act_ret_energy"] == pytest.approx(12345.0)
    assert values["a_total_act_energy"] == pytest.approx(100000.0)
    assert values["b_total_act_energy"] == pytest.approx(100001.0)
    assert values["c_total_act_energy"] == pytest.approx(100002.0)
    assert values["c_fund_act_ret_energy"] == pytest.approx(5001.0)
    assert values["a_lag_react_energy"] == pytest.approx(1200.0)
    assert values["c_total_act_energy_perpetual"] == pytest.approx(100002.0)


@async_test
async def test_read_em1_blocks() -> None:
    """The monophase registers of all three EM1 components are read."""
    device = FakeShellyDevice(profile="monophase")
    server, client = await _setup(device)
    try:
        momentary = await client.async_read_block(EM1_BLOCK)
        energy = await client.async_read_block(EM1_DATA_BLOCK)
    finally:
        await client.async_close()
        await server.stop()

    assert device.requests == [(2000, 60), (2300, 54)]
    assert momentary["em1_0_voltage"] == pytest.approx(230.0, abs=1e-3)
    assert momentary["em1_1_voltage"] == pytest.approx(231.0, abs=1e-3)
    assert momentary["em1_2_current"] == pytest.approx(3.0, abs=1e-3)
    assert momentary["em1_2_aprt_power"] == pytest.approx(247.0, abs=1e-2)
    assert momentary["em1_0_error"] is False
    assert energy["em1data_0_total_act_energy"] == pytest.approx(1000.0)
    assert energy["em1data_2_total_act_ret_energy"] == pytest.approx(102.0)
    assert energy["em1data_1_lead_react_energy"] == pytest.approx(61.0)


@async_test
async def test_read_illegal_address_raises() -> None:
    """Reading a component that does not exist raises an error."""
    device = FakeShellyDevice()
    server, client = await _setup(device)
    try:
        with pytest.raises(ShellyModbusError):
            await client.async_read_block(EM1_BLOCK)
    finally:
        await client.async_close()
        await server.stop()


@async_test
async def test_client_reconnects_after_connection_loss() -> None:
    """A lost connection is re-established on the next read."""
    device = FakeShellyDevice()
    server, client = await _setup(device)
    port = server.port
    try:
        values = await client.async_read_block(EM_BLOCK)
        assert values["a_voltage"] == pytest.approx(230.1, abs=1e-3)

        await server.stop()
        with pytest.raises(ShellyModbusError):
            await client.async_read_block(EM_BLOCK)

        server = FakeShellyServer(device, port=port)
        await server.start()
        values = await client.async_read_block(EM_BLOCK)
        assert values["a_voltage"] == pytest.approx(230.1, abs=1e-3)
    finally:
        await client.async_close()
        await server.stop()
