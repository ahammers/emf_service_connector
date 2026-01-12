from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_BASE_URL,
    CONF_API_KEY,
    CONF_SITE_FID,
    CONF_DATAPOINT_TS_MODE,
    CONF_DATAPOINT_TS_ENTITY,
    CONF_EM_POWER_GRID_ENTITY,
    CONF_QUEUE_MAX_LEN,
    CONF_QUEUE_MAX_SEND_PER_TICK,
    ADV_FIELDS,
    DEFAULT_BASE_URL,
    DEFAULT_QUEUE_MAX_LEN,
    DEFAULT_QUEUE_MAX_SEND_PER_TICK,
)


def _entity_sel(domains: list[str] | None = None) -> dict:
    filt = {"domain": domains} if domains else {}
    return selector.selector({"entity": {"filter": filt, "multiple": False}})


class EmfServiceConnectorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="EMF Service Connector", data=dict(user_input))

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
                # Queue defaults (can be changed later via options)
                vol.Required(CONF_QUEUE_MAX_LEN, default=DEFAULT_QUEUE_MAX_LEN): vol.All(int, vol.Range(min=0)),
                vol.Required(CONF_QUEUE_MAX_SEND_PER_TICK, default=DEFAULT_QUEUE_MAX_SEND_PER_TICK): vol.All(int, vol.Range(min=0)),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return EmfServiceConnectorOptionsFlow(config_entry)


class EmfServiceConnectorOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self.entry = entry
        self._standard: dict = {}

    async def async_step_init(self, user_input=None):
        current = {**self.entry.data, **self.entry.options}

        if user_input is not None:
            self._standard = dict(user_input)
            return self.async_show_menu(step_id="menu", menu_options=["finish", "advanced"])

        schema = vol.Schema(
            {
                vol.Required(CONF_BASE_URL, default=current.get(CONF_BASE_URL, DEFAULT_BASE_URL)): str,
                vol.Required(CONF_API_KEY, default=current.get(CONF_API_KEY, "")): str,
                vol.Required(CONF_SITE_FID, default=current.get(CONF_SITE_FID, "")): str,
                vol.Required(CONF_DATAPOINT_TS_MODE, default=current.get(CONF_DATAPOINT_TS_MODE, "now")): selector.selector(
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
                vol.Optional(CONF_DATAPOINT_TS_ENTITY, default=current.get(CONF_DATAPOINT_TS_ENTITY)): _entity_sel(),
                vol.Required(CONF_EM_POWER_GRID_ENTITY, default=current.get(CONF_EM_POWER_GRID_ENTITY)): _entity_sel(
                    domains=["sensor", "number", "input_number"]
                ),
                vol.Required(CONF_QUEUE_MAX_LEN, default=current.get(CONF_QUEUE_MAX_LEN, DEFAULT_QUEUE_MAX_LEN)): vol.All(int, vol.Range(min=0)),
                vol.Required(CONF_QUEUE_MAX_SEND_PER_TICK, default=current.get(CONF_QUEUE_MAX_SEND_PER_TICK, DEFAULT_QUEUE_MAX_SEND_PER_TICK)): vol.All(int, vol.Range(min=0)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_menu(self, user_input=None):
        return self.async_show_menu(step_id="menu", menu_options=["finish", "advanced"])

    async def async_step_finish(self, user_input=None):
        return self.async_create_entry(title="", data=self._standard)

    async def async_step_advanced(self, user_input=None):
        current = {**self.entry.data, **self.entry.options}

        if user_input is not None:
            data = {**self._standard, **user_input}
            return self.async_create_entry(title="", data=data)

        adv_schema_dict = {}
        for conf_key, _api_key in ADV_FIELDS:
            adv_schema_dict[vol.Optional(conf_key, default=current.get(conf_key))] = _entity_sel(
                domains=["sensor", "number", "input_number"]
            )
        return self.async_show_form(step_id="advanced", data_schema=vol.Schema(adv_schema_dict))
