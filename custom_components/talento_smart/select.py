from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

OPTIONS = ["AUTO", "OVR", "FIX ON", "FIX OFF"]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    client = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([TalentoChannelModeSelect(entry, client)])


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.data["address"])},
        name=entry.data.get("name", "Talento Smart"),
        manufacturer="Grässlin",
        model="talento smart",
    )


class TalentoChannelModeSelect(SelectEntity):
    _attr_has_entity_name = True
    _attr_name = "Driftstilstand"
    _attr_icon = "mdi:toggle-switch"
    _attr_options = OPTIONS
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, client) -> None:
        self._entry = entry
        self._client = client
        self._attr_unique_id = f"{entry.data['address']}_channel_1_mode"
        self._attr_current_option = None
        self._attr_device_info = _device_info(entry)
        self._attr_extra_state_attributes = {
            "channel": 1,
            "inverted_output": True,
            "mode_effect": {
                "AUTO": "Følger timerprogram",
                "OVR": "Midlertidig override til næste programskift",
                "FIX ON": "Talento ON / faktisk lys SLUKKET",
                "FIX OFF": "Talento OFF / faktisk lys TÆNDT",
            },
        }

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{DOMAIN}_{self._entry.entry_id}_channel_mode",
                self._handle_mode,
            )
        )
        self.hass.async_create_task(self._initial_read())

    async def _initial_read(self) -> None:
        # Avoid competing with startup time/program reads.
        import asyncio
        await asyncio.sleep(6)
        try:
            mode = await self._client.async_read_channel_mode(1)
            self._attr_current_option = mode
            self.schedule_update_ha_state()
        except Exception:
            pass

    def _handle_mode(self, data: dict) -> None:
        if data.get("channel") != 1:
            return
        self._attr_current_option = data.get("mode")
        attrs = dict(self._attr_extra_state_attributes)
        attrs["raw_status"] = data.get("raw")
        attrs["raw_status_hex"] = data.get("raw_hex")
        attrs["relay_status"] = data.get("relay")
        self._attr_extra_state_attributes = attrs
        self.schedule_update_ha_state()

    async def async_select_option(self, option: str) -> None:
        mode = await self._client.async_write_channel_mode(option, 1)
        self._attr_current_option = mode
        self.schedule_update_ha_state()
