import voluptuous as vol
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigFlow

from .core import DOMAIN


class FlowHandler(ConfigFlow, domain=DOMAIN):
    async def async_step_user(self, user_input=None):
        if user_input is not None:
            mac = user_input["mac"].strip().upper()
            await self.async_set_unique_id(mac)
            self._abort_if_unique_id_configured()
            title = user_input.get("title") or f"Ergomotion {mac[-5:]}"
            return self.async_create_entry(title=title, data={"mac": mac})

        discovered = bluetooth.async_discovered_service_info(self.hass, connectable=True)
        device_choices = {}
        for d in discovered:
            name = d.name or "Unknown"
            device_choices[d.address] = f"{name} ({d.address})"

        if device_choices:
            schema = vol.Schema({
                vol.Required("mac"): vol.In(device_choices),
                vol.Optional("title", default="Ergomotion Bed"): str,
            })
        else:
            schema = vol.Schema({
                vol.Required("mac"): str,
                vol.Optional("title", default="Ergomotion Bed"): str,
            })

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
        )
