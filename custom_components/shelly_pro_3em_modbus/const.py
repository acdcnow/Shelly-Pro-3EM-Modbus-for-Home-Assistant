"""Constants and Modbus register map for the Shelly Pro 3EM integration.

The register layout is documented by Allterco Robotics in the Shelly API
documentation (https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/EM).

Shelly documents the registers with the ``3xxxx`` reference convention, where
``31020`` is phase A voltage and ``31160`` is the timestamp of the energy data.
Modbus requests use the plain protocol address, which is the documented number
minus ``30000``, so ``31020`` is read from input register ``1020``.

Every register listed by Shelly for the Pro 3EM is an input register (Modbus
function code 4).  The byte order was verified against a real Shelly Pro 3EM
(firmware 2.1.0-beta1):

* 32 bit values are stored in the CDAB order, the low word comes first and every
  word is big endian (``0x4369`` ``0xA260`` is 233.63 V).  This is the "byte order
  mixed" mode that Shelly uses in its own tool examples.
* ASCII strings hold two characters per register with the low byte first
  (``0x4345`` is ``"EC"``) and are terminated with a zero byte.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
import struct
from typing import Any, Final

DOMAIN: Final = "shelly_pro_3em_modbus"

MANUFACTURER: Final = "Shelly"
MODEL_PRO_3EM: Final = "Shelly Pro 3EM"
DEFAULT_DEVICE_NAME: Final = "Shelly Pro 3EM"

#: Friendly names for the model codes that the devices report in their registers.
MODEL_DISPLAY_NAMES: Final[dict[str, str]] = {
    # Shelly Pro 3EM, verified on a real device (app "Pro3EM").
    "SPEM-003CEBEU": MODEL_PRO_3EM,
}

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
CONF_HOST: Final = "host"
CONF_PORT: Final = "port"
CONF_UNIT_ID: Final = "unit_id"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_TIMEOUT: Final = "timeout"
CONF_CREATE_ENERGY_ENTITIES: Final = "create_energy_entities"
CONF_CREATE_DIAGNOSTIC_ENTITIES: Final = "create_diagnostic_entities"

DEFAULT_PORT: Final = 502
DEFAULT_UNIT_ID: Final = 1
DEFAULT_SCAN_INTERVAL: Final = 10
DEFAULT_TIMEOUT: Final = 5
MIN_SCAN_INTERVAL: Final = 5
MAX_SCAN_INTERVAL: Final = 600
MIN_TIMEOUT: Final = 1
MAX_TIMEOUT: Final = 30

# --------------------------------------------------------------------------
# Device profiles
# --------------------------------------------------------------------------
# A Shelly Pro 3EM runs either the "triphase" profile (a single EM component
# with three phases) or the "monophase" profile (three separate EM1 components).
PROFILE_TRIPHASE: Final = "triphase"
PROFILE_MONOPHASE: Final = "monophase"

PHASES: Final = ("a", "b", "c")


# --------------------------------------------------------------------------
# Register decoding
# --------------------------------------------------------------------------
Decoder = Callable[[Sequence[int], int], Any]


def decode_float32(registers: Sequence[int], offset: int) -> float:
    """Decode a 32 bit float from two registers.

    Shelly stores 32 bit values in the CDAB order: the low word comes first and
    every word is big endian.
    """
    return float(
        struct.unpack(
            ">f", struct.pack(">HH", registers[offset + 1], registers[offset])
        )[0]
    )


def decode_uint32(registers: Sequence[int], offset: int) -> int:
    """Decode a 32 bit unsigned integer from two registers (CDAB order)."""
    return (registers[offset + 1] << 16) | registers[offset]


def decode_bool(registers: Sequence[int], offset: int) -> bool:
    """Decode a single register into a boolean."""
    return bool(registers[offset])


def _ascii_decoder(register_count: int) -> Decoder:
    """Return a decoder for a zero terminated ASCII string.

    Every register holds two characters with the low byte first, so ``0x4345``
    is ``"EC"``.  Everything from the first zero byte on is padding.
    """

    def _decode(registers: Sequence[int], offset: int) -> str:
        raw = b"".join(
            struct.pack("<H", registers[offset + index])
            for index in range(register_count)
        )
        return raw.split(b"\x00", 1)[0].decode("ascii", errors="ignore").strip()

    return _decode


@dataclass(frozen=True, slots=True)
class Register:
    """A single value inside a block of registers."""

    key: str
    address: int
    size: int
    decoder: Decoder


@dataclass(frozen=True, slots=True)
class RegisterBlock:
    """A contiguous block of input registers read with a single request."""

    key: str
    address: int
    size: int
    registers: tuple[Register, ...]

    @property
    def keys(self) -> tuple[str, ...]:
        """Return the keys of all values in the block."""
        return tuple(register.key for register in self.registers)


# --------------------------------------------------------------------------
# Device information (registers 30000 - 30047)
# --------------------------------------------------------------------------
DEVICE_MAC: Final = "mac"
DEVICE_MODEL: Final = "model"
DEVICE_NAME: Final = "device_name"

DEVICE_INFO_BLOCK: Final = RegisterBlock(
    key="device_info",
    address=0,
    size=48,
    registers=(
        Register(DEVICE_MAC, 0, 6, _ascii_decoder(6)),
        Register(DEVICE_MODEL, 6, 10, _ascii_decoder(10)),
        Register(DEVICE_NAME, 16, 32, _ascii_decoder(32)),
    ),
)

# --------------------------------------------------------------------------
# EM component, three phase profile (registers 31000 - 31075)
# --------------------------------------------------------------------------
EM_TIMESTAMP: Final = "em_timestamp"
EM_PHASE_A_METER_ERROR: Final = "phase_a_meter_error"
EM_PHASE_B_METER_ERROR: Final = "phase_b_meter_error"
EM_PHASE_C_METER_ERROR: Final = "phase_c_meter_error"
EM_NEUTRAL_METER_ERROR: Final = "neutral_meter_error"
EM_PHASE_SEQUENCE_ERROR: Final = "phase_sequence_error"
EM_NEUTRAL_CURRENT: Final = "neutral_current"
EM_NEUTRAL_CURRENT_MISMATCH: Final = "neutral_current_mismatch"
EM_NEUTRAL_OVERCURRENT: Final = "neutral_overcurrent"
EM_TOTAL_CURRENT: Final = "total_current"
EM_TOTAL_ACT_POWER: Final = "total_act_power"
EM_TOTAL_APRT_POWER: Final = "total_aprt_power"

EM_START: Final = 1000
EM_SIZE: Final = 76
EM_PHASE_START: Final = 1020
EM_PHASE_STRIDE: Final = 20


def _em_phase_registers() -> tuple[Register, ...]:
    """Build the register definitions of the three EM phases."""
    registers: list[Register] = []
    for index, phase in enumerate(PHASES):
        base = EM_PHASE_START + index * EM_PHASE_STRIDE
        registers.extend(
            (
                Register(f"{phase}_voltage", base, 2, decode_float32),
                Register(f"{phase}_current", base + 2, 2, decode_float32),
                Register(f"{phase}_act_power", base + 4, 2, decode_float32),
                Register(f"{phase}_aprt_power", base + 6, 2, decode_float32),
                Register(f"{phase}_pf", base + 8, 2, decode_float32),
                Register(f"{phase}_overpower", base + 10, 1, decode_bool),
                Register(f"{phase}_overvoltage", base + 11, 1, decode_bool),
                Register(f"{phase}_overcurrent", base + 12, 1, decode_bool),
                Register(f"{phase}_freq", base + 13, 2, decode_float32),
            )
        )
    return tuple(registers)


EM_BLOCK: Final = RegisterBlock(
    key="em",
    address=EM_START,
    size=EM_SIZE,
    registers=(
        Register(EM_TIMESTAMP, 1000, 2, decode_uint32),
        Register(EM_PHASE_A_METER_ERROR, 1002, 1, decode_bool),
        Register(EM_PHASE_B_METER_ERROR, 1003, 1, decode_bool),
        Register(EM_PHASE_C_METER_ERROR, 1004, 1, decode_bool),
        Register(EM_NEUTRAL_METER_ERROR, 1005, 1, decode_bool),
        Register(EM_PHASE_SEQUENCE_ERROR, 1006, 1, decode_bool),
        Register(EM_NEUTRAL_CURRENT, 1007, 2, decode_float32),
        Register(EM_NEUTRAL_CURRENT_MISMATCH, 1009, 1, decode_bool),
        Register(EM_NEUTRAL_OVERCURRENT, 1010, 1, decode_bool),
        Register(EM_TOTAL_CURRENT, 1011, 2, decode_float32),
        Register(EM_TOTAL_ACT_POWER, 1013, 2, decode_float32),
        Register(EM_TOTAL_APRT_POWER, 1015, 2, decode_float32),
    )
    + _em_phase_registers(),
)

# --------------------------------------------------------------------------
# EMData component, three phase profile (registers 31160 - 31226)
# --------------------------------------------------------------------------
EM_DATA_TIMESTAMP: Final = "emdata_timestamp"
EM_DATA_TOTAL_ACT_ENERGY: Final = "total_act_energy"
EM_DATA_TOTAL_ACT_RET_ENERGY: Final = "total_act_ret_energy"

EM_DATA_START: Final = 1160
EM_DATA_SIZE: Final = 67
EM_DATA_PHASE_START: Final = 1170
EM_DATA_PHASE_STRIDE: Final = 20


def _em_data_phase_registers() -> tuple[Register, ...]:
    """Build the register definitions of the three EMData phases."""
    registers: list[Register] = []
    for index, phase in enumerate(PHASES):
        base = EM_DATA_PHASE_START + index * EM_DATA_PHASE_STRIDE
        registers.extend(
            (
                Register(f"{phase}_total_act_energy", base, 2, decode_float32),
                Register(f"{phase}_fund_act_energy", base + 2, 2, decode_float32),
                Register(f"{phase}_total_act_ret_energy", base + 4, 2, decode_float32),
                Register(f"{phase}_fund_act_ret_energy", base + 6, 2, decode_float32),
                Register(f"{phase}_lag_react_energy", base + 8, 2, decode_float32),
                Register(f"{phase}_lead_react_energy", base + 10, 2, decode_float32),
                Register(
                    f"{phase}_total_act_energy_perpetual", base + 12, 2, decode_float32
                ),
                Register(
                    f"{phase}_total_act_ret_energy_perpetual",
                    base + 14,
                    2,
                    decode_float32,
                ),
            )
        )
    return tuple(registers)


EM_DATA_BLOCK: Final = RegisterBlock(
    key="emdata",
    address=EM_DATA_START,
    size=EM_DATA_SIZE,
    registers=(
        Register(EM_DATA_TIMESTAMP, 1160, 2, decode_uint32),
        Register(EM_DATA_TOTAL_ACT_ENERGY, 1162, 2, decode_float32),
        Register(EM_DATA_TOTAL_ACT_RET_ENERGY, 1164, 2, decode_float32),
    )
    + _em_data_phase_registers(),
)

# --------------------------------------------------------------------------
# EM1 components, monophase profile (registers 32000 - 32057)
# --------------------------------------------------------------------------
EM1_START: Final = 2000
EM1_SIZE: Final = 60
EM1_STRIDE: Final = 20


def _em1_registers() -> tuple[Register, ...]:
    """Build the register definitions of the three EM1 components."""
    registers: list[Register] = []
    for index in range(len(PHASES)):
        prefix = f"em1_{index}"
        base = EM1_START + index * EM1_STRIDE
        registers.extend(
            (
                Register(f"{prefix}_timestamp", base, 2, decode_uint32),
                Register(f"{prefix}_error", base + 2, 1, decode_bool),
                Register(f"{prefix}_voltage", base + 3, 2, decode_float32),
                Register(f"{prefix}_current", base + 5, 2, decode_float32),
                Register(f"{prefix}_act_power", base + 7, 2, decode_float32),
                Register(f"{prefix}_aprt_power", base + 9, 2, decode_float32),
                Register(f"{prefix}_pf", base + 11, 2, decode_float32),
                Register(f"{prefix}_overpower", base + 13, 1, decode_bool),
                Register(f"{prefix}_overvoltage", base + 14, 1, decode_bool),
                Register(f"{prefix}_overcurrent", base + 15, 1, decode_bool),
                Register(f"{prefix}_freq", base + 16, 2, decode_float32),
            )
        )
    return tuple(registers)


EM1_BLOCK: Final = RegisterBlock(
    key="em1",
    address=EM1_START,
    size=EM1_SIZE,
    registers=_em1_registers(),
)

# --------------------------------------------------------------------------
# EM1Data components, monophase profile (registers 32300 - 32333)
# --------------------------------------------------------------------------
EM1_DATA_START: Final = 2300
EM1_DATA_SIZE: Final = 54
EM1_DATA_STRIDE: Final = 20


def _em1_data_registers() -> tuple[Register, ...]:
    """Build the register definitions of the three EM1Data components."""
    registers: list[Register] = []
    for index in range(len(PHASES)):
        prefix = f"em1data_{index}"
        base = EM1_DATA_START + index * EM1_DATA_STRIDE
        registers.extend(
            (
                Register(f"{prefix}_timestamp", base, 2, decode_uint32),
                Register(f"{prefix}_total_act_energy", base + 2, 2, decode_float32),
                Register(f"{prefix}_total_act_ret_energy", base + 4, 2, decode_float32),
                Register(f"{prefix}_lag_react_energy", base + 6, 2, decode_float32),
                Register(f"{prefix}_lead_react_energy", base + 8, 2, decode_float32),
                Register(
                    f"{prefix}_total_act_energy_perpetual", base + 10, 2, decode_float32
                ),
                Register(
                    f"{prefix}_total_act_ret_energy_perpetual",
                    base + 12,
                    2,
                    decode_float32,
                ),
            )
        )
    return tuple(registers)


EM1_DATA_BLOCK: Final = RegisterBlock(
    key="em1data",
    address=EM1_DATA_START,
    size=EM1_DATA_SIZE,
    registers=_em1_data_registers(),
)

#: The blocks that are polled for every profile.
PROFILE_BLOCKS: Final[dict[str, tuple[RegisterBlock, ...]]] = {
    PROFILE_TRIPHASE: (EM_BLOCK, EM_DATA_BLOCK),
    PROFILE_MONOPHASE: (EM1_BLOCK, EM1_DATA_BLOCK),
}
