"""Tests that the register map matches the Shelly documentation.

The expected addresses are derived from the register tables published in the
Shelly API documentation.  Shelly numbers the registers with the ``3xxxx``
reference convention, the Modbus protocol address is that number minus 30000.
"""

from __future__ import annotations

from typing import Final

import pytest

from custom_components.shelly_pro_3em_modbus.const import (
    DEVICE_INFO_BLOCK,
    DEVICE_MAC,
    DEVICE_MODEL,
    DEVICE_NAME,
    EM_BLOCK,
    EM_DATA_BLOCK,
    EM1_BLOCK,
    EM1_DATA_BLOCK,
    PHASES,
    RegisterBlock,
    decode_bool,
    decode_float32,
    decode_uint32,
)

# Registers captured from a real Shelly Pro 3EM, firmware 2.1.0-beta1.
REAL_MAC_REGISTERS: Final = (0x4345, 0x3236, 0x3036, 0x3739, 0x4135, 0x3836)
REAL_MODEL_REGISTERS: Final = (0x5053, 0x4D45, 0x302D, 0x3330, 0x4543, 0x4542, 0x0055)
REAL_MAC: Final = "EC6260975A68"
REAL_MODEL: Final = "SPEM-003CEBEU"
REAL_PHASE_A_VOLTAGE_REGISTERS: Final = (0xA260, 0x4369)  # 233.63 V
REAL_PHASE_A_FREQUENCY_REGISTERS: Final = (0xF600, 0x4247)  # 49.99 Hz
REAL_TIMESTAMP_REGISTERS: Final = (0x36DD, 0x6ABC)  # 2026-09-29 22:08:29 UTC

# Highest amount of registers a Modbus request may read.
MAX_REGISTER_COUNT: Final = 125

# Documented device information registers.
DOCUMENTED_DEVICE_INFO: Final = (
    (30000, "mac", 6),
    (30006, "model", 10),
    (30016, "device_name", 32),
)

# Documented layout of one EM phase, repeated at 31020 / 31040 / 31060.
EM_PHASE_TEMPLATE: Final = (
    (0, "voltage", 2),
    (2, "current", 2),
    (4, "act_power", 2),
    (6, "aprt_power", 2),
    (8, "pf", 2),
    (10, "overpower", 1),
    (11, "overvoltage", 1),
    (12, "overcurrent", 1),
    (13, "freq", 2),
)
EM_PHASE_REFERENCES: Final = (31020, 31040, 31060)

DOCUMENTED_EM_HEADER: Final = (
    (31000, "em_timestamp", 2),
    (31002, "phase_a_meter_error", 1),
    (31003, "phase_b_meter_error", 1),
    (31004, "phase_c_meter_error", 1),
    (31005, "neutral_meter_error", 1),
    (31006, "phase_sequence_error", 1),
    (31007, "neutral_current", 2),
    (31009, "neutral_current_mismatch", 1),
    (31010, "neutral_overcurrent", 1),
    (31011, "total_current", 2),
    (31013, "total_act_power", 2),
    (31015, "total_aprt_power", 2),
)

# Documented layout of one EMData phase, repeated at 31170 / 31190 / 31210.
EM_DATA_PHASE_TEMPLATE: Final = (
    (0, "total_act_energy", 2),
    (2, "fund_act_energy", 2),
    (4, "total_act_ret_energy", 2),
    (6, "fund_act_ret_energy", 2),
    (8, "lag_react_energy", 2),
    (10, "lead_react_energy", 2),
    (12, "total_act_energy_perpetual", 2),
    (14, "total_act_ret_energy_perpetual", 2),
)
EM_DATA_PHASE_REFERENCES: Final = (31170, 31190, 31210)

DOCUMENTED_EM_DATA_HEADER: Final = (
    (31160, "emdata_timestamp", 2),
    (31162, "total_act_energy", 2),
    (31164, "total_act_ret_energy", 2),
)

# Documented layout of one EM1 component, repeated every 20 registers from 32000.
EM1_TEMPLATE: Final = (
    (0, "timestamp", 2),
    (2, "error", 1),
    (3, "voltage", 2),
    (5, "current", 2),
    (7, "act_power", 2),
    (9, "aprt_power", 2),
    (11, "pf", 2),
    (13, "overpower", 1),
    (14, "overvoltage", 1),
    (15, "overcurrent", 1),
    (16, "freq", 2),
)
EM1_BASES: Final = (32000, 32020, 32040)

# Documented layout of one EM1Data component, repeated every 20 registers from 32300.
EM1_DATA_TEMPLATE: Final = (
    (0, "timestamp", 2),
    (2, "total_act_energy", 2),
    (4, "total_act_ret_energy", 2),
    (6, "lag_react_energy", 2),
    (8, "lead_react_energy", 2),
    (10, "total_act_energy_perpetual", 2),
    (12, "total_act_ret_energy_perpetual", 2),
)
EM1_DATA_BASES: Final = (32300, 32320, 32340)


def _documented_block(
    header: tuple[tuple[int, str, int], ...],
    template: tuple[tuple[int, str, int], ...],
    bases: tuple[int, ...],
    key_prefix: str,
) -> dict[str, tuple[int, int]]:
    """Expand a documented register table into key -> (address, size)."""
    expected = {
        key: (reference - 30000, size) for reference, key, size in header
    }
    for base, phase in zip(bases, PHASES, strict=True):
        for offset, field, size in template:
            expected[f"{key_prefix}{phase}_{field}"] = (base - 30000 + offset, size)
    return expected


