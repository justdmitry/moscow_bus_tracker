from datetime import timedelta
import logging
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import *
from .api import MoscowOpenDataApiClient

_LOGGER = logging.getLogger(__name__)

class BusTrackerCoordinator(DataUpdateCoordinator):
    def __init__(
        self,
        hass: HomeAssistant,
        api_client: MoscowOpenDataApiClient,
        update_interval: timedelta,
        newday_shift_interval: timedelta,
        route_id: str,
        stop_id: str
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"Bus Tracker for route {route_id} and stop {stop_id}",
            update_interval=update_interval,
        )
        self._api_client = api_client
        self._route_id = route_id
        self._stop_id = stop_id
        self._newday_shift_interval = newday_shift_interval
        _LOGGER.debug(f"Created DataUpdateCoordinator for route {route_id}, stop {stop_id}, update {update_interval}, newday shift {newday_shift_interval}.")

    async def _async_update_data(self):
        try:
            active_services = await self._api_client.get_active_services_for_today(self._route_id, self._newday_shift_interval)
            if not active_services:
                return []
            return await self._api_client.get_timetable(self._stop_id, self._route_id, active_services)
        except MoscowOpenDataApiAuthError as err:
            raise ConfigEntryAuthFailed("The API key is invalid") from err
        except MoscowOpenDataApiError as err:
            raise UpdateFailed("Unable to retrieve data from the API") from err
