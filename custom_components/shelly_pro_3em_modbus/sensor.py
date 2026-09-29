"""Sensor platform for the Shelly Pro 3EM Modbus integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfApparentPower,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfReactiveEnergy,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import ShellyPro3EMConfigEntry
from .const import (
    CONF_CREATE_DIAGNOSTIC_ENTITIES,
    CONF_CREATE_ENERGY_ENTITIES,
    EM_DATA_TIMESTAMP,
    EM_DATA_TOTAL_ACT_ENERGY,
    EM_DATA_TOTAL_ACT_RET_ENERGY,
    EM_NEUTRAL_CURRENT,
    EM_TIMESTAMP,
    EM_TOTAL_ACT_POWER,
    EM_TOTAL_APRT_POWER,
    EM_TOTAL_CURRENT,
    PHASES,
    PROFILE_TRIPHASE,
)
from .coordinator import ShellyPro3EMCoordinator


@dataclass(frozen=True, kw_only=True)
class ShellyPro3EMSensorEntityDescription(SensorEntityDescription):
    """Describes a Shelly Pro 3EM sensor entity."""

    register_key: str = ""
    value_fn: Callable[[Any], Any] | None = None


def _timestamp(value: Any) -> datetime | None:
    """Convert a Unix timestamp register to a datetime."""
    if not isinstance(value, int | float) or isinstance(value, bool) or value <= 0:
        return None
    return dt_util.utc_from_timestamp(value)


_VOLTAGE: Final = {
    "device_class": SensorDeviceClass.VOLTAGE,
    "native_unit_of_measurement": UnitOfElectricPotential.VOLT,
    "state_class": SensorStateClass.MEASUREMENT,
    "suggested_display_precision": 1,
}
_CURRENT: Final = {
    "device_class": SensorDeviceClass.CURRENT,
    "native_unit_of_measurement": UnitOfElectricCurrent.AMPERE,
    "state_class": SensorStateClass.MEASUREMENT,
    "suggested_display_precision": 2,
}
_POWER: Final = {
    "device_class": SensorDeviceClass.POWER,
    "native_unit_of_measurement": UnitOfPower.WATT,
    "state_class": SensorStateClass.MEASUREMENT,
    "suggested_display_precision": 1,
}
_APPARENT_POWER: Final = {
    "device_class": SensorDeviceClass.APPARENT_POWER,
    "native_unit_of_measurement": UnitOfApparentPower.VOLT_AMPERE,
    "state_class": SensorStateClass.MEASUREMENT,
    "suggested_display_precision": 1,
}
_POWER_FACTOR: Final = {
    "device_class": SensorDeviceClass.POWER_FACTOR,
    "state_class": SensorStateClass.MEASUREMENT,
    "suggested_display_precision": 3,
}
_FREQUENCY: Final = {
    "device_class": SensorDeviceClass.FREQUENCY,
    "native_unit_of_measurement": UnitOfFrequency.HERTZ,
    "state_class": SensorStateClass.MEASUREMENT,
    "suggested_display_precision": 2,
}
_ENERGY: Final = {
    "device_class": SensorDeviceClass.ENERGY,
    "native_unit_of_measurement": UnitOfEnergy.WATT_HOUR,
    "state_class": SensorStateClass.TOTAL_INCREASING,
    "suggested_display_precision": 1,
}
_REACTIVE_ENERGY: Final = {
    "device_class": SensorDeviceClass.REACTIVE_ENERGY,
    "native_unit_of_measurement": UnitOfReactiveEnergy.VOLT_AMPERE_REACTIVE_HOUR,
    "state_class": SensorStateClass.TOTAL_INCREASING,
    "suggested_display_precision": 1,
}
_ENERGY_DISABLED: Final = {**_ENERGY, "entity_registry_enabled_default": False}
_TIMESTAMP: Final = {
    "device_class": SensorDeviceClass.TIMESTAMP,
    "entity_category": EntityCategory.DIAGNOSTIC,
    "value_fn": _timestamp,
}

#: Momentary values of a phase (EM) or a channel (EM1).
MOMENTARY_FIELDS: Final[tuple[tuple[str, str, dict[str, Any]], ...]] = (
    ("voltage", "voltage", _VOLTAGE),
    ("current", "current", _CURRENT),
    ("act_power", "active_power", _POWER),
    ("aprt_power", "apparent_power", _APPARENT_POWER),
    ("pf", "power_factor", _POWER_FACTOR),
    ("freq", "frequency", _FREQUENCY),
)

#: Energy values of a phase of the EMData component.
EM_DATA_ENERGY_FIELDS: Final[tuple[tuple[str, str, dict[str, Any]], ...]] = (
    ("total_act_energy", "total_active_energy", _ENERGY),
    ("total_act_ret_energy", "total_active_returned_energy", _ENERGY),
)

#: Diagnostic energy values of a phase of the EMData component.
EM_DATA_DIAGNOSTIC_ENERGY_FIELDS: Final[
    tuple[tuple[str, str, dict[str, Any]], ...]
] = (
    ("fund_act_energy", "fundamental_active_energy", _ENERGY_DISABLED),
    ("fund_act_ret_energy", "fundamental_active_returned_energy", _ENERGY_DISABLED),
    ("lag_react_energy", "lagging_reactive_energy", _REACTIVE_ENERGY),
    ("lead_react_energy", "leading_reactive_energy", _REACTIVE_ENERGY),
    ("total_act_energy_perpetual", "perpetual_active_energy", _ENERGY_DISABLED),
    (
        "total_act_ret_energy_perpetual",
        "perpetual_active_returned_energy",
        _ENERGY_DISABLED,
    ),
)

#: Energy values of an EM1Data component of a monophase device.
EM1_DATA_ENERGY_FIELDS: Final[tuple[tuple[str, str, dict[str, Any]], ...]] = (
    ("total_act_energy", "total_active_energy", _ENERGY),
    ("total_act_ret_energy", "total_active_returned_energy", _ENERGY),
)

#: Diagnostic energy values of an EM1Data component of a monophase device.
EM1_DATA_DIAGNOSTIC_ENERGY_FIELDS: Final[
    tuple[tuple[str, str, dict[str, Any]], ...]
] = (
    ("lag_react_energy", "lagging_reactive_energy", _REACTIVE_ENERGY),
    ("lead_react_energy", "leading_reactive_energy", _REACTIVE_ENERGY),
    ("total_act_energy_perpetual", "perpetual_active_energy", _ENERGY_DISABLED),
    (
        "total_act_ret_energy_perpetual",
        "perpetual_active_returned_energy",
        _ENERGY_DISABLED,
    ),
)


def _description(
    key: str, translation_key: str, **kwargs: Any
) -> ShellyPro3EMSensorEntityDescription:
    """Create a sensor description for a register key."""
    return ShellyPro3EMSensorEntityDescription(
        key=key, register_key=key, translation_key=translation_key, **kwargs
    )


def _component_sensors(
    key_prefix: str,
    translation_prefix: str,
    fields: tuple[tuple[str, str, dict[str, Any]], ...],
    placeholder: str,
) -> tuple[ShellyPro3EMSensorEntityDescription, ...]:
    """Build the descriptions of the three phases or channels of a component.

    ``key_prefix`` is empty for the triphase EM/EMData registers (keys such as
    ``a_voltage``) and ``em1``/``em1data`` for the monophase registers (keys such
    as ``em1_0_voltage``).  ``translation_prefix`` is ``phase`` or ``channel``.
    """
    descriptions: list[ShellyPro3EMSensorEntityDescription] = []
    for index, phase in enumerate(PHASES):
        if key_prefix:
            key_start = f"{key_prefix}_{index}"
            placeholders = {placeholder: str(index + 1)}
        else:
            key_start = phase
            placeholders = {placeholder: phase.upper()}
        descriptions.extend(
            _description(
                f"{key_start}_{field}",
                f"{translation_prefix}_{name}",
                translation_placeholders=placeholders,
                **kwargs,
            )
            for field, name, kwargs in fields
        )
    return tuple(descriptions)


def _triphase_momentary_sensors() -> tuple[ShellyPro3EMSensorEntityDescription, ...]:
    """Return the momentary sensors of the EM component."""
    return (
        _description(EM_TOTAL_CURRENT, "total_current", **_CURRENT),
        _description(EM_TOTAL_ACT_POWER, "total_active_power", **_POWER),
        _description(EM_TOTAL_APRT_POWER, "total_apparent_power", **_APPARENT_POWER),
        _description(EM_NEUTRAL_CURRENT, "neutral_current", **_CURRENT),
    ) + _component_sensors("", "phase", MOMENTARY_FIELDS, "phase")


def _triphase_energy_sensors() -> tuple[ShellyPro3EMSensorEntityDescription, ...]:
    """Return the energy sensors of the EMData component."""
    return (
        _description(EM_DATA_TOTAL_ACT_ENERGY, "total_active_energy", **_ENERGY),
        _description(
            EM_DATA_TOTAL_ACT_RET_ENERGY, "total_active_returned_energy", **_ENERGY
        ),
    ) + _component_sensors("", "phase", EM_DATA_ENERGY_FIELDS, "phase")


def _triphase_diagnostic_sensors() -> tuple[ShellyPro3EMSensorEntityDescription, ...]:
    """Return the diagnostic sensors of a triphase device."""
    return (
        _description(EM_TIMESTAMP, "last_update", **_TIMESTAMP),
        _description(EM_DATA_TIMESTAMP, "energy_last_update", **_TIMESTAMP),
    ) + _component_sensors("", "phase", EM_DATA_DIAGNOSTIC_ENERGY_FIELDS, "phase")


def _monophase_momentary_sensors() -> tuple[ShellyPro3EMSensorEntityDescription, ...]:
    """Return the momentary sensors of the EM1 components."""
    return _component_sensors("em1", "channel", MOMENTARY_FIELDS, "channel")


def _monophase_energy_sensors() -> tuple[ShellyPro3EMSensorEntityDescription, ...]:
    """Return the energy sensors of the EM1Data components."""
    return _component_sensors("em1data", "channel", EM1_DATA_ENERGY_FIELDS, "channel")


def _monophase_diagnostic_sensors() -> tuple[ShellyPro3EMSensorEntityDescription, ...]:
    """Return the diagnostic sensors of a monophase device."""
    return (
        _component_sensors(
            "em1", "channel", (("timestamp", "last_update", _TIMESTAMP),), "channel"
        )
        + _component_sensors(
            "em1data",
            "channel",
            (("timestamp", "energy_last_update", _TIMESTAMP),),
            "channel",
        )
        + _component_sensors(
            "em1data", "channel", EM1_DATA_DIAGNOSTIC_ENERGY_FIELDS, "channel"
        )
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ShellyPro3EMConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors of a Shelly Pro 3EM device."""
    coordinator = entry.runtime_data
    triphase = coordinator.profile == PROFILE_TRIPHASE

    descriptions: list[ShellyPro3EMSensorEntityDescription] = list(
        _triphase_momentary_sensors()
        if triphase
        else _monophase_momentary_sensors()
    )

    if entry.options.get(CONF_CREATE_ENERGY_ENTITIES, True):
        descriptions.extend(
            _triphase_energy_sensors() if triphase else _monophase_energy_sensors()
        )

    if entry.options.get(CONF_CREATE_DIAGNOSTIC_ENTITIES, True):
        descriptions.extend(
            _triphase_diagnostic_sensors()
            if triphase
            else _monophase_diagnostic_sensors()
        )

    async_add_entities(
        ShellyPro3EMSensor(coordinator, description) for description in descriptions
    )


class ShellyPro3EMSensor(CoordinatorEntity[ShellyPro3EMCoordinator], SensorEntity):
    """Sensor reading a single register of a Shelly energy meter."""

    _attr_has_entity_name = True
    entity_description: ShellyPro3EMSensorEntityDescription

    def __init__(
        self,
        coordinator: ShellyPro3EMCoordinator,
        description: ShellyPro3EMSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.device.mac}_{description.key}"

    @property
    def available(self) -> bool:
        """Return whether the register was read during the last poll."""
        return (
            super().available
            and self.entity_description.register_key in self.coordinator.data
        )

    @property
    def native_value(self) -> Any:
        """Return the value of the register.

        The registers of the device are 32 bit floats, which carry a small
        quantization error (``230.100006`` for 230.1 V).  Values are rounded to the
        precision that is suggested for the display, so the state and the display
        agree.
        """
        value = self.coordinator.data.get(self.entity_description.register_key)
        if value is None:
            return None
        if (value_fn := self.entity_description.value_fn) is not None:
            return value_fn(value)
        if isinstance(value, float) and (
            precision := self.entity_description.suggested_display_precision
        ) is not None:
            return round(value, precision)
        return value