def _block_map(block: RegisterBlock) -> dict[str, tuple[int, int]]:
    """Return key -> (address, size) of an integration register block."""
    return {
        register.key: (register.address, register.size)
        for register in block.registers
    }


def test_device_information_registers() -> None:
    """The device information registers match the documentation."""
    expected = {
        key: (reference - 30000, size) for reference, key, size in DOCUMENTED_DEVICE_INFO
    }
    assert _block_map(DEVICE_INFO_BLOCK) == expected


def test_em_registers() -> None:
    """The EM registers match the documentation."""
    expected = _documented_block(
        DOCUMENTED_EM_HEADER, EM_PHASE_TEMPLATE, EM_PHASE_REFERENCES, ""
    )
    assert _block_map(EM_BLOCK) == expected


def test_em_data_registers() -> None:
    """The EMData registers match the documentation."""
    expected = {
        key: (reference - 30000, size)
        for reference, key, size in DOCUMENTED_EM_DATA_HEADER
    }
    expected.update(
        _documented_block((), EM_DATA_PHASE_TEMPLATE, EM_DATA_PHASE_REFERENCES, "")
    )
    assert _block_map(EM_DATA_BLOCK) == expected


def test_em1_registers() -> None:
    """The EM1 registers match the documentation."""
    expected: dict[str, tuple[int, int]] = {}
    for index, base in enumerate(EM1_BASES):
        for offset, field, size in EM1_TEMPLATE:
            expected[f"em1_{index}_{field}"] = (base - 30000 + offset, size)
    assert _block_map(EM1_BLOCK) == expected


def test_em1_data_registers() -> None:
    """The EM1Data registers match the documentation."""
    expected: dict[str, tuple[int, int]] = {}
    for index, base in enumerate(EM1_DATA_BASES):
        for offset, field, size in EM1_DATA_TEMPLATE:
            expected[f"em1data_{index}_{field}"] = (base - 30000 + offset, size)
    assert _block_map(EM1_DATA_BLOCK) == expected


@pytest.mark.parametrize(
    "block",
    [DEVICE_INFO_BLOCK, EM_BLOCK, EM_DATA_BLOCK, EM1_BLOCK, EM1_DATA_BLOCK],
    ids=lambda block: block.key,
)
def test_block_is_readable(block: RegisterBlock) -> None:
    """Every block fits into a single Modbus request and stays inside itself."""
    assert 0 < block.size <= MAX_REGISTER_COUNT
    for register in block.registers:
        offset = register.address - block.address
        assert 0 <= offset
        assert offset + register.size <= block.size


@pytest.mark.parametrize(
    "block",
    [DEVICE_INFO_BLOCK, EM_BLOCK, EM_DATA_BLOCK, EM1_BLOCK, EM1_DATA_BLOCK],
    ids=lambda block: block.key,
)
def test_registers_do_not_overlap(block: RegisterBlock) -> None:
    """No two values of a block share a register."""
    used: set[int] = set()
    for register in block.registers:
        addresses = set(range(register.address, register.address + register.size))
        assert not used & addresses, register.key
        used |= addresses


def test_decode_float32() -> None:
    """Floats are stored with the low word first (CDAB)."""
    assert decode_float32([0x6666, 0x4366], 0) == pytest.approx(230.4, abs=1e-3)
    assert decode_float32([0x0000, 0x0000], 0) == 0.0
    assert decode_float32([0xFFFF, 0x0000, 0xC1F0], 1) == pytest.approx(-30.0)
    # Registers of a real device.
    assert decode_float32(list(REAL_PHASE_A_VOLTAGE_REGISTERS), 0) == pytest.approx(
        233.63, abs=1e-2
    )
    assert decode_float32(list(REAL_PHASE_A_FREQUENCY_REGISTERS), 0) == pytest.approx(
        49.99, abs=1e-2
    )


def test_decode_uint32() -> None:
    """32 bit integers are stored with the low word first."""
    assert decode_uint32([0x0002, 0x0001], 0) == 0x00010002
    assert decode_uint32([0x5678, 0x1234], 0) == 0x12345678
    # Registers of a real device: the timestamp of the last EM update.
    assert decode_uint32(list(REAL_TIMESTAMP_REGISTERS), 0) == 1790719709


def test_decode_bool() -> None:
    """Boolean registers are decoded as booleans."""
    assert decode_bool([0], 0) is False
    assert decode_bool([1], 0) is True


def test_device_information_decoding() -> None:
    """The ASCII device information decodes to readable strings.

    The registers are the ones that a real Shelly Pro 3EM returned, the low byte
    of every register holds the first character.
    """
    registers = [0] * DEVICE_INFO_BLOCK.size
    for index, value in enumerate(REAL_MAC_REGISTERS):
        registers[index] = value
    for index, value in enumerate(REAL_MODEL_REGISTERS):
        registers[6 + index] = value

    values = {
        register.key: register.decoder(registers, register.address)
        for register in DEVICE_INFO_BLOCK.registers
    }
    assert values[DEVICE_MAC] == REAL_MAC
    assert values[DEVICE_MODEL] == REAL_MODEL
    assert values[DEVICE_NAME] == ""
