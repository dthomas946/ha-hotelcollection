"""Config flow: ask for the diffuser's IP and check that it answers."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT

from .client import HotelCollectionClient, HotelCollectionError
from .codec import CMD_NAME, decode_name
from .const import DEFAULT_PORT, DOMAIN

SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Optional(CONF_NAME, default="Villa"): str,
    }
)


class HotelCollectionConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()
            client = HotelCollectionClient(host, user_input[CONF_PORT])
            try:
                frame = await client.read(CMD_NAME)
                device_name = decode_name(frame.payload)
            except HotelCollectionError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={**user_input, CONF_HOST: host, "device_name": device_name},
                )
            finally:
                await client.close()
        return self.async_show_form(step_id="user", data_schema=SCHEMA, errors=errors)
