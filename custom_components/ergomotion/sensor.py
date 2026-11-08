from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .core import DOMAIN
from .core.entity import XEntity


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, add_entities: AddEntitiesCallback
):
    device = hass.data[DOMAIN][config_entry.entry_id]

    add_entities([
        XPositionSensor(device, "head", "Head Position", "mdi:seat-recline-extra"),
        XPositionSensor(device, "foot", "Foot Position", "mdi:seat-legroom-extra"),
    ])


class XPositionSensor(XEntity, SensorEntity, RestoreEntity):
    _attr_native_unit_of_measurement = "%"

    def __init__(self, device, motor: str, title: str, icon: str):
        self._motor = motor
        self._title = title
        self._attr_icon = icon
        super().__init__(device, f"{motor}_position")
        self._attr_name = title

    @property
    def max_position(self) -> int | None:
        return self.device.max_positions.get(self._motor)

    @property
    def is_calibrated(self) -> bool:
        return self.device.calibrated.get(self._motor, False)

    @property
    def extra_state_attributes(self):
        return {
            "raw_position": self.device.current_state.get(f"{self._motor}_position_raw", 0),
            "max_position": self.max_position,
            "calibrated": self.is_calibrated,
        }

    def internal_update(self):
        raw = self.device.current_state.get(f"{self._motor}_position_raw", 0)
        current_max = self.max_position

        if current_max and current_max > 0:
            pct = round((raw / current_max) * 100.0)
            self._attr_native_value = min(100, max(0, pct))
        elif raw == 0:
            self._attr_native_value = 0
        else:
            self._attr_native_value = None

        if self.hass:
            self._async_write_ha_state()
