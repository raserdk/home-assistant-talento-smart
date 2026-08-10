# Talento Smart BLE protocol notes

These notes describe the subset of the Grässlin Talento Smart BLE protocol implemented in version 1.0.0.

The information was reconstructed from the official Android application and validated against Bluetooth HCI snoop traffic captured while the official app communicated with a Talento Smart timer.

## Services and characteristics

### Configuration service

```text
EC040000-04DA-47E5-ADD4-8ED1C9D52FEC
```

Known characteristics:

| Purpose | UUID |
|---|---|
| Channel select | `EC040004-04DA-47E5-ADD4-8ED1C9D52FEC` |
| Channel state/mode | `EC040008-04DA-47E5-ADD4-8ED1C9D52FEC` |
| Time | `EC040010-04DA-47E5-ADD4-8ED1C9D52FEC` |
| PIN/status | `EC040017-04DA-47E5-ADD4-8ED1C9D52FEC` |

### Program/memory service

```text
EC04000A-04DA-47E5-ADD4-8ED1C9D52FEC
```

| Purpose | UUID |
|---|---|
| Direction | `EC04000B-04DA-47E5-ADD4-8ED1C9D52FEC` |
| Package count | `EC04000C-04DA-47E5-ADD4-8ED1C9D52FEC` |
| Package counter / notify | `EC04000D-04DA-47E5-ADD4-8ED1C9D52FEC` |
| 14-byte content buffer | `EC04000E-04DA-47E5-ADD4-8ED1C9D52FEC` |

## Time synchronization

The official app writes current Unix time as exactly four bytes, little-endian:

```text
uint32 little-endian Unix seconds
```

Example Python representation:

```python
struct.pack("<I", unix_seconds)
```

## Operating mode

The app first selects channel 1 by writing:

```text
01
```

to `EC040004`.

It then writes the requested operating mode to `EC040008`:

| Requested mode | Write byte |
|---|---:|
| AUTO | `00` |
| FIX ON | `01` |
| FIX OFF | `02` |
| OVR | `03` |

### Read-back is composite

The read value from `EC040008` is not encoded the same way as the write command.

The decoder recovered from the Android app maps channel type approximately as follows:

| Raw values | Decoded mode |
|---|---|
| `0,1,6,7,8,9` and default/unknown | AUTO |
| `4,5,12,13` | OVR |
| `2,10` | FIX ON |
| `3,11` | FIX OFF |

The relay-state decoder reports relay ON for raw values `1`, `2`, and `4`.

## Program read

Verified flow:

1. Read PIN/status as the official app does on connect.
2. Write direction READ:

   ```text
   00
   ```

   to `EC04000B`.
3. Wait about 500 ms.
4. Read `EC04000C` exactly once.
5. Decode the two-byte little-endian package count.
6. Read `EC04000E` exactly `package_count` times.

Each content package is 14 bytes.

## Program write

Verified from an official-app HCI capture:

1. Write direction WRITE to `EC04000B`:

   ```text
   01
   ```

2. Wait about 600 ms.
3. Write package count as little-endian `uint16` to `EC04000C`.
4. Enable notification/counter diagnostics on `EC04000D`.
5. Wait about 600 ms before the first content package.
6. Write each 14-byte package to `EC04000E` using ATT Write Request / Write Response.
7. Maintain roughly 600 ms **start-to-start** between content writes.
8. No additional commit command was observed after the final content package.
9. Disconnect/reconnect and read the program back for verification.

`EC04000D` did not produce a mandatory `package_count` acknowledgement for the tested normal 8-package transfer. It is therefore treated as diagnostic rather than a required commit signal.

## Program package structure

### Header

A typical program header:

```text
00 00 50 72 6F 67 31 00 00 00 00 00 00 00
```

This contains program name `Prog1`.

The current encoder uses:

- package type/header in byte 0
- program name in bytes 2..12
- program priority in byte 13

### Switching-time package

Typical package:

```text
08 00 10 01 00 3E 06 10 00 00 00 00 00 00
```

Known fields in the implemented subset:

| Byte | Meaning |
|---:|---|
| 0 | record/package type (`08`) |
| 2 | function code |
| 3 | channel (`01`) |
| 4 | offset / signed parameter used by supported event types |
| 5 | weekday mask |
| 6 | hour |
| 7 | minute |
| 8..13 | unused/zero in the implemented normal clock subset |

### Function codes observed

| Function code | Meaning |
|---:|---|
| `08` | normal OFF |
| `10` | normal ON |
| `28` | astronomical sunset OFF |

### Weekday bit mask

Bit allocation:

| Bit | Day |
|---:|---|
| 0 | Sunday |
| 1 | Monday |
| 2 | Tuesday |
| 3 | Wednesday |
| 4 | Thursday |
| 5 | Friday |
| 6 | Saturday |

Examples:

| Mask | Days |
|---:|---|
| `0x7F` | all days |
| `0x1F` | Sunday + Monday–Thursday |
| `0x41` | Saturday + Sunday |
| `0x60` | Friday + Saturday |
| `0x3E` | Monday–Friday |

## Why timing matters

During development, BLE writes that completed successfully at the GATT API level still failed at the Talento program layer when content packages were sent too quickly.

Home Assistant/Bleak sometimes returned from a `response=True` write in roughly 20–35 ms. Sending the next packet immediately, or after only a small fixed delay, could leave the device with corrupted, unchanged, or zero-filled program records.

The official app HCI trace showed approximately 600 ms between content-write request starts. Reproducing that pacing made program writing work reliably in testing.

## Scope and unknowns

Version 1.0.0 intentionally implements only the protocol subset that has been decoded and tested.

Not fully decoded/implemented:

- date ranges
- multiple complex program types
- special astronomical modes beyond the tested sunset event
- PIN-protected write flows
- additional channels on devices that expose more than channel 1

Contributions with sanitized HCI captures are welcome once a project license is selected.
