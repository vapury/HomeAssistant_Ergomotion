from homeassistant.components.cover import (
    CoverEntity,
    CoverEntityFeature,
    CoverDeviceClass,
)
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
        XCover(device, "head_position", "Head", "head"),
        XCover(device, "foot_position", "Foot", "foot"),
    ])


class XCover(XEntity, CoverEntity, RestoreEntity):
    _attr_device_class = CoverDeviceClass.DAMPER
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_POSITION
    )

    def __init__(self, device, attr: str, title: str, motor: str):
        self._motor = motor
        self._title = title
        self._attr_extra_state_attributes = {
            "max_position": None,
            "calibrated": False,
            "raw_position": 0,
        }
        super().__init__(device, attr)
        self._attr_name = title

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state and "max_position" in state.attributes:
            stored_max = state.attributes.get("max_position")
            if stored_max:
                self.device.set_max_position(self._motor, stored_max)

    @property
    def max_position(self) -> int | None:
        return self.device.max_positions.get(self._motor)

    @property
    def is_calibrated(self) -> bool:
        return self.device.calibrated.get(self._motor, False)

    @property
    def extra_state_attributes(self):
        return {
            "max_position": self.max_position,
            "calibrated": self.is_calibrated,
            "raw_position": self.device.current_state.get(f"{self._motor}_position_raw", 0),
        }

    def internal_update(self):
        attribute = self.device.attribute(self.attr)
        pos = attribute.get("position")
        if pos is None:
            return

        current_max = self.max_position

        if current_max and current_max > 0:
            scaled = round((pos / current_max) * 100.0)
            self._attr_current_cover_position = min(100, max(0, scaled))
            self._attr_is_closed = self._attr_current_cover_position == 0
        else:
            self._attr_current_cover_position = 0 if pos == 0 else None
            self._attr_is_closed = pos == 0

        if self.hass:
            self._async_write_ha_state()

    async def async_open_cover(self, **kwargs) -> None:
        self.device.manual_cover_moved()
        if self.is_calibrated:
            await self.async_set_cover_position(position=100)
        else:
            await self.device.move_to_raw_target(self._motor, 20000)

    async def async_close_cover(self, **kwargs) -> None:
        self.device.manual_cover_moved()
        await self.async_set_cover_position(position=0)

    async def async_stop_cover(self, **kwargs) -> None:
        self.device.stop()

    async def async_set_cover_position(self, **kwargs) -> None:
        target_pct = kwargs.get("position", 0)
        self.device.manual_cover_moved()

        if not self.is_calibrated:
            await self.async_open_cover()
            return

        target_raw = round((target_pct / 100.0) * self.max_position)
        await self.device.move_to_raw_target(self._motor, target_raw)
