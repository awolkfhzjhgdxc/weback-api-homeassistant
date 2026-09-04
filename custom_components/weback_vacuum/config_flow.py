"""Config flow for WeBack Vacuum."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import (
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_API_VERSION,
    CONF_CLIENT_ID,
)
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from .webackapi import WebackApi
from .const import (
    DOMAIN,
    CONF_REGION,
    CONF_LANGUAGE,
    CONF_APP,
    DEFAULT_LANGUAGE,
    DEFAULT_APP,
    DEFAULT_CLIENT_ID,
    DEFAULT_API_VERS,
    REGIONS,
    APPS,
)

class WeBackConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            api = WebackApi(
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                user_input[CONF_REGION],
                user_input[CONF_LANGUAGE],
                user_input[CONF_APP],
                user_input[CONF_CLIENT_ID],
                user_input[CONF_API_VERSION],
            )
            if await api.login():
                robots = await api.get_robot_list()
                if robots:
                    return self.async_create_entry(
                        title=f"WeBack ({user_input[CONF_USERNAME]})",
                        data=user_input,
                    )
                errors["base"] = "no_robots"
            else:
                errors["base"] = "invalid_auth"

        data_schema = vol.Schema({
            vol.Required(CONF_USERNAME): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Required(CONF_REGION): SelectSelector(
                SelectSelectorConfig(options=list(REGIONS.keys()), mode=SelectSelectorMode.DROPDOWN)
            ),
            vol.Optional(CONF_LANGUAGE, default=DEFAULT_LANGUAGE): SelectSelector(
                SelectSelectorConfig(options=["en", "ru", "zh"], mode=SelectSelectorMode.DROPDOWN)
            ),
            vol.Optional(CONF_APP, default=DEFAULT_APP): SelectSelector(
                SelectSelectorConfig(options=list(APPS.keys()), mode=SelectSelectorMode.DROPDOWN)
            ),
            vol.Optional(CONF_CLIENT_ID, default=DEFAULT_CLIENT_ID): str,
            vol.Optional(CONF_API_VERSION, default=DEFAULT_API_VERS): str,
        })
        return self.async_show_form(step_id="user", data_schema=data_schema, errors=errors)
