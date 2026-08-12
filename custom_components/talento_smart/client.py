from __future__ import annotations

import asyncio
import json
import logging
import struct
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import DOMAIN, TIME_CHARACTERISTIC_UUID

_LOGGER = logging.getLogger(__name__)

PROGRAM_SERVICE_UUID = "ec04000a-04da-47e5-add4-8ed1c9d52fec"
PROGRAM_DIRECTION_UUID = "ec04000b-04da-47e5-add4-8ed1c9d52fec"
PROGRAM_PACKET_COUNT_UUID = "ec04000c-04da-47e5-add4-8ed1c9d52fec"
PROGRAM_ACK_NOTIFY_UUID = "ec04000d-04da-47e5-add4-8ed1c9d52fec"
PROGRAM_DATA_UUID = "ec04000e-04da-47e5-add4-8ed1c9d52fec"
PIN_STATUS_UUID = "ec040017-04da-47e5-add4-8ed1c9d52fec"
CHANNEL_ID_UUID = "ec040004-04da-47e5-add4-8ed1c9d52fec"
CHANNEL_STATE_UUID = "ec040008-04da-47e5-add4-8ed1c9d52fec"

PROGRAM_DIRECTION_READ = b"\x00"
PROGRAM_DIRECTION_WRITE = b"\x01"
MAX_PACKAGES = 500
HEADER_NAME_LENGTH = 11

CHANNEL_MODE_TO_BYTE = {
    "AUTO": 0x00,
    "OVR": 0x03,
    "FIX ON": 0x01,
    "FIX OFF": 0x02,
}
CHANNEL_READ_OVR = {0x04, 0x05, 0x0C, 0x0D}
CHANNEL_READ_FIX_ON = {0x02, 0x0A}
CHANNEL_READ_FIX_OFF = {0x03, 0x0B}


def _decode_channel_status_byte(value: int) -> tuple[str, bool]:
    if value in CHANNEL_READ_OVR:
        mode = "OVR"
    elif value in CHANNEL_READ_FIX_ON:
        mode = "FIX ON"
    elif value in CHANNEL_READ_FIX_OFF:
        mode = "FIX OFF"
    else:
        mode = "AUTO"
    relay = value in {0x01, 0x02, 0x04}
    return mode, relay


def _hex(data: bytes) -> str:
    return data.hex(" ").upper()


def _decode_day_mask(mask: int) -> dict[str, Any]:
    selected = {
        "S": bool(mask & 0x01),
        "M": bool(mask & 0x02),
        "Ti": bool(mask & 0x04),
        "O": bool(mask & 0x08),
        "To": bool(mask & 0x10),
        "F": bool(mask & 0x20),
        "L": bool(mask & 0x40),
    }
    compact = "".join([
        "M" if selected["M"] else "_",
        "T" if selected["Ti"] else "_",
        "O" if selected["O"] else "_",
        "T" if selected["To"] else "_",
        "F" if selected["F"] else "_",
        "L" if selected["L"] else "_",
        "S" if selected["S"] else "_",
    ])
    names = [
        name for key, name in (
            ("M", "mandag"),
            ("Ti", "tirsdag"),
            ("O", "onsdag"),
            ("To", "torsdag"),
            ("F", "fredag"),
            ("L", "lørdag"),
            ("S", "søndag"),
        ) if selected[key]
    ]
    return {"mask": mask, "compact": compact, "days": names}


def _decode_time_function(code: int) -> tuple[str, str]:
    astro = code & 0x60
    base = code & 0x1F
    function = "ON" if base in (0x10, 0x11) else "OFF" if base in (0x08, 0x09) else "UNKNOWN"
    if astro == 0x20:
        mode = "sunset"
    elif astro == 0x40:
        mode = "sunrise"
    else:
        mode = "clock"
    return function, mode


def _actual_light(function: str) -> str:
    return "TÆNDT" if function == "OFF" else "SLUKKET" if function == "ON" else "ukendt"


