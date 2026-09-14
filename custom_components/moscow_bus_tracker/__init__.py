from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import *
from .api import MoscowOpenDataApiClient
from .coordinator import BusTrackerCoordinator

PLATFORMS = ["sensor"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    api_key = entry.data[CONF_API_KEY]

    entry.runtime_data = MoscowOpenDataApiClient(session, api_key)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        entry.runtime_data = None
    return unload_ok
