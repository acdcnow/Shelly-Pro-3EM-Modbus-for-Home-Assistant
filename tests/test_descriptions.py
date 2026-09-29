"""Tests for the entity descriptions of the integration.

Every entity needs a register that exists in the register map and a translation
key that exists in ``strings.json``, otherwise Home Assistant shows the raw key
instead of a name.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Final

import pytest

from custom_components.shelly_pro_3em_modbus import binary_sensor as binary_sensor_module
from custom_components.shelly_pro_3em_modbus import sensor as sensor_module
from custom_components.shelly_pro_3em_modbus.const import (
    DEVICE_INFO_BLOCK,
    EM_BLOCK,
    EM_DATA_BLOCK,
    EM1_BLOCK,
    EM1_DATA_BLOCK,
)

COMPONENT_DIR: Final = Path(sensor_module.__file__).parent
STRINGS: Final = json.loads((COMPONENT_DIR / "strings.json").read_text("utf-8"))

REGISTER_KEYS: Final = frozenset(
    key
    for block in (DEVICE_INFO_BLOCK, EM_BLOCK, EM_DATA_BLOCK, EM1_BLOCK, EM1_DATA_BLOCK)
    for key in block.keys
)

SENSOR_DESCRIPTIONS: Final = (
    sensor_module._triphase_momentary_sensors()
    + sensor_module._triphase_energy_sensors()
    + sensor_module._triphase_diagnostic_sensors()
    + sensor_module._monophase_momentary_sensors()
    + sensor_module._monophase_energy_sensors()
    + sensor_module._monophase_diagnostic_sensors()
)

BINARY_SENSOR_DESCRIPTIONS: Final = (
    binary_sensor_module._triphase_binary_sensors()
    + binary_sensor_module._monophase_binary_sensors()
)


@pytest.mark.parametrize(
    ("domain", "descriptions"),
    [
        ("sensor", SENSOR_DESCRIPTIONS),
        ("binary_sensor", BINARY_SENSOR_DESCRIPTIONS),
    ],
)
def test_description_keys_are_unique(domain: str, descriptions: tuple[Any, ...]) -> None:
    """No two entities share the same key."""
    keys = [description.key for description in descriptions]
    assert len(keys) == len(set(keys))


@pytest.mark.parametrize(
    ("domain", "descriptions"),
    [
        ("sensor", SENSOR_DESCRIPTIONS),
        ("binary_sensor", BINARY_SENSOR_DESCRIPTIONS),
    ],
)
def test_descriptions_use_documented_registers(
    domain: str, descriptions: tuple[Any, ...]
) -> None:
    """Every entity reads a register that is part of the register map."""
    for description in descriptions:
        assert description.register_key in REGISTER_KEYS, description.key


@pytest.mark.parametrize(
    ("domain", "descriptions"),
    [
        ("sensor", SENSOR_DESCRIPTIONS),
        ("binary_sensor", BINARY_SENSOR_DESCRIPTIONS),
    ],
)
def test_translations_exist(domain: str, descriptions: tuple[Any, ...]) -> None:
    """Every entity has a translated name."""
    translations = STRINGS["entity"][domain]
    for description in descriptions:
        assert description.translation_key, description.key
        assert description.translation_key in translations, description.translation_key


@pytest.mark.parametrize(
    ("domain", "descriptions"),
    [
        ("sensor", SENSOR_DESCRIPTIONS),
        ("binary_sensor", BINARY_SENSOR_DESCRIPTIONS),
    ],
)
def test_translation_placeholders_match(
    domain: str, descriptions: tuple[Any, ...]
) -> None:
    """The placeholders of a description match the placeholders of its name."""
    translations = STRINGS["entity"][domain]
    for description in descriptions:
        name: str = translations[description.translation_key]["name"]
        expected = set(re.findall(r"\{(\w+)\}", name))
        given = set(description.translation_placeholders or {})
        assert expected == given, (
            f"{description.key}: {expected} != {given} ({name})"
        )


def test_all_translations_of_strings_json_are_used() -> None:
    """Translations are only defined for entities that are created."""
    used_sensor_keys = {d.translation_key for d in SENSOR_DESCRIPTIONS}
    used_binary_sensor_keys = {d.translation_key for d in BINARY_SENSOR_DESCRIPTIONS}

    assert set(STRINGS["entity"]["sensor"]) == used_sensor_keys
    assert set(STRINGS["entity"]["binary_sensor"]) == used_binary_sensor_keys


def test_translated_languages_are_complete() -> None:
    """All translated files provide the same keys as strings.json."""
    translations_dir = COMPONENT_DIR / "translations"
    for path in translations_dir.glob("*.json"):
        content = json.loads(path.read_text("utf-8"))
        assert set(content["entity"]["sensor"]) == set(STRINGS["entity"]["sensor"]), path
        assert set(content["entity"]["binary_sensor"]) == set(
            STRINGS["entity"]["binary_sensor"]
        ), path


def test_default_enabled_entities() -> None:
    """Most entities are enabled by default, only proven extras are not."""
    disabled = [
        description.key
        for description in SENSOR_DESCRIPTIONS
        if not description.entity_registry_enabled_default
    ]
    assert set(disabled) == {
        "a_fund_act_energy",
        "b_fund_act_energy",
        "c_fund_act_energy",
        "a_fund_act_ret_energy",
        "b_fund_act_ret_energy",
        "c_fund_act_ret_energy",
        "a_total_act_energy_perpetual",
        "b_total_act_energy_perpetual",
        "c_total_act_energy_perpetual",
        "a_total_act_ret_energy_perpetual",
        "b_total_act_ret_energy_perpetual",
        "c_total_act_ret_energy_perpetual",
        "em1data_0_total_act_energy_perpetual",
        "em1data_1_total_act_energy_perpetual",
        "em1data_2_total_act_energy_perpetual",
        "em1data_0_total_act_ret_energy_perpetual",
        "em1data_1_total_act_ret_energy_perpetual",
        "em1data_2_total_act_ret_energy_perpetual",
    }
