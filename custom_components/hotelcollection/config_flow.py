"""Config flow: ask for the diffuser's IP and check that it answers."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers import selector

from .client import HotelCollectionClient, HotelCollectionError
from .codec import CMD_NAME, decode_name
from .const import CONF_HVAC_FAN_ENTITY, CONF_START_DELAY, DEFAULT_PORT, DEFAULT_START_DELAY, DOMAIN

SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Optional(CONF_NAME, default="Villa"): str,
    }
)


class HotelCollectionConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return HotelCollectionOptionsFlow()

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


class HotelCollectionOptionsFlow(OptionsFlow):
    """HVAC pause: which entity says the HVAC fan is running, and the start delay."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            if not user_input.get(CONF_HVAC_FAN_ENTITY):
                user_input.pop(CONF_HVAC_FAN_ENTITY, None)
            return self.async_create_entry(data=user_input)
        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_HVAC_FAN_ENTITY,
                    description={"suggested_value": opts.get(CONF_HVAC_FAN_ENTITY)},
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=["climate", "binary_sensor", "sensor", "switch", "fan", "input_boolean"]
                    )
                ),
                vol.Optional(
                    CONF_START_DELAY, default=opts.get(CONF_START_DELAY, DEFAULT_START_DELAY)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=300, step=5, unit_of_measurement="s",
                                                  mode=selector.NumberSelectorMode.BOX)
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
