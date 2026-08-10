# Talento Smart for Home Assistant 1.0.0

First stable release of the unofficial Grässlin Talento Smart Bluetooth integration for Home Assistant.

Highlights:

- read and edit Talento timer programs
- write programs with official-app HCI-verified timing
- automatic backup and read-back verification
- AUTO / OVR / FIX ON / FIX OFF
- time synchronization
- Lovelace program editor
- detailed diagnostics

The key write fix is approximately 600 ms start-to-start pacing between 14-byte program blocks, matching the official Android app's Bluetooth HCI traffic.
