"""Клиент для работы с REST API открытых данных Москвы (Mos.ru)."""
from dataclasses import dataclass
import logging
from urllib.parse import quote
from datetime import timedelta
import aiohttp
import async_timeout
import homeassistant.util.dt as dt_util  # Используем правильное время HA

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
    latitude: float | None = None
    longitude: float | None = None

@dataclass(frozen=True)
class BusArrival:
    raw_time: str      # Для сортировки (например, "24:15:00")
    display_time: str  # Для экрана (например, "00:15")

ROUTE_TYPE_RU = {
    "0": "Трамвай",
    "1": "Метро",
    "2": "Поезд",
    "3": "Автобус",
    "4": "Паром",
    "5": "Канатный трамвай",
    "6": "Канатная дорога",
    "7": "Фуникулер",
    "11": "Троллейбус",
    "12": "Монорельс"
}

class MoscowBusApiClient:
    def __init__(self, session: aiohttp.ClientSession, api_key: str) -> None:
        self._session = session
        self._api_key = api_key
        self._base_url = "https://apidata.mos.ru/v1/datasets"

    async def _make_request(self, dataset_id: str, filter_query: str) -> list:
        url = f"{self._base_url}/{dataset_id}/rows?api_key={self._api_key}&$filter={quote(filter_query)}"
        try:
            async with async_timeout.timeout(10):
                async with self._session.get(url) as response:
                    if response.status == 200:
                        return await response.json()
                    _LOGGER.error("API Mos.ru вернул ошибку HTTP %s для датасета %s", response.status, dataset_id)
                    return []
        except Exception as err:
            _LOGGER.error("Сетевая ошибка при запросе к датасету %s: %s", dataset_id, err)
            raise err

    async def search_routes(self, route_number: str) -> list[BusRoute]:
        filter_str = f"route_short_name eq '{route_number.replace("'", "''")}'"
        data = await self._make_request("60664", filter_str)
        return [
            BusRoute(
                route_id=str(item.get("Cells", {}).get("route_id")),
                route_type=ROUTE_TYPE_RU.get(str(item.get("Cells", {}).get("route_type")), "Маршрут"),
                route_short_name=str(item.get("Cells", {}).get("route_short_name")),
                route_long_name=str(item.get("Cells", {}).get("route_long_name"))
            )
            for item in data if item.get("Cells", {}).get("route_id")
        ]

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
                    latitude=cells.get("Latitude"),
                    longitude=cells.get("Longitude")
                ))
        return stops

    async def get_timetable(self, stop_id: str, route_id: str) -> list[BusArrival]:
        """Единая точка входа для получения расписания."""
        now = dt_util.now()
        today_str = now.strftime("%Y%m%d")
        weekday_name = now.strftime("%A").lower()
        threshold_str = (now - timedelta(minutes=5)).strftime("%H:%M:%S")

        # 1. Календари рейсов
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

        if not active_services:
            return []

        # 2. Расписание остановки
        timetable_data = await self._make_request("60661", f"stop_id eq {stop_id}")
        arrivals = []
        prefix = f"{route_id}_"

        for item in timetable_data:
            cells = item.get("Cells", {})
            trip_id = cells.get("trip_id", "")
            arrival_time = cells.get("arrival_time", "")
            
            if trip_id and arrival_time and trip_id.startswith(prefix):
                trip_parts = trip_id.split("_")
                if len(trip_parts) >= 2 and trip_parts[1] in active_services and arrival_time >= threshold_str:
                    time_parts = arrival_time.split(":")
                    hours = int(time_parts[0])
                    if hours >= 24:
                        hours %= 24
                    display_time = f"{hours:02d}:{time_parts[1]}"
                    arrivals.append(BusArrival(raw_time=arrival_time, display_time=display_time))

        arrivals.sort(key=lambda x: x.raw_time)
        return arrivals
