from datetime import timedelta
import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.event import async_track_time_interval
import homeassistant.util.dt as dt_util

from .const import *
from .coordinator import BusTrackerCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:

    entities = []

    api_client = entry.runtime_data

    newday_shift_interval = entry.options.get(CONF_NEWDAY_SHIFT, DEFAULT_NEWDAY_SHIFT_MINUTES)
    update_interval = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL_MINUTES)

    for subentry in entry.subentries.values():
        coordinator = BusTrackerCoordinator(
            hass,
            api_client,
            timedelta(minutes=update_interval),
            timedelta(minutes=newday_shift_interval),
            subentry.data[CONF_ROUTE_ID],
            subentry.data[CONF_STOP_ID],
        )

        await coordinator.async_config_entry_first_refresh()

        entities.append(BusArrivalSensor(
            coordinator,
            entry,
            subentry,
        ))

    async_add_entities(entities)

def get_route_type_icon(route_type):
    route_mapper = {
        "0": "mdi:tram",
        "1": "mdi:subway-variant",
        "2": "mdi:train",
        "3": "mdi:bus",
        "4": "mdi:ferry",
        "5": "mdi:cable-car",
        "6": "mdi:gondola",
        "7": "mdi:slope-downhill",
        "11": "mdi:bus-electric",
        "12": "mdi:railroad-light",
    }
    return route_mapper.get(str(route_type), "mdi:transit-connection-variant")

class BusArrivalSensor(CoordinatorEntity, SensorEntity):

    def __init__(self, coordinator, entry, subentry):
        super().__init__(coordinator)

        self._upcoming_count = entry.options.get(CONF_UPCOMING_COUNT, DEFAULT_UPCOMING_COUNT)
        self._missed_interval = timedelta(minutes=entry.options.get(CONF_MISSED_INTERVAL, DEFAULT_MISSED_INTERVAL_MINUTES))
        self._missed_color = entry.options.get(CONF_MISSED_COLOR, DEFAULT_MISSED_COLOR)
        self._missed_badge = entry.options.get(CONF_MISSED_BADGE, DEFAULT_MISSED_BADGE)
        self._arriving_interval = timedelta(minutes=entry.options.get(CONF_ARRIVING_INTERVAL, DEFAULT_ARRIVING_INTERVAL_MINUTES))
        self._arriving_color = entry.options.get(CONF_ARRIVING_COLOR, DEFAULT_ARRIVING_COLOR)
        self._arriving_badge = entry.options.get(CONF_ARRIVING_BADGE, DEFAULT_ARRIVING_BADGE)
        self._default_color = entry.options.get(CONF_DEFAULT_COLOR, DEFAULT_DEFAULT_COLOR)

        self._route_id = subentry.data[CONF_ROUTE_ID]
        self._route_type = subentry.data[CONF_ROUTE_TYPE]
        self._route_short_name = subentry.data[CONF_ROUTE_SHORT_NAME]
        self._route_long_name = subentry.data[CONF_ROUTE_LONG_NAME]
        self._stop_id = subentry.data[CONF_STOP_ID]
        self._stop_name = subentry.data[CONF_STOP_NAME]

        self.entity_id = f"sensor.{subentry.unique_id}"
        self._attr_attribution = "Data provided by Open Data Portal of Moscow Government"
        self._attr_name = subentry.title
        self._attr_unique_id = f"{DOMAIN}.{subentry.unique_id}"
        self._attr_icon = get_route_type_icon(self._route_type)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_interval(
                self.hass,
                self._async_minute_tick,
                timedelta(minutes=1),
            )
        )

    @callback
    def _async_minute_tick(self, now_time) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self):
        valid_arrivals, _, _ = self._get_filtered_arrivals()
        if valid_arrivals:
            return valid_arrivals[0].display_time

    @property
    def extra_state_attributes(self):
        valid_arrivals, missed, arriving = self._get_filtered_arrivals()
        upcoming = [] if self._upcoming_count <= 0 else [arrival.display_time for arrival in valid_arrivals[1:]][:self._upcoming_count]
        icon_color = self._missed_color if missed else (self._arriving_color if arriving else self._default_color)
        icon_badge = self._missed_badge if missed else (self._arriving_badge if arriving else None)
        return {
            "missed": missed,
            "arriving": arriving,
            "icon_color": icon_color,
            "icon_badge": icon_badge,
            "upcoming": upcoming,
            "route_id": self._route_id,
            "route_type": self._route_type,
            "route_short_name": self._route_short_name,
            "route_long_name": self._route_long_name,
            "stop_id": self._stop_id,
            "stop_name": self._stop_name,
        }

    def _get_filtered_arrivals(self) -> tuple[list, bool, bool]:
        all_arrivals = self.coordinator.data
        if not all_arrivals:
            return [], false, false

        now = dt_util.now()
        now_str = now.strftime("%H:%M:%S")
        threshold_missed = (now - self._missed_interval)
        threshold_missed_str = threshold_missed.strftime("%H:%M:%S")

        threshold_arriving = (now + self._arriving_interval)
        threshold_arriving_str = threshold_arriving.strftime("%H:%M:%S")

        filtered = [arrival for arrival in all_arrivals if arrival.raw_time >= threshold_missed_str]
        missed = bool(filtered and filtered[0].raw_time <= now_str)
        arriving = bool(filtered and filtered[0].raw_time <= threshold_arriving_str)

        return filtered, missed, arriving
