from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .core import DOMAIN
from .core.entity import XEntity

PRESET_OPTIONS = ["Flat", "Zero G", "Lounge", "Preset 1", "Preset 2", "Preset 3", "Custom"]


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, add_entities: AddEntitiesCallback
):
    device = hass.data[DOMAIN][config_entry.entry_id]
    add_entities([XPresetSelect(device, "preset")])


class XPresetSelect(XEntity, SelectEntity, RestoreEntity):
    _attr_icon = "mdi:bed-clock"
    _attr_options = PRESET_OPTIONS

    def __init__(self, device, attr: str):
        super().__init__(device, attr)
        self._attr_name = "Preset"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state:
            if state.state in PRESET_OPTIONS:
                self.device.current_preset = state.state
            if "preset1_head" in state.attributes and state.attributes["preset1_head"] is not None:
                self.device.preset1_head = state.attributes["preset1_head"]
            if "preset1_foot" in state.attributes and state.attributes["preset1_foot"] is not None:
                self.device.preset1_foot = state.attributes["preset1_foot"]
            if "preset2_head" in state.attributes and state.attributes["preset2_head"] is not None:
                self.device.preset2_head = state.attributes["preset2_head"]
            if "preset2_foot" in state.attributes and state.attributes["preset2_foot"] is not None:
                self.device.preset2_foot = state.attributes["preset2_foot"]
            if "preset3_head" in state.attributes and state.attributes["preset3_head"] is not None:
                self.device.preset3_head = state.attributes["preset3_head"]
            if "preset3_foot" in state.attributes and state.attributes["preset3_foot"] is not None:
                self.device.preset3_foot = state.attributes["preset3_foot"]

    @property
    def current_option(self) -> str:
        return self.device.current_preset

    @property
    def extra_state_attributes(self):
        return {
            "preset1_head": self.device.preset1_head,
            "preset1_foot": self.device.preset1_foot,
            "preset2_head": self.device.preset2_head,
            "preset2_foot": self.device.preset2_foot,
            "preset3_head": self.device.preset3_head,
            "preset3_foot": self.device.preset3_foot,
        }

    def internal_update(self):
        if self.hass:
            self._async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        self.device.select_preset(option)
