from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN, CONF_ROUTE_NUMBER, CONF_ROUTE_ID, CONF_ROUTE_SHORT_NAME, 
    CONF_ROUTE_LONG_NAME, CONF_STOP_ID, CONF_STOP_NAME
)

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Создание сенсора на основе координатора."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([MoscowBusSensor(coordinator, entry.data)], True)

class MoscowBusSensor(CoordinatorEntity, SensorEntity):
    """Сенсор, подписанный на данные координатора."""

    def __init__(self, coordinator, config):
        """Инициализация."""
        super().__init__(coordinator)
        self._route_number = config[CONF_ROUTE_NUMBER]
        self._route_id = config[CONF_ROUTE_ID]
        self._route_short_name = config.get(CONF_ROUTE_SHORT_NAME, "")
        self._route_long_name = config.get(CONF_ROUTE_LONG_NAME, "")
        self._stop_id = config[CONF_STOP_ID]
        self._stop_name = config.get(CONF_STOP_NAME, f"Остановка {self._stop_id}")

        self._attr_name = f"{self._route_short_name} — {self._stop_name}"
        self.entity_id = f"sensor.mos_bus_{self._route_id}_at_{self._stop_id}"
        self._attr_unique_id = f"moscow_bus_tracker_{self._route_id}_at_{self._stop_id}"
        self._attr_icon = "mdi:bus"

        #self._attr_device_info = {
        #    "identifiers": {(DOMAIN, f"device_{self._stop_id}_{self._route_id}")},
        #    "name": f"Маршрут {self._route_number} ({self._stop_name})",
        #    "manufacturer": "Mos.ru",
        #    "model": "Расписание Мосгортранс",
        #}

    @property
    def native_value(self):
        """Берем данные напрямую из кэша координатора."""
        arrivals = self.coordinator.data
        if arrivals and len(arrivals) > 0:
            return arrivals[0].display_time
        return "Рейсов нет"

    @property
    def extra_state_attributes(self):
        """Формируем атрибуты из кэша координатора."""
        arrivals = self.coordinator.data
        upcoming = [arrival.display_time for arrival in arrivals[1:]] if arrivals else []
        return {
            "upcoming_buses": upcoming,
            "route_number": self._route_number,
            "route_id": self._route_id,
            "route_long_name": self._route_long_name,
            "stop_id": self._stop_id,
            "stop_name": self._stop_name,
        }
