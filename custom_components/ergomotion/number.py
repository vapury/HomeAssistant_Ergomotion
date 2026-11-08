from homeassistant.components.number import NumberEntity, NumberMode
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
        XPresetNumber(device, "Preset 1", "head", "Preset 1 Head Position", "mdi:seat-recline-extra"),
        XPresetNumber(device, "Preset 1", "foot", "Preset 1 Foot Position", "mdi:seat-legroom-extra"),
        XPresetNumber(device, "Preset 2", "head", "Preset 2 Head Position", "mdi:seat-recline-extra"),
        XPresetNumber(device, "Preset 2", "foot", "Preset 2 Foot Position", "mdi:seat-legroom-extra"),
        XPresetNumber(device, "Preset 3", "head", "Preset 3 Head Position", "mdi:seat-recline-extra"),
        XPresetNumber(device, "Preset 3", "foot", "Preset 3 Foot Position", "mdi:seat-legroom-extra"),
    ])


class XPresetNumber(XEntity, NumberEntity, RestoreEntity):
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0.0
    _attr_native_max_value = 100.0
    _attr_native_step = 1.0
    _attr_native_unit_of_measurement = "%"

    def __init__(self, device, preset: str, motor: str, title: str, icon: str):
        self._preset = preset
        self._motor = motor
        self._title = title
        self._attr_icon = icon

        key = f"{preset.lower().replace(' ', '')}_{motor}"
        super().__init__(device, key)
        self._attr_name = title

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state and state.state not in (None, "unknown", "unavailable"):
            try:
                val = int(float(state.state))
                self.device.set_preset_target(self._preset, self._motor, val)
                self._attr_native_value = float(val)
            except ValueError:
                pass

    @property
    def native_value(self) -> float | None:
        if self._preset == "Preset 1":
            return float(self.device.preset1_head if self._motor == "head" else self.device.preset1_foot)
        elif self._preset == "Preset 2":
            return float(self.device.preset2_head if self._motor == "head" else self.device.preset2_foot)
        else:
            return float(self.device.preset3_head if self._motor == "head" else self.device.preset3_foot)

    async def async_set_native_value(self, value: float) -> None:
        int_val = int(round(value))
        self.device.set_preset_target(self._preset, self._motor, int_val)
        self._attr_native_value = float(int_val)
        self.async_write_ha_state()

    def internal_update(self):
        if self.hass:
            self._async_write_ha_state()
