# Shelly Pro 3EM (Modbus)

A custom [Home Assistant](https://www.home-assistant.io/) integration for the
**Shelly Pro 3EM** and **Shelly Pro 3EM-400** energy meters that talks to the
device over **Modbus TCP** (port 502).

The integration is configured completely in the UI, reads the registers that
Allterco Robotics documents for the `EM`, `EMData`, `EM1` and `EM1Data`
components and creates a device with all measurements, energies and error flags.

> This integration is not affiliated with Allterco Robotics. *Shelly* is a
> trademark of Allterco Robotics.

## Features

- **UI configuration** — host, port, Modbus unit ID; no YAML needed
- **Reconfigure and options flow** — change the connection, the polling interval,
  the timeout and which entity groups are created
- **Automatic profile detection** — detects whether the device runs the default
  `triphase` profile (one `EM` component) or the `monophase` profile (three `EM1`
  components) and creates the matching entities
- **Device information from the device** — MAC address, model code and device name are
  read from the registers, so the device in Home Assistant is identified by its
  serial number instead of its IP address. Devices that do not fill the name registers
  (the current firmware does not) get the friendly name of their model code
- **Per phase measurements** — voltage, current, active power, apparent power,
  power factor and frequency for each phase
- **Energies** — active, returned, reactive and fundamental energy per phase plus
  the totals, ready for the energy dashboard
- **Error flags** — meter errors, phase sequence error, neutral conductor errors
  and the overvoltage/overcurrent/overpower alarms per phase
- **One persistent connection** — the registers of a component are read in a
  single Modbus request per polling cycle, and a lost connection is re-established
  automatically
- **Diagnostics** — downloadable diagnostics with the device information, the
  current register values and the blocks that could not be read
- **Translations** — English and German

## Requirements

| Requirement | Value |
| --- | --- |
| Home Assistant | 2026.9 or newer |
| Shelly firmware | 1.1.0 or newer (Modbus support for the Pro 3EM) |
| Device setting | *Modbus TCP* enabled in the device web interface |
| Network | Port 502 reachable from the Home Assistant host |

## Installation

### HACS (recommended)

1. Open HACS and choose **Integrations**.
2. Open the three dot menu and choose **Custom repositories**.
3. Add `https://github.com/acdcnow/Shelly-Pro-3EM-Modbus-for-Home-Assistant` as
   repository with the category **Integration**.
4. Search for *Shelly Pro 3EM* in HACS, install it and restart Home Assistant.

### Manual

Copy the folder `custom_components/shelly_pro_3em_modbus` into the
`custom_components` folder of your Home Assistant configuration and restart Home
Assistant.

## Enable Modbus on the Shelly device

1. Open the web interface of the device (`http://<device ip>`) or the Shelly app.
2. Go to **Settings → Modbus** (newer firmware: **Settings → Connectivity →
   Modbus**) and enable it. The server listens on port 502.
3. Make sure the unit ID (slave address) matches the value you enter in Home
   Assistant. The Shelly default is `1`.

## Configuration

1. Go to **Settings → Devices & services → Add integration**.
2. Search for **Shelly Pro 3EM (Modbus)**.
3. Enter host, port and unit ID. The integration reads the device information
   registers and refuses to set up if the device does not answer or if it is not a
   Shelly device with an energy meter component.

### Options

| Option | Default | Description |
| --- | --- | --- |
| Polling interval | 10 s | How often the register blocks are read. |
| Connection timeout | 5 s | How long to wait for the answer of the device. |
| Create energy sensors | on | Create the energy sensors of the meter. |
| Create diagnostic entities | on | Create the diagnostic sensors, the error flags and the per phase details. |

Changing an option reloads the integration.

## Entities

### Triphase profile (default)

`EM` component (momentary values):

| Entity | Unit |
| --- | --- |
| Total current, neutral current | A |
| Total active power | W |
| Total apparent power | VA |
| Phase A/B/C voltage | V |
| Phase A/B/C current | A |
| Phase A/B/C active power | W |
| Phase A/B/C apparent power | VA |
| Phase A/B/C power factor | – |
| Phase A/B/C frequency | Hz |

`EMData` component (energies):

| Entity | Unit |
| --- | --- |
| Total active energy, total active returned energy (all phases) | Wh |
| Phase A/B/C total active energy, total active returned energy | Wh |
| Phase A/B/C active energy counter, active returned energy counter | Wh |
| Phase A/B/C fundamental active / returned energy | Wh |
| Phase A/B/C lagging / leading reactive energy | varh |

The per phase energies are the *perpetual* counters of the device, the values that
the Shelly app shows. The resettable counters and the fundamental energies are
disabled by default, the values are only needed for special use cases.

Diagnostic entities: *Last update*, *Last energy data update* and the error flags
*phase A/B/C meter error*, *neutral meter error*, *phase sequence error*,
*neutral current mismatch*, *neutral overcurrent* as well as *overpower*,
*overvoltage* and *overcurrent* per phase.

### Monophase profile

The same values are created per channel (`Channel 1` to `Channel 3`) from the three
`EM1` and `EM1Data` components. The per channel energies are the perpetual counters
of the device as well, the resettable counters are disabled by default.

Energies are provided in the unit that the device reports (`Wh` and `varh`).
Home Assistant converts them to your preferred unit for the display and for the
energy dashboard.

## Register map

All registers listed by Shelly for the Pro 3EM are **input registers** (Modbus
function code `4`) and 32 bit values are **big endian**.

Shelly documents the registers with the `3xxxx` reference convention
(`31020` = phase A voltage). A Modbus request uses the protocol address, which is
the documented number minus `30000`, so phase A voltage is read from address
`1020`. This is the same convention that Shelly uses in its own examples
(`modbus <ip> i@1020/f`).

| Documented | Protocol address | Content |
| --- | --- | --- |
| 30000 | 0 | MAC address (6 registers, ASCII) |
| 30006 | 6 | Model (10 registers, ASCII) |
| 30016 | 16 | Device name (32 registers, ASCII) |
| 31000 | 1000 | `EM` timestamp and momentary values (76 registers) |
| 31020 / 31040 / 31060 | 1020 / 1040 / 1060 | Phase A / B / C of the momentary values |
| 31160 | 1160 | `EMData` timestamp and total energies (67 registers) |
| 31170 / 31190 / 31210 | 1170 / 1190 / 1210 | Phase A / B / C energies |
| 32000 + 20·n | 2000 + 20·n | `EM1` component `n` of a monophase device (20 registers each) |
| 32300 + 20·n | 2300 + 20·n | `EM1Data` component `n` of a monophase device (20 registers each) |

Sources:

- [Shelly API documentation — EM component](https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/EM)
- [Shelly API documentation — EMData component](https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/EMData)
- [Shelly API documentation — EM1 component](https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/EM1)
- [Shelly API documentation — EM1Data component](https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/EM1Data)
- [Shelly API documentation — Modbus](https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/Modbus)

### Byte order

The byte order was verified against a real Shelly Pro 3EM (firmware 2.1.0-beta1):

- 32 bit values are stored in the **CDAB** order, the low word comes first and every
  word is big endian. `0x4369 0xA260` is 233.63 V. Shelly itself uses this mode in its
  tool examples: `modbus -B mixed <ip> i@1020/f`.
- ASCII strings hold two characters per register with the **low byte first**, `0x4345`
  is `"EC"`, and are terminated with a zero byte. The MAC address of a real device
  decodes to `EC6260975A68` and its model code to `SPEM-003CEBEU`.

This matters when you build your own template sensors or YAML modbus entries for
these registers: in the Home Assistant modbus integration the 32 bit values need
`swap: word`.

## Verified against real hardware

The integration was checked against a physical Shelly Pro 3EM (firmware
2.1.0-beta1, model code `SPEM-003CEBEU`) while it was measuring a real three phase
installation. The register values were compared with the values of the device's own
API:

| Value | Modbus registers | Device API (`em:0` / `emdata:0`) |
| --- | --- | --- |
| Phase A voltage | 233.47 V | 233.2 V |
| Phase B current | 0.783 A | 0.782 A |
| Phase C active power | 140.20 W | 140.2 W |
| Phase A power factor | 0.621 | 0.62 |
| Frequency | 49.99 Hz | 50.0 Hz |
| Phase A total active energy | 882.99 Wh | 882.99 Wh |
| Total active energy (all phases) | 7852.95 Wh | 7852.95 Wh |
| Phase A returned energy | 6527.89 Wh | 6527.89 Wh |

The remaining difference of the momentary values comes from the two readings being
taken a moment apart while the load changes.

## Troubleshooting

| Problem | Cause and solution |
| --- | --- |
| `Failed to connect to the Modbus server` | Modbus TCP is not enabled on the device, the port is wrong or another master already holds the connection. Check *Settings → Modbus* on the device. |
| `The device responded, but it is not a Shelly device...` | Modbus is enabled at that address but it is not a Shelly Pro 3EM. |
| Entities become `unavailable` | The register block could not be read (network hiccup, polling interval smaller than the device response time). Increase the polling interval or the timeout. The *diagnostics* show which block failed. |
| Only some entities exist | *Create energy sensors* or *Create diagnostic entities* is disabled in the options. |
| Values changed after switching the profile on the device | The integration detects the profile change after a few failed polls and reloads itself. This can also be triggered by reloading the integration manually. |

## Development

The repository ships a simulated Shelly Pro 3EM Modbus server
(`tests/modbus_server.py`) and a test suite with three layers:

- `tests/test_register_map.py` verifies every register address and size against
  the register tables published by Shelly
- `tests/test_client.py` runs the real Modbus client against the simulated device
- `tests/test_integration.py` sets the integration up inside a real Home Assistant
  (through the official `pytest-homeassistant-custom-component` harness) and checks
  the config flow, the entities, the options flow, the reload and the unload

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements_test.txt
.venv/Scripts/python -m pytest tests
```

> On Windows run `python scripts/setup_windows_test_env.py` once before the tests:
> Home Assistant and its test harness only support Linux and macOS, they import the
> Unix only modules `fcntl` and `resource` at import time and the script writes the
> minimal shims for them into the virtual environment.

The brand images in `custom_components/shelly_pro_3em_modbus/brand` are generated
by `scripts/generate_brand_assets.py` (requires Pillow).

## License

[MIT](LICENSE)
