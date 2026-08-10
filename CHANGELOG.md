# Changelog

## 1.0.0 — 2026-08-10

First stable baseline.

### Added

- Bluetooth discovery/config flow
- time synchronization
- timer-program reading and semantic decoding
- timer-program writing
- automatic backup before writes
- semantic and raw read-back verification
- AUTO / OVR / FIX ON / FIX OFF control
- composite operating-mode read decoder
- custom Lovelace program editor
- write-status diagnostics
- per-device BLE operation lock
- periodic time sync and program refresh

### Protocol validation

- Confirmed program writes use ATT Write Request / Write Response
- Confirmed approximately 600 ms request-to-request pacing used by the official Android app
- Confirmed no extra final commit write after the final program package
- Confirmed package-counter notification is diagnostic and not a mandatory `08 00` acknowledgement for the tested 8-package program

### Safety

- Program writes create a JSON backup first
- Program writes are verified by reconnecting and reading the program back
- A write is reported as failed when the decoded read-back does not match

## Development history

Earlier 0.x builds were reverse-engineering and test releases. Some early program-write builds could truncate or corrupt timer programs and should not be used.

See [docs/REVERSE_ENGINEERING.md](docs/REVERSE_ENGINEERING.md) for the full development history.
