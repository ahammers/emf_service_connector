from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_BASE_URL,
    CONF_API_KEY,
    CONF_SITE_FID,
    CONF_DATAPOINT_TS_MODE,
    CONF_DATAPOINT_TS_ENTITY,
    CONF_EM_POWER_GRID_ENTITY,
    ADV_FIELDS,
    DEFAULT_BASE_URL,
)


def _entity_sel(domains: list[str] | None = None) -> dict:
    filt = {"domain": domains} if domains else {}
    return selector.selector(
        {
            "entity": {
                "filter": filt,
                "multiple": False,
            }
        }
    )


class EmfServiceConnectorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._standard: dict = {}

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            self._standard = dict(user_input)
            return self.async_show_menu(
                step_id="menu",
                menu_options=["finish", "advanced"],
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_BASE_URL, default=DEFAULT_BASE_URL): str,
                vol.Required(CONF_API_KEY): str,
                vol.Required(CONF_SITE_FID): str,
                vol.Required(CONF_DATAPOINT_TS_MODE, default="now"): selector.selector(
                    {
                        "select": {
                            "options": [
                                {"value": "now", "label": "now (Home Assistant Zeit)"},
                                {"value": "entity", "label": "aus Entität"},
                            ],
                            "mode": "dropdown",
                        }
                    }
                ),
                vol.Optional(CONF_DATAPOINT_TS_ENTITY): _entity_sel(),
                vol.Required(CONF_EM_POWER_GRID_ENTITY): _entity_sel(domains=["sensor", "number", "input_number"]),
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_menu(self, user_input=None):
        return self.async_show_menu(step_id="menu", menu_options=["finish", "advanced"])

    async def async_step_finish(self, user_input=None):
        return self.async_create_entry(title="EMF Service Connector", data=self._standard)

    async def async_step_advanced(self, user_input=None):
        if user_input is not None:
            data = {**self._standard, **user_input}
            return self.async_create_entry(title="EMF Service Connector", data=data)

        adv_schema_dict = {}
        for conf_key, _api_key_name in ADV_FIELDS:
            adv_schema_dict[vol.Optional(conf_key)] = _entity_sel(domains=["sensor", "number", "input_number"])

        schema = vol.Schema(adv_schema_dict)
        return self.async_show_form(step_id="advanced", data_schema=schema)
