from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .core import DOMAIN
from .core.entity import XEntity


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, add_entities: AddEntitiesCallback
):
    device = hass.data[DOMAIN][config_entry.entry_id]

    add_entities([
        XBinarySensor(device, "connection", BinarySensorDeviceClass.CONNECTIVITY),
    ])


class XBinarySensor(XEntity, BinarySensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, device, attr: str, device_class=None):
        self._attr_device_class = device_class
        super().__init__(device, attr)

    def internal_update(self):
        attribute = self.device.attribute(self.attr)

        self._attr_is_on = attribute.get("is_on")
        self._attr_extra_state_attributes = attribute.get("extra")

        if self.hass:
            self._async_write_ha_state()
