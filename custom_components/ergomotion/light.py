from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .core import DOMAIN
from .core.entity import XEntity


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, add_entities: AddEntitiesCallback
):
    device = hass.data[DOMAIN][config_entry.entry_id]
    add_entities([XLed(device, "led")])


class XLed(XEntity, LightEntity):
    _attr_icon = "mdi:lightbulb"
    _attr_supported_color_modes = {ColorMode.ONOFF}
    _attr_color_mode = ColorMode.ONOFF

    def __init__(self, device, attr: str):
        super().__init__(device, attr)
        self._attr_name = "Light"

    def internal_update(self):
        attribute = self.device.attribute(self.attr)
        self._attr_is_on = attribute.get("is_on")

        if self.hass:
            self._async_write_ha_state()

    async def async_turn_on(self, **kwargs) -> None:
        if not self._attr_is_on:
            self.device.toggle_light()

    async def async_turn_off(self, **kwargs) -> None:
        if self._attr_is_on:
            self.device.toggle_light()
