from __future__ import annotations

from datetime import datetime

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    client = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        TalentoSyncTimeButton(entry, client),
        TalentoReadProgramButton(entry, client),
    ])


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.data["address"])},
        name=entry.data.get("name", "Talento Smart"),
        manufacturer="Grässlin",
        model="talento smart",
    )


class TalentoSyncTimeButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_name = "Synkroniser tid"
    _attr_icon = "mdi:clock-sync"

    def __init__(self, entry: ConfigEntry, client) -> None:
        self._entry = entry
        self._client = client
        self._attr_unique_id = f"{entry.data['address']}_sync_time"
        self._attr_device_info = _device_info(entry)
        self._attr_extra_state_attributes = {"last_sent_unix": None, "last_sync": None}

    async def async_press(self) -> None:
        unix_seconds = await self._client.async_sync_time()
        self._attr_extra_state_attributes = {
            "last_sent_unix": unix_seconds,
            "last_sync": datetime.now().astimezone().isoformat(),
        }
        self.async_write_ha_state()


class TalentoReadProgramButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_name = "Hent timerprogram"
    _attr_icon = "mdi:calendar-import"

    def __init__(self, entry: ConfigEntry, client) -> None:
        self._entry = entry
        self._client = client
        self._attr_unique_id = f"{entry.data['address']}_read_program"
        self._attr_device_info = _device_info(entry)

    async def async_press(self) -> None:
        await self._client.async_read_program()
