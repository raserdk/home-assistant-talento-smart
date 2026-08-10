from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import bluetooth
from homeassistant.data_entry_flow import FlowResult

from .const import CONFIG_SERVICE_UUID, DOMAIN


class TalentoSmartConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._discovery = None

    async def async_step_bluetooth(self, discovery_info) -> FlowResult:
        self._discovery = discovery_info
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self.context["title_placeholders"] = {"name": discovery_info.name or "Talento Smart"}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(self, user_input=None) -> FlowResult:
        if user_input is not None:
            info = self._discovery
            return self.async_create_entry(
                title=info.name or "Talento Smart",
                data={"address": info.address, "name": info.name or "Talento Smart"},
            )
        return self.async_show_form(step_id="bluetooth_confirm")

    async def async_step_user(self, user_input=None) -> FlowResult:
        if user_input is not None:
            address = user_input["address"].upper()
            await self.async_set_unique_id(address)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=user_input.get("name") or "Talento Smart",
                data={"address": address, "name": user_input.get("name") or "Talento Smart"},
            )

        discovered = bluetooth.async_discovered_service_info(self.hass, connectable=True)
        candidates = [
            info for info in discovered
            if CONFIG_SERVICE_UUID in {u.lower() for u in info.service_uuids}
            or "talento" in (info.name or "").lower()
        ]
        if candidates:
            choices = {info.address: f"{info.name or 'Talento Smart'} ({info.address})" for info in candidates}
            schema = vol.Schema({
                vol.Required("address"): vol.In(choices),
                vol.Optional("name", default="Talento Smart"): str,
            })
        else:
            schema = vol.Schema({
                vol.Required("address"): str,
                vol.Optional("name", default="Talento Smart"): str,
            })
        return self.async_show_form(step_id="user", data_schema=schema)
