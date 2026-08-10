# Talento Smart for Home Assistant

Unofficial Home Assistant integration for **Grässlin Talento Smart** Bluetooth time switches.

The integration was built by reverse-engineering the official Android app and validating the BLE timing with Android Bluetooth HCI snoop captures. It supports reading and writing timer programs, time synchronization, and operating-mode control directly from Home Assistant.

> This project is not affiliated with or endorsed by Grässlin.

## Features

- Automatic Bluetooth discovery of Talento Smart devices
- Manual setup by Bluetooth MAC address
- Read complete timer programs from the device
- Edit and write timer programs from Home Assistant
- Automatic JSON backup before every program write
- Read-back verification after every program write
- Time synchronization from Home Assistant to the timer
- Operating modes:
  - AUTO
  - OVR
  - FIX ON
  - FIX OFF
- Custom Lovelace program editor card
- Diagnostic write-status sensor
- Per-device BLE operation locking to avoid overlapping GATT sessions
- Automatic time sync and periodic program refresh

## Tested scope

Version 1.1.0 has been tested with Talento Smart devices using one program and channel 1.

The current encoder supports:

- normal ON/OFF clock events
- sunset-based events
- weekday masks
- program name
- program priority

Date-range program features are not currently implemented.

## Installation

### HACS — recommended

1. Add this repository to HACS as a **Custom repository → Integration**.
2. Install **Talento Smart**.
3. Restart Home Assistant.
4. Add **Talento Smart** under **Settings → Devices & services**.

**Done.**

The Lovelace card is bundled inside the integration, served by Home Assistant,
and loaded automatically at startup. There is no `/config/www/` copy and no
manual Dashboard Resource to add.

### Manual installation

Copy:

```text
custom_components/talento_smart/
```

to:

```text
/config/custom_components/talento_smart/
```

Restart Home Assistant and add the integration. The frontend card is loaded
automatically.

## Lovelace card

Example:

```yaml
type: custom:talento-smart-card
entity: sensor.my_talento_timerprogram
mode_entity: select.my_talento_driftstilstand
```

`mode_entity` is optional if the card can identify the matching operating-mode select automatically.

The card provides:

- Read program
- Sync time
- AUTO / OVR / FIX ON / FIX OFF
- Program-name editing
- Add/remove switching times
- Weekday selection
- Clock and sunset events
- Write program to Talento

## Safety during program writes

Before every write, Home Assistant reads the current timer program and stores a JSON backup under:

```text
/config/talento_smart_backups/
```

After writing, the integration disconnects, reconnects, reads the program back, decodes it, and compares it with the requested program. A write is only reported as successful when the semantic read-back matches.

The `Skrivestatus` sensor contains detailed diagnostics if a write fails.

## BLE protocol summary

The protocol was reconstructed from the official Talento Smart Android app and confirmed with Android Bluetooth HCI snoop captures.

### Program service

```text
Service:       EC04000A-04DA-47E5-ADD4-8ED1C9D52FEC
Direction:     EC04000B-04DA-47E5-ADD4-8ED1C9D52FEC
Package count: EC04000C-04DA-47E5-ADD4-8ED1C9D52FEC
Counter:       EC04000D-04DA-47E5-ADD4-8ED1C9D52FEC
Content:       EC04000E-04DA-47E5-ADD4-8ED1C9D52FEC
```

### Time characteristic

```text
EC040010-04DA-47E5-ADD4-8ED1C9D52FEC
```

Time is sent as a 4-byte little-endian Unix timestamp.

### Operating mode

Channel selection:

```text
EC040004-04DA-47E5-ADD4-8ED1C9D52FEC
```

Operating state:

```text
EC040008-04DA-47E5-ADD4-8ED1C9D52FEC
```

Write values:

| Mode | Value |
|---|---:|
| AUTO | `00` |
| FIX ON | `01` |
| FIX OFF | `02` |
| OVR | `03` |

See [docs/PROTOCOL.md](docs/PROTOCOL.md) for the detailed protocol notes.

## Why program writing needs ~600 ms pacing

A key reverse-engineering result was that a successful official-app write does **not** send program blocks as quickly as the BLE stack allows.

The HCI trace showed approximately:

```text
Direction WRITE
~600 ms
PackageCount
~600 ms
Program header
~600 ms start-to-start
Program block 1
~600 ms start-to-start
Program block 2
...
```

The integration therefore deliberately maintains roughly **600 ms from the start of one content write to the start of the next** using ATT Write Request / Write Response.

Sending the packets substantially faster caused incomplete or invalid program buffers during development.

## Services

The integration registers:

```text
talento_smart.read_program
talento_smart.sync_time
talento_smart.write_program
talento_smart.read_mode
talento_smart.set_mode
```

## Diagnostics

Useful entities include:

- Timerprogram sensor
- Skrivestatus sensor
- Driftstilstand select
- Hent timerprogram button
- Synkroniser tid button

The write-status sensor can show:

- requested program
- expected raw blocks
- read-back program
- read-back raw blocks
- byte differences
- BLE write timing
- program backup filename

## Reverse engineering

The development history and important findings are documented in:

- [docs/REVERSE_ENGINEERING.md](docs/REVERSE_ENGINEERING.md)
- [docs/PROTOCOL.md](docs/PROTOCOL.md)
- [CHANGELOG.md](CHANGELOG.md)

## Privacy

Do not upload Android bugreports or Bluetooth HCI captures publicly without checking them first. Android bugreports can contain device identifiers and other private system information.

## License

No open-source license has been selected yet. Add a license before accepting external redistribution or contributions under specific terms.
