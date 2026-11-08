from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .core import DOMAIN
from .core.entity import XEntity

BUTTON_TYPES = [
    ("stop", "Stop", "mdi:stop-circle", "stop"),
]


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, add_entities: AddEntitiesCallback
):
    device = hass.data[DOMAIN][config_entry.entry_id]

    add_entities([
        XButton(device, attr, name, icon, method)
        for attr, name, icon, method in BUTTON_TYPES
    ])


class XButton(XEntity, ButtonEntity):
    def __init__(self, device, attr: str, display_name: str, icon: str, method: str):
        self._display_name = display_name
        self._attr_icon = icon
        self._method = method
        super().__init__(device, attr)
        self._attr_name = display_name

    def internal_update(self):
        pass

    async def async_press(self) -> None:
        handler = getattr(self.device, self._method, None)
        if callable(handler):
            handler()
