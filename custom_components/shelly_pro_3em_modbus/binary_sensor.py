"""Binary sensor platform for the Shelly Pro 3EM Modbus integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ShellyPro3EMConfigEntry
from .const import (
    CONF_CREATE_DIAGNOSTIC_ENTITIES,
    EM_NEUTRAL_CURRENT_MISMATCH,
    EM_NEUTRAL_METER_ERROR,
    EM_NEUTRAL_OVERCURRENT,
    EM_PHASE_A_METER_ERROR,
    EM_PHASE_B_METER_ERROR,
    EM_PHASE_C_METER_ERROR,
    EM_PHASE_SEQUENCE_ERROR,
    PHASES,
    PROFILE_TRIPHASE,
)
from .coordinator import ShellyPro3EMCoordinator


@dataclass(frozen=True, kw_only=True)
class ShellyPro3EMBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes a Shelly Pro 3EM binary sensor entity."""

    register_key: str = ""


_PROBLEM: Final = {
    "device_class": BinarySensorDeviceClass.PROBLEM,
    "entity_category": EntityCategory.DIAGNOSTIC,
}

#: Alarm registers that exist for every phase of the EM component.
PHASE_ALARM_FIELDS: Final[tuple[tuple[str, str], ...]] = (
    ("overpower", "overpower"),
    ("overvoltage", "overvoltage"),
    ("overcurrent", "overcurrent"),
)


def _description(
    key: str,
    translation_key: str,
    placeholders: dict[str, str] | None = None,
) -> ShellyPro3EMBinarySensorEntityDescription:
    """Create a binary sensor description for a register key."""
    return ShellyPro3EMBinarySensorEntityDescription(
        key=key,
        register_key=key,
        translation_key=translation_key,
        translation_placeholders=placeholders,
        **_PROBLEM,
    )


def _triphase_binary_sensors() -> (
    tuple[ShellyPro3EMBinarySensorEntityDescription, ...]
):
    """Return the error flags of the EM component."""
    descriptions = [
        _description(EM_PHASE_A_METER_ERROR, "phase_meter_error", {"phase": "A"}),
        _description(EM_PHASE_B_METER_ERROR, "phase_meter_error", {"phase": "B"}),
        _description(EM_PHASE_C_METER_ERROR, "phase_meter_error", {"phase": "C"}),
        _description(EM_NEUTRAL_METER_ERROR, "neutral_meter_error"),
        _description(EM_PHASE_SEQUENCE_ERROR, "phase_sequence_error"),
        _description(EM_NEUTRAL_CURRENT_MISMATCH, "neutral_current_mismatch"),
        _description(EM_NEUTRAL_OVERCURRENT, "neutral_overcurrent"),
    ]
    for phase in PHASES:
        placeholders = {"phase": phase.upper()}
        descriptions.extend(
            _description(f"{phase}_{field}", f"phase_{name}", placeholders)
            for field, name in PHASE_ALARM_FIELDS
        )
    return tuple(descriptions)


def _monophase_binary_sensors() -> (
    tuple[ShellyPro3EMBinarySensorEntityDescription, ...]
):
    """Return the error flags of the EM1 components."""
    descriptions: list[ShellyPro3EMBinarySensorEntityDescription] = []
    for index in range(len(PHASES)):
        placeholders = {"channel": str(index + 1)}
        descriptions.append(
            _description(f"em1_{index}_error", "channel_error", placeholders)
        )
        descriptions.extend(
            _description(
                f"em1_{index}_{field}", f"channel_{name}", placeholders
            )
            for field, name in PHASE_ALARM_FIELDS
        )
    return tuple(descriptions)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ShellyPro3EMConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors of a Shelly Pro 3EM device."""
    if not entry.options.get(CONF_CREATE_DIAGNOSTIC_ENTITIES, True):
        return

    coordinator = entry.runtime_data
    descriptions = (
        _triphase_binary_sensors()
        if coordinator.profile == PROFILE_TRIPHASE
        else _monophase_binary_sensors()
    )
    async_add_entities(
        ShellyPro3EMBinarySensor(coordinator, description)
        for description in descriptions
    )


class ShellyPro3EMBinarySensor(
    CoordinatorEntity[ShellyPro3EMCoordinator], BinarySensorEntity
):
    """Binary sensor reporting an error flag of a Shelly energy meter."""

    _attr_has_entity_name = True
    entity_description: ShellyPro3EMBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: ShellyPro3EMCoordinator,
        description: ShellyPro3EMBinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
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
    def is_on(self) -> bool | None:
        """Return whether the error flag is set."""
        value: Any = self.coordinator.data.get(self.entity_description.register_key)
        return None if value is None else bool(value)
