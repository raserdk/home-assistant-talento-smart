# Reverse-engineering history

This document summarizes how the Home Assistant Talento Smart integration was developed.

## Goal

The original goal was simple: synchronize the timer clock from Home Assistant because the physical Talento timers could drift over time.

The project then expanded to:

- read the timer program
- decode switching records
- write program changes
- expose AUTO / OVR / FIX ON / FIX OFF
- build a Home Assistant Lovelace editor

## Android application analysis

The official Talento Smart Android application is a Xamarin/.NET application.

Reverse engineering identified two important Bluetooth classes used by the active Android code path:

```text
BluetoothConnectionNew
BluetoothLEServiceNew
```

The old Bluetooth connection path could therefore be excluded.

Methods and concepts investigated included:

```text
SendTimerProgram
WriteTimerProgramAsync
WriteQueuePart
WriteCharacteristicQueue
OnPacketCountValueChanged
PackageCreator
PackageReader
```

## First success: time synchronization

The time characteristic was identified as:

```text
EC040010-04DA-47E5-ADD4-8ED1C9D52FEC
```

The app sends current Unix time as a four-byte little-endian integer.

This became the first stable Home Assistant function.

## Program memory discovery

The program service was identified as:

```text
EC04000A-04DA-47E5-ADD4-8ED1C9D52FEC
```

with direction, package count, package counter, and a 14-byte content buffer.

A reliable read sequence was recovered:

```text
Direction READ (00)
wait ~500 ms
read package count once
read content exactly N times
```

This exposed complete 14-byte blocks and made it possible to decode the existing program.

## Program decoder

Observed packages revealed:

- header packages (`00`)
- switching-time packages (`08`)
- ON/OFF function codes
- weekday bit masks
- hour/minute fields
- sunset/astronomical markers

A semantic decoder was then added so Home Assistant could display events rather than raw bytes.

## Early write failures

Initial write implementations were unsafe and incomplete.

Observed failure modes included:

- a program being shortened
- unchanged records after a write attempt
- a single nonsensical/corrupt read-back record
- complete zero-filled program read-back

Those failures led to several safeguards:

- backup before writing
- semantic read-back verification
- raw byte diff diagnostics
- one-operation-at-a-time BLE locking
- write-status sensor

During this period the official phone application was used to restore known-good programs.

## Operating modes

APK analysis recovered operating-mode write values:

```text
AUTO    00
FIX ON  01
FIX OFF 02
OVR     03
```

A separate APK decoder showed that read-back values are composite and cannot be interpreted with the same table as writes.

After implementing the composite decoder, Home Assistant correctly displayed AUTO/FIX states.

## Bluetooth connection locking

At one point both timers remained visible in Home Assistant Bluetooth advertisements but active connections timed out.

A full Home Assistant host restart recovered the Bluetooth stack.

The integration was also changed to serialize all BLE work for each physical timer with one `asyncio.Lock`, preventing time sync, program reads, program writes, and mode operations from opening competing GATT sessions to the same device.

## HCI snoop breakthrough

Android Bluetooth HCI snoop logging provided the decisive write-protocol evidence.

The capture confirmed:

- exact characteristics/handles used by the official app
- ATT Write Request / Write Response for program content
- program block bytes matched the reverse-engineered encoder
- no hidden commit command after the last program block
- no required 8-packet acknowledgement from the counter characteristic
- approximately 600 ms pacing between content write starts

The timing was the missing piece.

Home Assistant writes had been completing at the API level in roughly 20–35 ms, causing the next content package to be transmitted much earlier than the official app would send it.

Once the integration reproduced the official app's ~600 ms request-to-request pacing, program writing succeeded in testing.

## Version milestones

### 0.1–0.2

- time sync
- basic BLE diagnostics

### 0.3–0.7

- program memory discovery
- raw program reading
- semantic decoder

### 0.8–0.10

- first editor/write attempts
- backup/read-back diagnostics
- several write-transport experiments

These builds were experimental and could truncate or corrupt program data.

### 0.11

- safer program read/write architecture
- operating modes
- custom Lovelace card
- composite operating-mode read decoder
- per-device BLE operation lock

### 0.12

- experiments around WithResponse / timing / package counter
- diagnostic GATT-property capture

### 0.13

- program-write timing based directly on Android HCI snoop capture
- ~600 ms request-to-request pacing
- successful program write in testing

### 1.0.0

- cleaned stable baseline
- HCI-verified write flow
- stale experimental UI/service wording removed
- GitHub documentation added

## Responsible sharing

Raw Android bugreports were intentionally not included in the repository. Such reports may contain private identifiers, Bluetooth addresses, device information, account details, or unrelated logs.

Only the protocol findings needed to reproduce the integration are documented here.
