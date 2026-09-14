from dataclasses import dataclass
from urllib.parse import quote
from datetime import timedelta
import aiohttp
import asyncio
import async_timeout
import homeassistant.util.dt as dt_util
import logging

_LOGGER = logging.getLogger(__name__)

@dataclass(frozen=True)
class BusRoute:
    route_id: str
    route_type: str
    route_short_name: str
    route_long_name: str

@dataclass(frozen=True)
class BusStop:
    stop_id: str
    stop_name: str
    global_id: str

@dataclass(frozen=True)
class BusArrival:
    raw_time: str      # For storing (e.g., "24:15:00").
    display_time: str  # For screen (e.g., "00:15").

class MoscowOpenDataApiError(Exception):
    """Generic API error."""

class MoscowOpenDataApiAuthError(MoscowOpenDataApiError):
    """API authentication failed."""

class MoscowOpenDataApiClient:
    def __init__(self, session: aiohttp.ClientSession, api_key: str) -> None:
        self._session = session
        self._api_key = api_key
        self._base_url = "https://apidata.mos.ru/v1/datasets"

    @staticmethod
    def _check_response_status_code(response: aiohttp.ClientResponse) -> None:
        if response.status in (401, 403):
            raise MoscowOpenDataApiAuthError(f"API key was rejected (response code {response.status})")

        if response.status >= 400:
            raise MoscowOpenDataApiError(f"API returned HTTP {response.status}")

    async def _make_request(self, dataset_id: str, filter_query: str) -> list:
        url = f"{self._base_url}/{dataset_id}/rows?api_key={self._api_key}&$filter={quote(filter_query)}"
        try:
            async with async_timeout.timeout(10):
                async with self._session.get(url) as response:
                    _LOGGER.debug(f"Request for dataset {dataset_id} done with response code {response.status}")
                    self._check_response_status_code(response)
                    return await response.json()
        except asyncio.TimeoutError as err:
            raise MoscowOpenDataApiError("Request timed out") from err
        except aiohttp.ClientError as err:
            raise MoscowOpenDataApiError("Network error") from err

    async def check_key(self) -> None:
        filter_str = f"route_short_name eq '0'"
        data = await self._make_request("60664", filter_str)
        _LOGGER.debug(f"check_key() done (successfully)")

    async def search_routes(self, route_number: str) -> list[BusRoute]:
        filter_str = f"route_short_name eq '{route_number.replace("'", "''")}'"
        data = await self._make_request("60664", filter_str)
        routes = [
            BusRoute(
                route_id=str(item.get("Cells", {}).get("route_id")),
                route_type=str(item.get("Cells", {}).get("route_type")),
                route_short_name=str(item.get("Cells", {}).get("route_short_name")),
                route_long_name=str(item.get("Cells", {}).get("route_long_name"))
            )
            for item in data
            if item.get("Cells", {}).get("route_id")
        ]
        _LOGGER.debug("search_routes(%s) found %d items", route_number, len(routes))
        return routes

    async def search_stops(self, search_query: str) -> list[BusStop]:
        filter_str = f"substringof('{search_query.replace("'", "''")}', stop_name)"
        data = await self._make_request("60662", filter_str)
        stops = []
        for item in data:
            cells = item.get("Cells", {})
            if cells.get("stop_id") and str(cells.get("stop_id")) != "None":
                stops.append(BusStop(
                    stop_id=str(cells.get("stop_id")),
                    stop_name=str(cells.get("stop_name")),
                    global_id=str(cells.get("global_id"))
                ))
        _LOGGER.debug("search_stops(%s) found %d items", search_query, len(stops))
        return stops

    async def get_active_services_for_today(self, route_id: str, newday_shift: timedelta) -> list[str]:
        now = (dt_util.now() - newday_shift)
        today_str = now.strftime("%Y%m%d")
        weekday_name = now.strftime("%A").lower()

        trips_data = await self._make_request("60665", f"route_id eq '{route_id.replace("'", "''")}'")
        service_ids = {str(i.get("Cells", {}).get("service_id")) for i in trips_data if i.get("Cells", {}).get("service_id")}

        active_services = []
        for s_id in service_ids:
            calendar_data = await self._make_request("60666", f"service_id eq '{s_id}'")
            for cal in calendar_data:
                cells = cal.get("Cells", {})
                if cells.get("start_date", "") <= today_str <= cells.get("end_date", "") and str(cells.get(weekday_name, 0)) == "1":
                    active_services.append(s_id)
                    break
        _LOGGER.debug("get_active_services_for_today(route %s) found %d items for date %s / %s", route_id, len(active_services), today_str, weekday_name)
        return active_services

    async def get_timetable(self, stop_id: str, route_id: str, active_services: list[str]) -> list[BusArrival]:

        timetable_data = await self._make_request("60661", f"stop_id eq {stop_id}")

        arrivals = []
        prefix = f"{route_id}_"

        for item in timetable_data:
            cells = item.get("Cells", {})
            trip_id = cells.get("trip_id", "")
            arrival_time = cells.get("arrival_time", "")

            if trip_id and arrival_time and trip_id.startswith(prefix):
                trip_parts = trip_id.split("_")
                if len(trip_parts) >= 2 and trip_parts[1] in active_services:
                    time_parts = arrival_time.split(":")
                    hours = int(time_parts[0])
                    if hours >= 24:
                        hours %= 24
                    display_time = f"{hours:02d}:{time_parts[1]}"
                    arrivals.append(BusArrival(raw_time=arrival_time, display_time=display_time))

        arrivals = {a.raw_time: a for a in arrivals}.values() # distinct
        arrivals = sorted(arrivals, key=lambda x: x.raw_time) # sort
        _LOGGER.debug("get_timetable(stop %s, route %s) found %d items", stop_id, route_id, len(arrivals))
        return arrivals
