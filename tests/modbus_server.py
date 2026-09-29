"""A small Modbus TCP server that simulates a Shelly Pro 3EM device.

The server is written against the register tables published by Allterco
Robotics and is intentionally independent of the integration code: the pytest
suite uses it to prove that the integration reads and decodes the documented
register addresses.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import logging
import struct
import time
from typing import Final

_LOGGER = logging.getLogger(__name__)

FUNCTION_READ_INPUT_REGISTERS: Final = 4
EXCEPTION_ILLEGAL_FUNCTION: Final = 0x01
EXCEPTION_ILLEGAL_DATA_ADDRESS: Final = 0x02

#: Documented register ranges of the device: (address, size).
DEVICE_INFO_RANGE: Final = (0, 48)
TRIPHASE_RANGES: Final = ((0, 48), (1000, 76), (1160, 67))
MONOPHASE_RANGES: Final = ((0, 48), (2000, 60), (2300, 54))

DEFAULT_MAC: Final = "EC62608A33A0"
DEFAULT_MODEL: Final = "SPEM-003CEBEU"
DEFAULT_NAME: Final = "shellypro3em-f008d1d8b8b8"


def float_registers(value: float) -> list[int]:
    """Encode a float the way the device stores it.

    The low word comes first and every word is big endian (CDAB), like on a real
    Shelly Pro 3EM.
    """
    high, low = struct.unpack(">HH", struct.pack(">f", value))
    return [low, high]


def uint32_registers(value: int) -> list[int]:
    """Encode a 32 bit integer with the low word first, like the device."""
    return [value & 0xFFFF, (value >> 16) & 0xFFFF]


def ascii_registers(text: str, size: int) -> list[int]:
    """Encode a zero terminated ASCII string, low byte of a register first."""
    raw = (text.encode("ascii") + b"\x00")[: size * 2].ljust(size * 2, b"\x00")
    return list(struct.unpack(f"<{size}H", raw))


@dataclass
class FakeShellyDevice:
    """Holds the simulated register values of a Shelly Pro 3EM."""

    profile: str = "triphase"
    mac: str = DEFAULT_MAC
    model: str = DEFAULT_MODEL
    name: str = DEFAULT_NAME
    interval: float = 0.0
    registers: dict[int, int] = field(default_factory=dict)
    requests: list[tuple[int, int]] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Build the initial register values."""
        self.refresh()

    @property
    def ranges(self) -> tuple[tuple[int, int], ...]:
        """Return the register ranges that the device answers."""
        match self.profile:
            case "triphase":
                return TRIPHASE_RANGES
            case "monophase":
                return MONOPHASE_RANGES
            case _:
                return (DEVICE_INFO_RANGE,)

    def put_float(self, address: int, value: float) -> None:
        """Store a float in the register map."""
        self.registers[address], self.registers[address + 1] = float_registers(value)

    def put_uint32(self, address: int, value: int) -> None:
        """Store a 32 bit integer in the register map."""
        self.registers[address], self.registers[address + 1] = uint32_registers(value)

    def refresh(self) -> None:
        """Rebuild all register values."""
        self.registers = {}
        self._build_device_info()
        if self.profile == "triphase":
            self._build_em()
            self._build_em_data()
        else:
            self._build_em1()
            self._build_em1_data()

    def _build_device_info(self) -> None:
        """Build the device information registers."""
        for index, value in enumerate(ascii_registers(self.mac, 6)):
            self.registers[index] = value
        for index, value in enumerate(ascii_registers(self.model, 10)):
            self.registers[6 + index] = value
        for index, value in enumerate(ascii_registers(self.name, 32)):
            self.registers[16 + index] = value

    def _build_em(self) -> None:
        """Build the EM component registers."""
        self.put_uint32(1000, int(time.time()))
        self.registers[1002] = 0  # phase A meter error
        self.registers[1003] = 0  # phase B meter error
        self.registers[1004] = 1  # phase C meter error
        self.registers[1005] = 0  # neutral meter error
        self.registers[1006] = 1  # phase sequence error
        self.put_float(1007, 1.5)  # neutral current
        self.registers[1009] = 1  # neutral current mismatch
        self.registers[1010] = 0  # neutral overcurrent
        self.put_float(1011, 11.0)  # total current
        self.put_float(1013, 2530.2)  # total active power
        self.put_float(1015, 2590.4)  # total apparent power

        phases = (
            (230.1, 4.1, 943.4, 945.0, 0.998, 0, 0, 0, 50.01),
            (231.2, 3.9, 901.7, 903.2, 0.997, 1, 0, 0, 50.0),
            (229.8, 3.0, 685.1, 690.0, 0.993, 0, 0, 1, 49.99),
        )
        for index, values in enumerate(phases):
            base = 1020 + index * 20
            (
                voltage,
                current,
                act_power,
                aprt_power,
                power_factor,
                overpower,
                overvoltage,
                overcurrent,
                frequency,
            ) = values
            self.put_float(base, voltage)
            self.put_float(base + 2, current)
            self.put_float(base + 4, act_power)
            self.put_float(base + 6, aprt_power)
            self.put_float(base + 8, power_factor)
            self.registers[base + 10] = overpower
            self.registers[base + 11] = overvoltage
            self.registers[base + 12] = overcurrent
            self.put_float(base + 13, frequency)

    def _build_em_data(self) -> None:
        """Build the EMData component registers."""
        self.put_uint32(1160, int(time.time()))
        self.put_float(1162, 1234567.0)  # total active energy, all phases
        self.put_float(1164, 12345.0)  # total active returned energy, all phases

        phases = (
            # total, fundamental, returned, fundamental returned, lagging, leading,
            # perpetual total, perpetual returned
            (10.0, 9.0, 1.0, 0.9, 1200.0, 1300.0, 100000.0, 5000.0),
            (11.0, 10.0, 1.1, 1.0, 1201.0, 1301.0, 100001.0, 5001.0),
            (12.0, 11.0, 1.2, 1.1, 1202.0, 1302.0, 100002.0, 5002.0),
        )
        for index, values in enumerate(phases):
            base = 1170 + index * 20
            for offset, value in enumerate(values):
                self.put_float(base + offset * 2, value)

    def _build_em1(self) -> None:
        """Build the EM1 component registers of a monophase device."""
        for index in range(3):
            base = 2000 + index * 20
            self.put_uint32(base, int(time.time()))
            self.registers[base + 2] = 0  # EM1 error
            self.put_float(base + 3, 230.0 + index)
            self.put_float(base + 5, 1.0 + index)
            self.put_float(base + 7, 240.0 + index)
            self.put_float(base + 9, 245.0 + index)
            self.put_float(base + 11, 0.99)
            self.registers[base + 13] = 0  # overpower
            self.registers[base + 14] = 0  # overvoltage
            self.registers[base + 15] = 0  # overcurrent
            self.put_float(base + 16, 50.0)

    def _build_em1_data(self) -> None:
        """Build the EM1Data component registers of a monophase device."""
        for index in range(3):
            base = 2300 + index * 20
            self.put_uint32(base, int(time.time()))
            self.put_float(base + 2, 10.0 + index)  # resettable counter
            self.put_float(base + 4, 1.0 + index)  # resettable counter
            self.put_float(base + 6, 50.0 + index)
            self.put_float(base + 8, 60.0 + index)
            self.put_float(base + 10, 1000.0 + index)  # perpetual counter
            self.put_float(base + 12, 100.0 + index)  # perpetual counter

    def read_registers(self, address: int, count: int) -> list[int] | None:
        """Return the register values or None for an illegal address."""
        if not any(
            start <= address and address + count <= start + size
            for start, size in self.ranges
        ):
            return None
        return [self.registers.get(address + offset, 0) for offset in range(count)]


