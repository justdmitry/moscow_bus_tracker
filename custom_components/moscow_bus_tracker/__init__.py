from datetime import timedelta
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import MoscowBusApiClient
from .const import DOMAIN, CONF_API_KEY, CONF_STOP_ID, CONF_ROUTE_ID, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["sensor"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Настройка интеграции."""
    session = async_get_clientsession(hass)
    client = MoscowBusApiClient(session, entry.data[CONF_API_KEY])

    # Локальные переменные текущего экземпляра настроек (для фиксации в замыкании)
    api_key = entry.data[CONF_API_KEY]
    stop_id = entry.data[CONF_STOP_ID]
    route_id = entry.data[CONF_ROUTE_ID]
    scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    
    async def _async_update_data():
        try:
            return await client.get_timetable(entry.data[CONF_STOP_ID], entry.data[CONF_ROUTE_ID])
        except Exception as err:
            raise UpdateFailed(f"Ошибка обновления API: {err}")

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"mos_bus_coordinator_{stop_id}_{route_id}",
        update_method=_async_update_data,
        update_interval=timedelta(minutes=scan_interval),
    )

    # Первоначальный сбор данных при старте
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Выгрузка."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
