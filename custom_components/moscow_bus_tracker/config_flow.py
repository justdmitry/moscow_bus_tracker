"""Мастер настройки для Moscow Bus Tracker."""
import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import MoscowBusApiClient
from .const import (
    DOMAIN, CONF_API_KEY, CONF_ROUTE_NUMBER, CONF_STOP_SEARCH_QUERY,
    CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, CONF_ROUTE_ID,
    CONF_ROUTE_TYPE, CONF_ROUTE_SHORT_NAME, CONF_ROUTE_LONG_NAME, CONF_STOP_ID, CONF_STOP_NAME
)

_LOGGER = logging.getLogger(__name__)

class MoscowBusTrackerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Многошаговая настройка Moscow Bus Tracker."""
    VERSION = 1

    def __init__(self) -> None:
        super().__init__()
        self._api_key = ""
        self._route_number = ""
        self._scan_interval = DEFAULT_SCAN_INTERVAL
        
        self._ui_routes_options = {}
        self._clean_route_short_names = {}
        self._clean_route_long_names = {}
        self._ui_stops_options = {}
        self._clean_stop_names = {}
        self._map_links_markdown = ""

    async def async_step_user(self, user_input=None):
        """ШАГ 1: Ввод API-ключа."""
        if user_input is not None:
            self._api_key = user_input[CONF_API_KEY].strip()
            return await self.async_step_route()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): str})
        )

    async def async_step_route(self, user_input=None):
        """ШАГ 2: Ввод маршрута и ключевого слова остановки."""
        errors = {}

        if user_input is not None:
            self._route_number = user_input[CONF_ROUTE_NUMBER].strip().replace("'", "''")
            search_query = user_input[CONF_STOP_SEARCH_QUERY].strip().replace("'", "''")
            self._scan_interval = user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

            session = async_get_clientsession(self.hass)
            client = MoscowBusApiClient(session, self._api_key)
            
            try:
                # Работаем со строгими DTO объектами
                routes_data = await client.search_routes(self._route_number)
                stops_data = await client.search_stops(search_query)

                self._ui_routes_options = {}
                self._clean_route_names = {}
                for route in routes_data:
                    self._clean_route_short_names[route.route_id] = f"{route.route_type} {self._route_number}"
                    self._clean_route_long_names[route.route_id] = route.route_long_name
                    self._ui_routes_options[route.route_id] = f"{self._route_number} ({route.route_long_name}) [ID: {route.route_id}]"

                self._ui_stops_options = {}
                self._clean_stop_names = {}
                links_list = []

                for stop in stops_data:
                    self._clean_stop_names[stop.stop_id] = stop.stop_name
                    self._ui_stops_options[stop.stop_id] = f"{stop.stop_name} [ID: {stop.stop_id}]"
                    map_url = f"https://data.mos.ru/opendata/60662?objectId={stop.global_id}&filter=global_id%3D{stop.global_id}"
                    links_list.append(f"* [{stop.stop_name} (ID: {stop.stop_id})]({map_url})")

                if not self._ui_routes_options:
                    errors[CONF_ROUTE_NUMBER] = "route_not_found"
                elif not self._ui_stops_options:
                    errors[CONF_STOP_SEARCH_QUERY] = "no_stops_found"
                else:
                    self._map_links_markdown = "\n".join(links_list) if links_list else "Координаты не найдены."
                    return await self.async_step_stop()

            except Exception as err:
                _LOGGER.error("Ошибка при поиске данных через клиент: %s", err)
                errors["base"] = "cannot_connect"

        DATA_SCHEMA = vol.Schema({
            vol.Required(CONF_ROUTE_NUMBER): str,
            vol.Required(CONF_STOP_SEARCH_QUERY): str,
            vol.Optional(CONF_SCAN_INTERVAL, default=self._scan_interval): vol.All(int, vol.Range(min=1)),
        })
        return self.async_show_form(step_id="route", data_schema=DATA_SCHEMA, errors=errors)

    async def async_step_stop(self, user_input=None):
        """ШАГ 3: Выбор маршрута и остановки."""
        if user_input is not None:
            selected_route_id = user_input[CONF_ROUTE_ID]
            selected_stop_id = user_input[CONF_STOP_ID]
            
            selected_route_short_name = self._clean_route_short_names.get(selected_route_id, "")
            selected_stop_name = self._clean_stop_names.get(selected_stop_id, "")
            
            final_data = {
                CONF_API_KEY: self._api_key,
                CONF_ROUTE_NUMBER: self._route_number,
                CONF_ROUTE_ID: selected_route_id,
                CONF_ROUTE_SHORT_NAME: selected_route_short_name,
                CONF_ROUTE_LONG_NAME: self._clean_route_long_names.get(selected_route_id, ""),
                CONF_STOP_ID: selected_stop_id,
                CONF_STOP_NAME: selected_stop_name,
                CONF_SCAN_INTERVAL: self._scan_interval
            }

            await self.async_set_unique_id(f"{selected_route_id}_at_{selected_stop_id}")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"{selected_route_short_name} (Ост. {selected_stop_name})", 
                data=final_data
            )

        STOP_SCHEMA = vol.Schema({
            vol.Required(CONF_ROUTE_ID): vol.In(self._ui_routes_options),
            vol.Required(CONF_STOP_ID): vol.In(self._ui_stops_options)
        })

        return self.async_show_form(
            step_id="stop", 
            data_schema=STOP_SCHEMA, 
            description_placeholders={"map_links": self._map_links_markdown}
        )
