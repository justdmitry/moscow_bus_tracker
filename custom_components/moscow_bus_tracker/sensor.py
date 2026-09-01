from datetime import timedelta
import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.event import async_track_time_interval
import homeassistant.util.dt as dt_util

from .const import (
    DOMAIN, CONF_ROUTE_NUMBER, CONF_ROUTE_ID, CONF_ROUTE_SHORT_NAME, 
    CONF_ROUTE_LONG_NAME, CONF_STOP_ID, CONF_STOP_NAME
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([MoscowBusSensor(coordinator, entry.data)], True)

class MoscowBusSensor(CoordinatorEntity, SensorEntity):

    def __init__(self, coordinator, config):
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

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        
        # Регистрируем внутренний таймер HA, который раз в 60 секунд 
        # принудительно заставляет датчик пересчитать свойства (БЕЗ запроса в сеть!)
        self.async_on_remove(
            async_track_time_interval(
                self.hass,
                self._async_minute_tick,
                timedelta(minutes=1),
            )
        )

    @callback
    def _async_minute_tick(self, now_time) -> None:
        """Триггер таймера: заставляем HA перерисовать состояние."""
        self.async_write_ha_state()

    def _get_filtered_arrivals(self) -> list:
        """Вспомогательный метод фильтрации кэша координатора под текущую минуту."""
        all_arrivals = self.coordinator.data
        if not all_arrivals:
            return []

        # Вычисляем порог "Текущее время минус 5 минут" прямо сейчас
        now = dt_util.now()
        time_threshold = now - timedelta(minutes=5)
        threshold_str = time_threshold.strftime("%H:%M:%S")

        # Фильтруем массив DTO, который лежит в памяти координатора
        # Сравниваем raw_time ("15:35:00" >= "15:25:00")
        return [arrival for arrival in all_arrivals if arrival.raw_time >= threshold_str]

    @property
    def native_value(self):
        """Главное состояние — динамически вычисляется каждую минуту."""
        valid_arrivals = self._get_filtered_arrivals()
        if valid_arrivals:
            return valid_arrivals[0].display_time
        return "Рейсов нет"

    @property
    def extra_state_attributes(self):
        """Атрибуты — динамически вычисляются каждую минуту."""
        valid_arrivals = self._get_filtered_arrivals()
        upcoming = [arrival.display_time for arrival in valid_arrivals[1:]]
        return {
            "upcoming_buses": upcoming[:5],  # отдаем топ-5 актуальных на эту минуту
            "route_number": self._route_number,
            "route_id": self._route_id,
            "route_long_name": self._route_long_name,
            "stop_id": self._stop_id,
            "stop_name": self._stop_name,
        }
