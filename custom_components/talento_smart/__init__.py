from __future__ import annotations

import logging
from datetime import timedelta

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_interval

from .client import TalentoSmartClient
from .const import DEFAULT_SYNC_HOURS, DOMAIN

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["button", "sensor", "select"]

SERVICE_READ_PROGRAM = "read_program"
SERVICE_SYNC_TIME = "sync_time"
SERVICE_WRITE_PROGRAM = "write_program"
SERVICE_READ_MODE = "read_mode"
SERVICE_SET_MODE = "set_mode"

ADDRESS_SCHEMA = vol.Schema({vol.Required("address"): cv.string})
WRITE_SCHEMA = vol.Schema({
    vol.Required("address"): cv.string,
    vol.Required("program"): dict,
})
MODE_SCHEMA = vol.Schema({
    vol.Required("address"): cv.string,
    vol.Required("mode"): vol.In(["AUTO", "OVR", "FIX ON", "FIX OFF"]),
})


def _client_by_address(hass: HomeAssistant, address: str) -> TalentoSmartClient:
    address = address.upper()
    for client in hass.data.get(DOMAIN, {}).values():
        if isinstance(client, TalentoSmartClient) and client.address.upper() == address:
            return client
    raise vol.Invalid(f"Talento Smart med adresse {address} er ikke indlæst")


async def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_READ_PROGRAM):
        return

    async def read_program(call: ServiceCall) -> None:
        await _client_by_address(hass, call.data["address"]).async_read_program()

    async def sync_time(call: ServiceCall) -> None:
        await _client_by_address(hass, call.data["address"]).async_sync_time()

    async def write_program(call: ServiceCall) -> None:
        await _client_by_address(hass, call.data["address"]).async_write_program(
            call.data["program"]
        )

    async def read_mode(call: ServiceCall) -> None:
        await _client_by_address(hass, call.data["address"]).async_read_channel_mode(1)

    async def set_mode(call: ServiceCall) -> None:
        await _client_by_address(hass, call.data["address"]).async_write_channel_mode(
            call.data["mode"], 1
        )

    hass.services.async_register(DOMAIN, SERVICE_READ_PROGRAM, read_program, schema=ADDRESS_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SYNC_TIME, sync_time, schema=ADDRESS_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_WRITE_PROGRAM, write_program, schema=WRITE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_READ_MODE, read_mode, schema=ADDRESS_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SET_MODE, set_mode, schema=MODE_SCHEMA)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    address = entry.data["address"]
    name = entry.data.get("name", "Talento Smart")
    client = TalentoSmartClient(hass, address, name, entry.entry_id)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = client

    await _register_services(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _scheduled_sync(_now) -> None:
        try:
            await client.async_sync_time()
        except Exception:
            _LOGGER.exception("Planlagt Talento-tidssynkronisering fejlede for %s", address)

    async def _scheduled_program_read(_now) -> None:
        try:
            await client.async_read_program()
        except Exception:
            _LOGGER.exception("Automatisk Talento-programlæsning fejlede for %s", address)

    entry.async_on_unload(
        async_track_time_interval(hass, _scheduled_sync, timedelta(hours=DEFAULT_SYNC_HOURS))
    )
    entry.async_on_unload(
        async_track_time_interval(hass, _scheduled_program_read, timedelta(hours=6))
    )

    async def _startup_sequence() -> None:
        # Let HA Bluetooth settle after startup, then perform Talento operations
        # sequentially. The client also has its own per-device operation lock.
        await __import__("asyncio").sleep(3)
        await _scheduled_sync(None)
        await __import__("asyncio").sleep(1)
        await _scheduled_program_read(None)

    hass.async_create_task(_startup_sequence())
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    if ok and not hass.data.get(DOMAIN):
        for service in (SERVICE_READ_PROGRAM, SERVICE_SYNC_TIME, SERVICE_WRITE_PROGRAM, SERVICE_READ_MODE, SERVICE_SET_MODE):
            hass.services.async_remove(DOMAIN, service)
    return ok