def _decode_program_blocks(raw_blocks: list[bytes]) -> dict[str, Any]:
    program_name = None
    priority = 0
    entries: list[dict[str, Any]] = []
    for idx, data in enumerate(raw_blocks):
        if len(data) < 14 or not any(data):
            continue
        packet_type = data[0] & 0x1C
        if packet_type == 0x00:
            name_bytes = data[2:13].split(b"\x00", 1)[0]
            try:
                program_name = name_bytes.decode("ascii")
            except UnicodeDecodeError:
                program_name = "Prog1"
            priority = data[13] & 0x07
            continue
        if packet_type != 0x08:
            continue
        function, mode = _decode_time_function(data[2])
        days = _decode_day_mask(data[5])
        offset = struct.unpack("b", bytes([data[4]]))[0]
        item: dict[str, Any] = {
            "index": idx,
            "function_code_hex": f"0x{data[2]:02X}",
            "talento_function": function,
            "actual_light": _actual_light(function),
            "mode": mode,
            "kind": "clock" if mode == "clock" else "astronomical",
            "day_mask": data[5],
            "day_mask_hex": f"0x{data[5]:02X}",
            "days_compact": days["compact"],
            "days": days["days"],
            "channel": 1,
            "offset_minutes": offset,
            "raw_hex": _hex(data),
        }
        if mode == "clock":
            item["time"] = f"{data[6]:02d}:{data[7]:02d}"
            item["display"] = f"{function} {item['time']} {days['compact']}"
        else:
            event_da = "solnedgang" if mode == "sunset" else "solopgang"
            item["astronomical_event"] = event_da
            sign = "+" if offset >= 0 else ""
            item["display"] = f"{function} {event_da} {sign}{offset} min {days['compact']}"
        entries.append(item)
    return {
        "program_name": program_name or "Prog1",
        "priority": priority,
        "switching_times": entries,
        "switching_time_count": len(entries),
        "inverted_output": True,
    }


def _encode_program(program: dict[str, Any], old_blocks: list[bytes] | None = None) -> list[bytes]:
    name = str(program.get("program_name", "Prog1")).strip() or "Prog1"
    try:
        name_b = name.encode("ascii")
    except UnicodeEncodeError as err:
        raise ValueError("Programnavnet må kun indeholde almindelige ASCII-tegn") from err
    if len(name_b) > HEADER_NAME_LENGTH:
        raise ValueError("Programnavnet må højst være 11 tegn")
    priority = int(program.get("priority", 0))
    if priority < 0 or priority > 7:
        raise ValueError("Prioritet skal være mellem 0 og 7")
    entries = list(program.get("switching_times") or [])
    if not entries:
        raise ValueError("Programmet skal indeholde mindst én skiftetid")
    if len(entries) + 1 > MAX_PACKAGES:
        raise ValueError("Programmet er for stort")
    header = bytearray(14)
    header[0] = 0x00
    header[1] = 0x00
    header[2:2 + len(name_b)] = name_b
    header[13] = priority & 0x07
    blocks: list[bytes] = [bytes(header)]
    for entry in entries:
        function = str(entry.get("talento_function", "ON")).upper()
        mode = str(entry.get("mode") or ("clock" if entry.get("kind") == "clock" else "sunset")).lower()
        if function not in ("ON", "OFF"):
            raise ValueError(f"Ukendt funktion: {function}")
        if mode not in ("clock", "sunset", "sunrise"):
            raise ValueError(f"Ukendt tidstype: {mode}")
        base = 0x10 if function == "ON" else 0x08
        code = base | 0x20 if mode == "sunset" else base | 0x40 if mode == "sunrise" else base
        day_mask = int(entry.get("day_mask", 0))
        if day_mask < 1 or day_mask > 0x7F:
            raise ValueError("Der skal vælges mindst én ugedag")
        block = bytearray(14)
        block[0] = 0x08
        block[1] = 0x00
        block[2] = code
        block[3] = 0x01
        if mode == "clock":
            t = str(entry.get("time", "00:00"))
            try:
                hour_s, minute_s = t.split(":", 1)
                hour, minute = int(hour_s), int(minute_s)
            except Exception as err:
                raise ValueError(f"Ugyldigt tidspunkt: {t}") from err
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError(f"Ugyldigt tidspunkt: {t}")
            block[4] = 0
            block[6] = hour
            block[7] = minute
        else:
            offset = int(entry.get("offset_minutes", 0))
            if offset < -128 or offset > 127:
                raise ValueError("Sol-offset skal være mellem -128 og +127 minutter")
            block[4] = offset & 0xFF
        block[5] = day_mask
        blocks.append(bytes(block))
    return blocks


