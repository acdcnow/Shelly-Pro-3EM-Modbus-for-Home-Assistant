"""Modbus TCP client and device probe for Shelly energy meters."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import re
from typing import Any, Final

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException
from pymodbus.pdu import ExceptionResponse

from .const import (
    DEVICE_INFO_BLOCK,
    DEVICE_MAC,
    DEVICE_MODEL,
    DEVICE_NAME,
    EM1_START,
    EM_START,
    PROFILE_MONOPHASE,
    PROFILE_TRIPHASE,
    RegisterBlock,
)

_LOGGER = logging.getLogger(__name__)

#: Number of registers read to check whether a component exists.
EM_PROBE_ADDRESS: Final = EM_START  # 31000: timestamp and phase A voltage
EM_PROBE_COUNT: Final = 22
EM1_PROBE_ADDRESS: Final = EM1_START  # 32000: the whole first EM1 component
EM1_PROBE_COUNT: Final = 19

#: Modbus exception codes meaning that the requested component does not exist.
EXCEPTION_ILLEGAL_FUNCTION: Final = 0x01
EXCEPTION_ILLEGAL_DATA_ADDRESS: Final = 0x02

#: A MAC address of a Shelly device, 12 hexadecimal characters.
MAC_PATTERN: Final = re.compile(r"^[0-9A-F]{12}$")
EMPTY_MAC: Final = "0" * 12


class ShellyModbusError(Exception):
    """Raised when the device cannot be reached or answers with an error."""


class ShellyModbusResponseError(ShellyModbusError):
    """Raised when the device answers that the requested registers do not exist."""


class UnsupportedDeviceError(ShellyModbusError):
    """Raised when the device is reachable but is not a Shelly device."""


@dataclass(frozen=True, slots=True)
class ShellyDeviceInfo:
    """Information read from the Modbus device information registers."""

    mac: str
    model: str
    name: str
    profile: str


class ShellyModbusClient:
    """Small wrapper around the pymodbus TCP client.

    The wrapper keeps a single connection alive, reads whole register blocks in
    one request and translates every transport problem into
    :class:`ShellyModbusError`.
    """

    def __init__(self, host: str, port: int, unit_id: int, timeout: float) -> None:
        """Initialize the client."""
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self._client = AsyncModbusTcpClient(host, port=port, timeout=timeout)

    @property
    def connected(self) -> bool:
        """Return whether the TCP connection is established."""
        return self._client.connected

    async def async_connect(self) -> None:
        """Connect to the device if not connected already."""
        if self._client.connected:
            return
        if not await self._client.connect():
            raise ShellyModbusError(
                f"unable to connect to the Modbus server at {self.host}:{self.port}"
            )

    async def async_close(self) -> None:
        """Close the connection."""
        try:
            self._client.close()
        except ModbusException as err:  # pragma: no cover - defensive
            _LOGGER.debug("Error while closing the Modbus connection: %s", err)

    async def async_read_registers(self, address: int, count: int) -> list[int]:
        """Read input registers, retrying once with a fresh connection.

        An error response of the device (for example for the registers of a
        component that does not exist) is not retried, only transport errors are.
        """
        await self.async_connect()
        try:
            return await self._async_read_registers(address, count)
        except ShellyModbusResponseError:
            raise
        except ShellyModbusError as err:
            _LOGGER.debug(
                "Reading %s registers at %s failed (%s), reconnecting",
                count,
                address,
                err,
            )
        await self.async_close()
        await self.async_connect()
        return await self._async_read_registers(address, count)

    async def _async_read_registers(self, address: int, count: int) -> list[int]:
        """Read a single range of input registers."""
        try:
            result = await self._client.read_input_registers(
                address, count=count, device_id=self.unit_id
            )
        except ModbusException as err:
            raise ShellyModbusError(str(err)) from err

        if result is None:
            raise ShellyModbusError(
                f"no response for {count} registers at address {address}"
            )
        if result.isError():
            message = f"error response for {count} registers at address {address}: {result}"
            if isinstance(result, ExceptionResponse) and result.exception_code in (
                EXCEPTION_ILLEGAL_FUNCTION,
                EXCEPTION_ILLEGAL_DATA_ADDRESS,
            ):
                raise ShellyModbusResponseError(message)
            raise ShellyModbusError(message)
        if not hasattr(result, "registers"):
            raise ShellyModbusError(
                f"unexpected response for {count} registers at address {address}: {result}"
            )
        if len(result.registers) != count:
            raise ShellyModbusError(
                f"expected {count} registers at address {address},"
                f" got {len(result.registers)}"
            )
        return list(result.registers)

    async def async_read_block(self, block: RegisterBlock) -> dict[str, Any]:
        """Read a block of registers and decode all values in it."""
        registers = await self.async_read_registers(block.address, block.size)
        return {
            register.key: register.decoder(
                registers, register.address - block.address
            )
            for register in block.registers
        }


async def async_probe_device(client: ShellyModbusClient) -> ShellyDeviceInfo:
    """Read the device information and detect the configured device profile.

    The model register holds the model code of the device (``SPEM-003CEBEU`` for a
    Shelly Pro 3EM), not a friendly name, so the device is identified by its MAC
    address and by the energy meter component that answers, not by the model text.
    """
    values = await client.async_read_block(DEVICE_INFO_BLOCK)

    model = str(values.get(DEVICE_MODEL, ""))
    mac = str(values.get(DEVICE_MAC, "")).upper()
    name = str(values.get(DEVICE_NAME, ""))

    if mac == EMPTY_MAC or not MAC_PATTERN.match(mac):
        raise UnsupportedDeviceError(
            "the Modbus server did not return the device information registers"
            " of a Shelly device"
        )

    return ShellyDeviceInfo(
        mac=mac,
        model=model,
        name=name,
        profile=await _async_detect_profile(client),
    )


async def _async_detect_profile(client: ShellyModbusClient) -> str:
    """Detect whether the device runs the triphase or the monophase profile.

    The ``EM`` component only exists in the triphase profile and the ``EM1``
    components only exist in the monophase profile.  A component that does not
    exist answers with an illegal data address, which is the primary indication.
    Should a device answer both probes with zeros (for example right after a
    power loss without a synchronized clock), the component that reports values
    wins.
    """
    em = await _async_read_probe(client, EM_PROBE_ADDRESS, EM_PROBE_COUNT)
    em1 = await _async_read_probe(client, EM1_PROBE_ADDRESS, EM1_PROBE_COUNT)

    if em is not None and (any(em) or em1 is None or not any(em1)):
        return PROFILE_TRIPHASE
    if em1 is not None:
        return PROFILE_MONOPHASE
    raise UnsupportedDeviceError(
        "no energy meter component was found on the device"
    )


async def _async_read_probe(
    client: ShellyModbusClient, address: int, count: int
) -> list[int] | None:
    """Read a probe range, returning None if the component does not exist."""
    try:
        return await client.async_read_registers(address, count)
    except ShellyModbusResponseError as err:
        _LOGGER.debug("No component at address %s: %s", address, err)
        return None
