from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .core import DOMAIN
from .core.device import Device

PLATFORMS = ["binary_sensor", "button", "cover", "light", "number", "select", "sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    devices = hass.data.setdefault(DOMAIN, {})

    @callback
    def update_ble(
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        if devices.get(entry.entry_id):
            return

        devices[entry.entry_id] = Device(
            entry.title or "Bed",
            service_info.device,
            hass=hass,
        )

        hass.create_task(
            hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        )

    entry.async_on_unload(
        bluetooth.async_register_callback(
            hass,
            update_ble,
            {"address": entry.data["mac"], "connectable": True},
            bluetooth.BluetoothScanningMode.ACTIVE,
        )
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    if entry.entry_id in hass.data[DOMAIN]:
        await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return True
