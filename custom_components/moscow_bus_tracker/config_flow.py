import voluptuous as vol
from datetime import timedelta
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, ConfigSubentryFlow, SubentryFlowResult, OptionsFlowWithReload
from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.translation import async_get_translations
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import *
from .api import MoscowOpenDataApiClient, MoscowOpenDataApiError, MoscowOpenDataApiAuthError
from .coordinator import BusTrackerCoordinator

class BusTrackerConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            api_key = user_input.get(CONF_API_KEY, "").strip()

            if not api_key:
                errors[CONF_API_KEY] = "empty_field"
            else:
                session = async_get_clientsession(self.hass)
                api_client = MoscowOpenDataApiClient(session, api_key)

                try:
                    await api_client.check_key()

                    masked_key = f"{api_key[:3]}…{api_key[-3:]}"

                    translations = await async_get_translations(
                        hass=self.hass,
                        language=self.hass.config.language,
                        category="config",
                        integrations=[DOMAIN]
                    )
                    translated_string = translations.get(f"component.{DOMAIN}.config.flow_title", "Key {masked_key}")

                    return self.async_create_entry(
                        title=translated_string.format(masked_key=masked_key),
                        data={CONF_API_KEY: api_key }
                    )

                except MoscowOpenDataApiAuthError:
                    errors[CONF_API_KEY] = "invalid_auth"
                except MoscowOpenDataApiError:
                    errors["base"] = "request_error"

        data_schema = vol.Schema({
            vol.Required(CONF_API_KEY): str,
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors
        )

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, config_entry: ConfigEntry) -> dict[str, type[ConfigSubentryFlow]]:
        return {"route": BusTrackerRouteSubentryFlow}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return BusTrackerOptionsFlow()

class BusTrackerOptionsFlow(OptionsFlowWithReload):
    async def async_step_init(self, user_input = None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options_schema = vol.Schema({
            vol.Optional(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL_MINUTES): vol.All(int, vol.Range(min=10)),
            vol.Optional(CONF_SHOW_MISSED_INTERVAL, default=DEFAULT_SHOW_MISSED_INTERVAL_MINUTES): vol.All(int, vol.Range(min=0)),
            vol.Optional(CONF_NEWDAY_SHIFT, default=DEFAULT_NEWDAY_SHIFT_MINUTES): int,
        })

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                options_schema,
                self.config_entry.options
            ),
        )

class BusTrackerRouteSubentryFlow(ConfigSubentryFlow):
    VERSION = 1

    def __init__(self) -> None:
        super().__init__()

        self._route_number = ""
        self._stops_query = ""

        self._ui_routes_options = {}
        self._all_routes = {}
        self._ui_stops_options = {}
        self._all_stops = {}
        self._map_links_markdown = ""

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            self._route_number = user_input.get(CONF_ROUTE_NUMBER, "").strip().replace("'", "''")
            self._stops_query = user_input.get(CONF_STOPS_QUERY, "").strip().replace("'", "''")

            if not self._route_number:
                errors[CONF_ROUTE_NUMBER] = "empty_field"
            elif not self._stops_query:
                errors[CONF_STOPS_QUERY] = "empty_field"
            else:
                entry = self._get_entry()
                api_key = entry.data[CONF_API_KEY]

                session = async_get_clientsession(self.hass)
                api_client = MoscowOpenDataApiClient(session, api_key)

                try:
                    routes_data = await api_client.search_routes(self._route_number)
                    stops_data = await api_client.search_stops(self._stops_query)

                    self._ui_routes_options = {}
                    self._all_routes = {}
                    for route in routes_data:
                        self._ui_routes_options[route.route_id] = f"{route.route_short_name} ({route.route_long_name}) [ID: {route.route_id}]"
                        self._all_routes[route.route_id] = route

                    self._ui_stops_options = {}
                    self._all_stops = {}
                    links_list = []

                    for stop in stops_data:
                        self._ui_stops_options[stop.stop_id] = f"{stop.stop_name} [ID: {stop.stop_id}]"
                        self._all_stops[stop.stop_id] = stop
                        map_url = f"https://data.mos.ru/opendata/60662?objectId={stop.global_id}&filter=global_id%3D{stop.global_id}"
                        links_list.append(f"* [{stop.stop_name} (ID: {stop.stop_id})]({map_url})")

                    if not self._ui_routes_options:
                        errors[CONF_ROUTE_NUMBER] = "route_not_found"
                    elif not self._ui_stops_options:
                        errors[CONF_STOPS_QUERY] = "no_stops_found"
                    else:
                        self._map_links_markdown = "\n".join(links_list)
                        return await self.async_step_choice()

                except MoscowOpenDataApiError:
                    errors["base"] = "cannot_connect"

        data_schema = vol.Schema({
            vol.Required(CONF_ROUTE_NUMBER): str,
            vol.Required(CONF_STOPS_QUERY): str,
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors
        )

    async def async_step_choice(self, user_input=None):
        if user_input is not None:
            selected_route_id = user_input[CONF_ROUTE_ID]
            selected_stop_id = user_input[CONF_STOP_ID]

            selected_route = self._all_routes.get(selected_route_id)
            selected_stop = self._all_stops.get(selected_stop_id)

            translations_common = await async_get_translations(
                hass=self.hass,
                language=self.hass.config.language,
                category="common",
                integrations=[DOMAIN]
            )
            translated_route_type = translations_common.get(f"component.{DOMAIN}.common.route_type_names.{selected_route.route_type}", translations_common.get(f"component.{DOMAIN}.common.route_type_names.default"))

            translations_subentries = await async_get_translations(
                hass=self.hass,
                language=self.hass.config.language,
                category="config_subentries",
                integrations=[DOMAIN]
            )
            translated_title = translations_subentries.get(f"component.{DOMAIN}.config_subentries.route.flow_title", "Route {route_name} at {stop_name} ({stop_id})")

            final_title = translated_title.format(
                route_type=translated_route_type,
                route_name=selected_route.route_short_name,
                stop_name=selected_stop.stop_name,
                stop_id=selected_stop_id,
            )

            final_data = {
                CONF_ROUTE_ID: selected_route_id,
                CONF_ROUTE_TYPE: selected_route.route_type,
                CONF_ROUTE_TYPE_NAME: translated_route_type,
                CONF_ROUTE_SHORT_NAME: selected_route.route_short_name,
                CONF_ROUTE_LONG_NAME: selected_route.route_long_name,
                CONF_STOP_ID: selected_stop_id,
                CONF_STOP_NAME: selected_stop.stop_name
            }

            return self.async_create_entry(
                title=final_title,
                unique_id=f"route_{selected_route_id}_stop_{selected_stop_id}",
                data=final_data
            )

        STOP_SCHEMA = vol.Schema({
            vol.Required(CONF_ROUTE_ID): vol.In(self._ui_routes_options),
            vol.Required(CONF_STOP_ID): vol.In(self._ui_stops_options)
        })

        return self.async_show_form(
            step_id="choice",
            data_schema=STOP_SCHEMA,
            description_placeholders={"map_links": self._map_links_markdown}
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return BusTrackerOptionsFlow()
