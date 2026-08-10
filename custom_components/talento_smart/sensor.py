from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    client = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        TalentoDecodedProgramSensor(entry, client),
        TalentoWriteStatusSensor(entry, client),
    ])


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.data["address"])},
        name=entry.data.get("name", "Talento Smart"),
        manufacturer="Grässlin",
        model="talento smart",
    )


class TalentoDecodedProgramSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Timerprogram"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, entry: ConfigEntry, client) -> None:
        self._entry = entry
        self._client = client
        self._attr_unique_id = f"{entry.data['address']}_decoded_program"
        self._attr_native_value = "Ikke hentet"
        self._attr_extra_state_attributes = {"address": entry.data["address"]}
        self._attr_device_info = _device_info(entry)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(
            self.hass,
            f"{DOMAIN}_{self._entry.entry_id}_program_transfer",
            self._handle_transfer,
        ))
        if self._client.last_program_transfer:
            self._handle_transfer(self._client.last_program_transfer)

    def _handle_transfer(self, result: dict) -> None:
        decoded = result.get("decoded_program", {})
        program_name = decoded.get("program_name", "Ukendt")
        entries = decoded.get("switching_times", [])
        self._attr_native_value = f"{program_name}: {len(entries)} skiftetider"
        self._attr_extra_state_attributes = {
            "address": result.get("address", self._entry.data["address"]),
            "program_name": program_name,
            "priority": decoded.get("priority", 0),
            "switching_time_count": len(entries),
            "inverted_output": decoded.get("inverted_output", True),
            "switching_times": entries,
            "summary": [item.get("display") for item in entries],
            "gatt_properties": result.get("gatt_properties", {}),
        }
        self.async_write_ha_state()


class TalentoWriteStatusSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Skrivestatus"
    _attr_icon = "mdi:content-save-check"
    _attr_entity_registry_enabled_default = True

    def __init__(self, entry: ConfigEntry, client) -> None:
        self._entry = entry
        self._client = client
        self._attr_unique_id = f"{entry.data['address']}_write_status"
        self._attr_native_value = "Ingen skrivning endnu"
        self._attr_extra_state_attributes = {}
        self._attr_device_info = _device_info(entry)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(
            self.hass,
            f"{DOMAIN}_{self._entry.entry_id}_write_status",
            self._handle_status,
        ))
        if getattr(self._client, "last_write_status", None):
            self._handle_status(self._client.last_write_status)

    def _handle_status(self, status: dict) -> None:
        if status.get("success") and status.get("restored"):
            self._attr_native_value = "Backup gendannet"
        elif status.get("success"):
            self._attr_native_value = "Skrevet og verificeret"
        else:
            self._attr_native_value = "Skrivning fejlede"
        self._attr_extra_state_attributes = status
        self.async_write_ha_state()
