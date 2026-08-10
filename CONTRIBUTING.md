# Contributing

Thanks for helping improve Talento Smart support.

## Useful contributions

- reports from other Talento Smart models
- sanitized Bluetooth HCI captures
- decoded program/event types not currently supported
- Home Assistant compatibility fixes
- Lovelace card improvements

## Please remove private information

Do not attach raw Android bugreports publicly unless you have inspected and sanitized them first.

At minimum remove or review:

- Bluetooth MAC addresses
- Wi-Fi identifiers
- account/e-mail information
- device serial numbers
- unrelated application logs
- location information

## Program-write changes

Program writes can change the timer's persistent schedule. Any pull request that changes the write transport should preserve:

- backup before write
- per-device operation locking
- read-back verification
- failure diagnostics

Changes to packet timing should be supported by an official-app capture or equivalent evidence rather than trial-and-error on production schedules.