def _semantic_program(program: dict[str, Any]) -> dict[str, Any]:
    entries = []
    for item in program.get("switching_times", []):
        mode = str(item.get("mode") or ("clock" if item.get("kind") == "clock" else "sunset"))
        entry = {
            "talento_function": str(item.get("talento_function", "")).upper(),
            "mode": mode,
            "day_mask": int(item.get("day_mask", 0)),
            "channel": int(item.get("channel", 1)),
        }
        if mode == "clock":
            entry["time"] = str(item.get("time", "00:00"))
        else:
            entry["offset_minutes"] = int(item.get("offset_minutes", 0))
        entries.append(entry)
    return {
        "program_name": str(program.get("program_name", "Prog1")),
        "priority": int(program.get("priority", 0)),
        "switching_times": entries,
    }


def _raw_block_diffs(expected: list[bytes], actual: list[bytes]) -> list[dict[str, Any]]:
    diffs: list[dict[str, Any]] = []
    max_len = max(len(expected), len(actual))
    for i in range(max_len):
        exp = expected[i] if i < len(expected) else b""
        act = actual[i] if i < len(actual) else b""
        if exp != act:
            byte_diffs = []
            for j in range(max(len(exp), len(act))):
                eb = exp[j] if j < len(exp) else None
                ab = act[j] if j < len(act) else None
                if eb != ab:
                    byte_diffs.append({
                        "offset": j,
                        "expected": None if eb is None else f"{eb:02X}",
                        "actual": None if ab is None else f"{ab:02X}",
                    })
            diffs.append({
                "block": i,
                "expected_hex": _hex(exp),
                "actual_hex": _hex(act),
                "byte_diffs": byte_diffs,
            })
    return diffs