class FakeShellyServer:
    """Modbus TCP server that answers with the registers of a fake device."""

    def __init__(self, device: FakeShellyDevice, host: str = "127.0.0.1", port: int = 0):
        """Initialize the server."""
        self.device = device
        self.host = host
        self.port = port
        self._server: asyncio.AbstractServer | None = None
        self._writers: set[asyncio.StreamWriter] = set()

    @property
    def request_count(self) -> int:
        """Return the amount of handled requests."""
        return len(self.device.requests)

    @property
    def last_request(self) -> tuple[int, int] | None:
        """Return the last read request."""
        return self.device.requests[-1] if self.device.requests else None

    async def start(self) -> None:
        """Start listening."""
        self._server = await asyncio.start_server(
            self._handle_client, self.host, self.port
        )
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        """Stop listening and close all client connections."""
        for writer in list(self._writers):
            writer.close()
        self._writers.clear()

        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle a single client connection."""
        self._writers.add(writer)
        try:
            while True:
                try:
                    header = await reader.readexactly(7)
                except (asyncio.IncompleteReadError, ConnectionError):
                    return
                transaction_id, protocol_id, length, unit_id = struct.unpack(
                    ">HHHB", header
                )
                pdu = await reader.readexactly(length - 1)
                response = self._build_response(pdu)
                writer.write(
                    struct.pack(
                        ">HHHB",
                        transaction_id,
                        protocol_id,
                        len(response) + 1,
                        unit_id,
                    )
                    + response
                )
                await writer.drain()
        except (ConnectionError, asyncio.CancelledError):
            return
        finally:
            self._writers.discard(writer)
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:  # pragma: no cover - defensive
                pass

    def _build_response(self, pdu: bytes) -> bytes:
        """Build the response PDU for a request PDU."""
        function_code = pdu[0]
        if function_code != FUNCTION_READ_INPUT_REGISTERS:
            return bytes([function_code | 0x80, EXCEPTION_ILLEGAL_FUNCTION])

        address, count = struct.unpack(">HH", pdu[1:5])
        self.device.requests.append((address, count))
        values = self.device.read_registers(address, count)
        if values is None:
            _LOGGER.debug("Illegal data address %s (count %s)", address, count)
            return bytes(
                [
                    function_code | 0x80,
                    EXCEPTION_ILLEGAL_DATA_ADDRESS,
                ]
            )

        payload = b"".join(struct.pack(">H", value) for value in values)
        return bytes([function_code, len(payload)]) + payload