class TalentoSmartClient:
    def __init__(self, hass: HomeAssistant, address: str, name: str, entry_id: str) -> None:
        self.hass = hass
        self.address = address
        self.name = name
        self.entry_id = entry_id
        self.last_program_transfer: dict[str, Any] = {}
        self.last_backup: dict[str, Any] | None = None
        self.last_write_status: dict[str, Any] = {}
        self._operation_lock = asyncio.Lock()

    async def _connect(self):
        ble_device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if ble_device is None:
            raise RuntimeError(
                f"Talento Smart {self.address} kan ikke nås via en connectable Bluetooth-adapter"
            )
        return await establish_connection(
            BleakClientWithServiceCache,
            ble_device,
            self.name,
            max_attempts=3,
        )

    async def _async_sync_time_unlocked(self) -> int:
        unix_seconds = int(time.time())
        payload = struct.pack("<I", unix_seconds)
        client = await self._connect()
        try:
            characteristic = client.services.get_characteristic(TIME_CHARACTERISTIC_UUID)
            if characteristic is None:
                raise RuntimeError(f"Time characteristic {TIME_CHARACTERISTIC_UUID} blev ikke fundet")
            props = {p.lower() for p in characteristic.properties}
            await client.write_gatt_char(characteristic, payload, response="write" in props)
            _LOGGER.info("Talento %s time synchronized to %s", self.address, unix_seconds)
            return unix_seconds
        finally:
            await client.disconnect()

    async def _read_program_raw(self) -> tuple[list[bytes], dict[str, Any]]:
        client = await self._connect()
        notifications: list[str] = []

        def _notify(_sender, data: bytearray) -> None:
            notifications.append(_hex(bytes(data)))

        try:
            for uuid in (
                PIN_STATUS_UUID,
                PROGRAM_DIRECTION_UUID,
                PROGRAM_PACKET_COUNT_UUID,
                PROGRAM_ACK_NOTIFY_UUID,
                PROGRAM_DATA_UUID,
            ):
                if client.services.get_characteristic(uuid) is None:
                    raise RuntimeError(f"Talento characteristic {uuid} blev ikke fundet")
            gatt_properties: dict[str, Any] = {}
            for label, uuid in (
                ("pin_status", PIN_STATUS_UUID),
                ("direction", PROGRAM_DIRECTION_UUID),
                ("package_count", PROGRAM_PACKET_COUNT_UUID),
                ("package_counter_notify", PROGRAM_ACK_NOTIFY_UUID),
                ("content_buffer", PROGRAM_DATA_UUID),
            ):
                ch = client.services.get_characteristic(uuid)
                props = list(getattr(ch, "properties", []) or [])
                item: dict[str, Any] = {
                    "uuid": str(uuid),
                    "properties": props,
                    "plugin_ble_would_use_response": any(str(p).lower() == "write" for p in props),
                }
                try:
                    item["handle"] = ch.handle
                except Exception:
                    pass
                try:
                    item["max_write_without_response_size"] = ch.max_write_without_response_size
                except Exception:
                    pass
                gatt_properties[label] = item
            pin_status = bytes(await client.read_gatt_char(PIN_STATUS_UUID))
            if pin_status and pin_status[0] == 0x55:
                raise RuntimeError("Talento kræver PIN; PIN-handshake er endnu ikke implementeret")
            notify_started = False
            try:
                await client.start_notify(PROGRAM_ACK_NOTIFY_UUID, _notify)
                notify_started = True
            except Exception:
                pass
            await client.write_gatt_char(PROGRAM_DIRECTION_UUID, PROGRAM_DIRECTION_READ, response=True)
            await asyncio.sleep(0.5)
            count_raw = bytes(await client.read_gatt_char(PROGRAM_PACKET_COUNT_UUID))
            package_count = int.from_bytes(count_raw, "little") if count_raw else 0
            if not 0 <= package_count <= MAX_PACKAGES:
                raise RuntimeError(f"Ugyldigt pakkeantal: {package_count}")
            raw_blocks = [
                bytes(await client.read_gatt_char(PROGRAM_DATA_UUID))
                for _ in range(package_count)
            ]
            if notify_started:
                try:
                    await client.stop_notify(PROGRAM_ACK_NOTIFY_UUID)
                except Exception:
                    pass
            meta = {
                "pin_status_hex": _hex(pin_status),
                "package_count_hex": _hex(count_raw),
                "package_count_le": package_count,
                "notifications": notifications,
                "gatt_properties": gatt_properties,
            }
            return raw_blocks, meta
        finally:
            await client.disconnect()

    async def _async_read_program_unlocked(self) -> dict[str, Any]:
        raw_blocks, meta = await self._read_program_raw()
        decoded = _decode_program_blocks(raw_blocks)
        blocks = [
            {
                "index": i,
                "length": len(block),
                "hex": _hex(block),
                "all_zero": not any(block),
            }
            for i, block in enumerate(raw_blocks)
        ]
        result = {
            "address": self.address,
            "decoded_program": decoded,
            "blocks": blocks,
            "raw_blocks_hex": [_hex(x) for x in raw_blocks],
            "record_count_le": len(raw_blocks),
            "record_count_hex": len(raw_blocks).to_bytes(2, "little").hex(" ").upper(),
            "nonzero_block_count": sum(1 for x in raw_blocks if any(x)),
            **meta,
        }
        self.last_program_transfer = result
        async_dispatcher_send(
            self.hass, f"{DOMAIN}_{self.entry_id}_program_transfer", result
        )
        return result

    async def _save_backup(self, raw_blocks: list[bytes], decoded: dict[str, Any]) -> dict[str, Any]:
        stamp = datetime.now().astimezone()
        backup = {
            "address": self.address,
            "name": self.name,
            "created": stamp.isoformat(),
            "raw_blocks_hex": [_hex(x) for x in raw_blocks],
            "decoded_program": decoded,
        }
        safe_addr = self.address.replace(":", "")
        folder = Path(self.hass.config.path("talento_smart_backups"))
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{safe_addr}_{stamp.strftime('%Y%m%d_%H%M%S')}.json"
        await self.hass.async_add_executor_job(
            path.write_text, json.dumps(backup, ensure_ascii=False, indent=2), "utf-8"
        )
        backup["file"] = str(path)
        self.last_backup = backup
        return backup

    async def _write_raw_blocks(self, blocks: list[bytes]) -> dict[str, Any]:
        if not blocks:
            raise ValueError("Programmet indeholder ingen programpakker")
        if len(blocks) > 100:
            raise ValueError("Talento Smart understøtter her ét batch på maks. 100 pakker")
        if any(len(block) != 14 for block in blocks):
            raise ValueError("Alle Talento-programpakker skal være præcis 14 bytes")
        client = await self._connect()
        notifications: list[str] = []
        counter_values: list[int] = []
        write_times_ms: list[float] = []
        inter_write_sleeps_ms: list[float] = []
        request_start_intervals_ms: list[float] = []

        def _notify(_sender, data: bytearray) -> None:
            raw = bytes(data)
            notifications.append(_hex(raw))
            if raw:
                counter_values.append(int.from_bytes(raw[:2], "little"))

        try:
            for uuid in (
                PIN_STATUS_UUID,
                PROGRAM_DIRECTION_UUID,
                PROGRAM_PACKET_COUNT_UUID,
                PROGRAM_ACK_NOTIFY_UUID,
                PROGRAM_DATA_UUID,
            ):
                if client.services.get_characteristic(uuid) is None:
                    raise RuntimeError(f"Talento characteristic {uuid} blev ikke fundet")
            pin_status = bytes(await client.read_gatt_char(PIN_STATUS_UUID))
            if pin_status and pin_status[0] == 0x55:
                raise RuntimeError("Talento kræver PIN; skrivning er stoppet")
            loop = asyncio.get_running_loop()
            await client.write_gatt_char(PROGRAM_DIRECTION_UUID, PROGRAM_DIRECTION_WRITE, response=True)
            await asyncio.sleep(0.60)
            await client.write_gatt_char(
                PROGRAM_PACKET_COUNT_UUID,
                len(blocks).to_bytes(2, "little"),
                response=True,
            )
            notify_started = False
            try:
                await client.start_notify(PROGRAM_ACK_NOTIFY_UUID, _notify)
                notify_started = True
            except Exception as err:
                _LOGGER.debug("Talento package-counter notify unavailable: %s", err)
            await asyncio.sleep(0.60)
            target_interval = 0.60
            previous_start = None
            for index, block in enumerate(blocks):
                start_time = loop.time()
                if previous_start is not None:
                    request_start_intervals_ms.append(
                        round((start_time - previous_start) * 1000.0, 1)
                    )
                previous_start = start_time
                await client.write_gatt_char(PROGRAM_DATA_UUID, block, response=True)
                elapsed = loop.time() - start_time
                write_times_ms.append(round(elapsed * 1000.0, 1))
                if index < len(blocks) - 1:
                    sleep_for = max(0.0, target_interval - elapsed)
                    inter_write_sleeps_ms.append(round(sleep_for * 1000.0, 1))
                    if sleep_for:
                        await asyncio.sleep(sleep_for)
            await asyncio.sleep(0.60)
            counter_after = b""
            try:
                counter_after = bytes(await client.read_gatt_char(PROGRAM_ACK_NOTIFY_UUID))
                if counter_after:
                    counter_values.append(int.from_bytes(counter_after[:2], "little"))
            except Exception:
                pass
            if notify_started:
                try:
                    await client.stop_notify(PROGRAM_ACK_NOTIFY_UUID)
                except Exception:
                    pass
            return {
                "written_packages": len(blocks),
                "notifications": notifications,
                "package_counter_values": counter_values,
                "package_counter_after_hex": _hex(counter_after),
                "pin_status_hex": _hex(pin_status),
                "transport": "official_app_with_response_600ms_start_to_start",
                "target_request_interval_ms": 600,
                "write_times_ms": write_times_ms,
                "inter_write_sleeps_ms": inter_write_sleeps_ms,
                "request_start_intervals_ms": request_start_intervals_ms,
            }
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass

    async def _async_read_channel_mode_unlocked(self, channel: int = 1) -> str:
        if channel < 1 or channel > 255:
            raise ValueError("Ugyldigt kanalnummer")
        client = await self._connect()
        try:
            for uuid in (CHANNEL_ID_UUID, CHANNEL_STATE_UUID):
                if client.services.get_characteristic(uuid) is None:
                    raise RuntimeError(f"Talento characteristic {uuid} blev ikke fundet")
            await client.write_gatt_char(CHANNEL_ID_UUID, bytes([channel]), response=True)
            await asyncio.sleep(1.0)
            raw = bytes(await client.read_gatt_char(CHANNEL_STATE_UUID))
            if not raw:
                raise RuntimeError("Talento returnerede ingen kanalstatus")
            value = raw[0]
            mode, relay = _decode_channel_status_byte(value)
            async_dispatcher_send(
                self.hass,
                f"{DOMAIN}_{self.entry_id}_channel_mode",
                {
                    "channel": channel,
                    "mode": mode,
                    "raw": value,
                    "raw_hex": f"0x{value:02X}",
                    "relay": relay,
                },
            )
            return mode
        finally:
            await client.disconnect()

    async def _async_write_channel_mode_unlocked(self, mode: str, channel: int = 1) -> str:
        normalized = mode.strip().upper()
        if normalized not in CHANNEL_MODE_TO_BYTE:
            raise ValueError(f"Ukendt driftstilstand: {mode}")
        if channel < 1 or channel > 255:
            raise ValueError("Ugyldigt kanalnummer")
        client = await self._connect()
        try:
            for uuid in (CHANNEL_ID_UUID, CHANNEL_STATE_UUID):
                if client.services.get_characteristic(uuid) is None:
                    raise RuntimeError(f"Talento characteristic {uuid} blev ikke fundet")
            await client.write_gatt_char(CHANNEL_ID_UUID, bytes([channel]), response=True)
            await asyncio.sleep(0.10)
            await client.write_gatt_char(
                CHANNEL_STATE_UUID,
                bytes([CHANNEL_MODE_TO_BYTE[normalized]]),
                response=True,
            )
            await asyncio.sleep(1.0)
        finally:
            await client.disconnect()
        return await self._async_read_channel_mode_unlocked(channel)

    async def _async_write_program_unlocked(self, program: dict[str, Any]) -> dict[str, Any]:
        current_raw, _meta = await self._read_program_raw()
        current_decoded = _decode_program_blocks(current_raw)
        backup = await self._save_backup(current_raw, current_decoded)
        new_blocks = _encode_program(program, current_raw)
        status: dict[str, Any] = {
            "address": self.address,
            "started": datetime.now().astimezone().isoformat(),
            "backup_file": backup.get("file"),
            "requested_program": program,
        }
        try:
            write_info = await self._write_raw_blocks(new_blocks)
            await asyncio.sleep(0.5)
            verify_raw, _ = await self._read_program_raw()
            raw_verified = verify_raw == new_blocks
            verify_decoded = _decode_program_blocks(verify_raw)
            expected_decoded = _decode_program_blocks(new_blocks)
            expected_semantic = _semantic_program(expected_decoded)
            actual_semantic = _semantic_program(verify_decoded)
            semantic_verified = actual_semantic == expected_semantic
            diffs = _raw_block_diffs(new_blocks, verify_raw)
            status.update({
                "success": semantic_verified,
                "verified": semantic_verified,
                "semantic_verified": semantic_verified,
                "raw_byte_verified": raw_verified,
                "written_packages": write_info["written_packages"],
                "transport": write_info.get("transport"),
                "target_request_interval_ms": write_info.get("target_request_interval_ms"),
                "write_times_ms": write_info.get("write_times_ms", []),
                "inter_write_sleeps_ms": write_info.get("inter_write_sleeps_ms", []),
                "request_start_intervals_ms": write_info.get("request_start_intervals_ms", []),
                "package_counter_values": write_info.get("package_counter_values", []),
                "package_counter_after_hex": write_info.get("package_counter_after_hex"),
                "notifications": write_info["notifications"],
                "expected_program": expected_decoded,
                "readback_program": verify_decoded,
                "expected_raw_blocks_hex": [_hex(x) for x in new_blocks],
                "readback_raw_blocks_hex": [_hex(x) for x in verify_raw],
                "raw_diffs": diffs,
                "finished": datetime.now().astimezone().isoformat(),
            })
            if not semantic_verified:
                raise RuntimeError(
                    "Talento-programmet blev skrevet, men det dekodede read-back-program matcher ikke det ønskede program. Brug 'Gendan sidste backup' før yderligere ændringer."
                )
            result = {
                "address": self.address,
                "decoded_program": verify_decoded,
                "blocks": [
                    {"index": i, "length": 14, "hex": _hex(b), "all_zero": not any(b)}
                    for i, b in enumerate(verify_raw)
                ],
                "raw_blocks_hex": [_hex(x) for x in verify_raw],
                "record_count_le": len(verify_raw),
                "nonzero_block_count": sum(1 for x in verify_raw if any(x)),
            }
            self.last_program_transfer = result
            async_dispatcher_send(
                self.hass, f"{DOMAIN}_{self.entry_id}_program_transfer", result
            )
            return status
        except Exception as err:
            status.update({
                "success": False,
                "verified": False,
                "error": str(err),
                "finished": datetime.now().astimezone().isoformat(),
            })
            raise
        finally:
            self.last_write_status = status
            async_dispatcher_send(
                self.hass, f"{DOMAIN}_{self.entry_id}_write_status", status
            )

    async def async_sync_time(self) -> int:
        async with self._operation_lock:
            return await self._async_sync_time_unlocked()

    async def async_read_program(self) -> dict[str, Any]:
        async with self._operation_lock:
            return await self._async_read_program_unlocked()

    async def async_write_program(self, program: dict[str, Any]) -> dict[str, Any]:
        async with self._operation_lock:
            return await self._async_write_program_unlocked(program)

    async def async_read_channel_mode(self, channel: int = 1) -> str:
        async with self._operation_lock:
            return await self._async_read_channel_mode_unlocked(channel)

    async def async_write_channel_mode(self, mode: str, channel: int = 1) -> str:
        async with self._operation_lock:
            return await self._async_write_channel_mode_unlocked(mode, channel)

    async def async_pull_program_diagnostic(self) -> dict[str, Any]:
        return await self.async_read_program()

    async def async_read_ble_dump(self) -> dict[str, Any]:
        return await self.async_read_program()
