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


def _select_ts_mode(default: str = "now") -> dict:
    return selector.selector(
        {
            "select": {
                "options": [
                    {"value": "now", "label": "now (Home Assistant Zeit)"},
                    {"value": "entity", "label": "aus Entität"},
                ],
                "mode": "dropdown",
            }
        }
    )


def _sanitize_ts_fields(data: dict) -> dict:
    """Ensure datapoint_ts_entity is only stored/validated when mode == entity."""
    mode = data.get(CONF_DATAPOINT_TS_MODE, "now")
    if mode != "entity":
        data.pop(CONF_DATAPOINT_TS_ENTITY, None)
    else:
        # If mode is entity but no entity given, keep it missing -> later validation will catch if required
        if not data.get(CONF_DATAPOINT_TS_ENTITY):
            data.pop(CONF_DATAPOINT_TS_ENTITY, None)
    return data


def _merge_current(entry: config_entries.ConfigEntry) -> dict:
    # options win
    return {**entry.data, **entry.options}


class EmfServiceConnectorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._standard: dict = {}

    def _entry_title_from_site(self, data: dict) -> str:
        site = data.get(CONF_SITE_FID) or "UNKNOWN"
        return f"EMF Service Connection to {site}"

    async def async_step_user(self, user_input=None):
        """
        Standard step: minimal required fields only.
        Advanced step: everything else (including base_url, ts mode/entity, queue settings, advanced mappings).
        """
        if user_input is not None:
            self._standard = dict(user_input)
            return self.async_show_menu(step_id="menu", menu_options=["finish", "advanced"])

        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY): str,
                vol.Required(CONF_SITE_FID): str,
                vol.Required(CONF_EM_POWER_GRID_ENTITY): _entity_sel(domains=["sensor", "number", "input_number"]),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_menu(self, user_input=None):
        return self.async_show_menu(step_id="menu", menu_options=["finish", "advanced"])

    async def async_step_finish(self, user_input=None):
        # store standard only (advanced optional via options)
        data = dict(self._standard)
        return self.async_create_entry(title=self._entry_title_from_site(data), data=data)

    async def async_step_advanced(self, user_input=None):
        if user_input is not None:
            data = {**self._standard, **_sanitize_ts_fields(dict(user_input))}
            return self.async_create_entry(title=self._entry_title_from_site(data), data=data)

        # Defaults for advanced on first setup
        adv = {
            CONF_BASE_URL: DEFAULT_BASE_URL,
            CONF_DATAPOINT_TS_MODE: "now",
            CONF_QUEUE_MAX_LEN: DEFAULT_QUEUE_MAX_LEN,
            CONF_QUEUE_MAX_SEND_PER_TICK: DEFAULT_QUEUE_MAX_SEND_PER_TICK,
        }

        adv_schema_dict: dict = {
            vol.Required(CONF_BASE_URL, default=adv[CONF_BASE_URL]): str,
            vol.Required(CONF_DATAPOINT_TS_MODE, default=adv[CONF_DATAPOINT_TS_MODE]): _select_ts_mode(),
            # Important: NO default=None here -> avoids "Entity None ..." validation issues
            vol.Optional(CONF_DATAPOINT_TS_ENTITY): _entity_sel(),
            vol.Required(CONF_QUEUE_MAX_LEN, default=adv[CONF_QUEUE_MAX_LEN]): vol.All(int, vol.Range(min=0)),
            vol.Required(CONF_QUEUE_MAX_SEND_PER_TICK, default=adv[CONF_QUEUE_MAX_SEND_PER_TICK]): vol.All(int, vol.Range(min=0)),
        }

        # Advanced field mappings
        for conf_key, _api_key_name in ADV_FIELDS:
            adv_schema_dict[vol.Optional(conf_key)] = _entity_sel(domains=["sensor", "number", "input_number"])

        return self.async_show_form(step_id="advanced", data_schema=vol.Schema(adv_schema_dict))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return EmfServiceConnectorOptionsFlow(config_entry)


class EmfServiceConnectorOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self.entry = entry
        self._standard: dict = {}

    async def async_step_init(self, user_input=None):
        """
        Standard options step: same as initial standard step.
        Advanced options step: base_url, ts mode/entity, queue settings, advanced mappings.
        """
        current = _merge_current(self.entry)

        if user_input is not None:
            self._standard = dict(user_input)
            return self.async_show_menu(step_id="menu", menu_options=["finish", "advanced"])

        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY, default=current.get(CONF_API_KEY, "")): str,
                vol.Required(CONF_SITE_FID, default=current.get(CONF_SITE_FID, "")): str,
                vol.Required(CONF_EM_POWER_GRID_ENTITY, default=current.get(CONF_EM_POWER_GRID_ENTITY)): _entity_sel(
                    domains=["sensor", "number", "input_number"]
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_menu(self, user_input=None):
        return self.async_show_menu(step_id="menu", menu_options=["finish", "advanced"])

    async def async_step_finish(self, user_input=None):
        # only store options; also sanitize ts fields the same way as initial setup
        options = _sanitize_ts_fields(dict(self._standard))
        return self.async_create_entry(title="", data=options)

    async def async_step_advanced(self, user_input=None):
        current = _merge_current(self.entry)

        if user_input is not None:
            data = {**self._standard, **_sanitize_ts_fields(dict(user_input))}
            return self.async_create_entry(title="", data=data)

        # Advanced options: must allow saving unchanged even if datapoint_ts_entity is absent.
        adv_schema_dict: dict = {
            vol.Required(CONF_BASE_URL, default=current.get(CONF_BASE_URL, DEFAULT_BASE_URL)): str,
            vol.Required(CONF_DATAPOINT_TS_MODE, default=current.get(CONF_DATAPOINT_TS_MODE, "now")): _select_ts_mode(),
            # CRITICAL FIX: only set default if we actually have a value. If None, omit default completely.
            (vol.Optional(CONF_DATAPOINT_TS_ENTITY, default=current[CONF_DATAPOINT_TS_ENTITY])
             if current.get(CONF_DATAPOINT_TS_ENTITY) else vol.Optional(CONF_DATAPOINT_TS_ENTITY)): _entity_sel(),
            vol.Required(CONF_QUEUE_MAX_LEN, default=current.get(CONF_QUEUE_MAX_LEN, DEFAULT_QUEUE_MAX_LEN)): vol.All(int, vol.Range(min=0)),
            vol.Required(CONF_QUEUE_MAX_SEND_PER_TICK, default=current.get(CONF_QUEUE_MAX_SEND_PER_TICK, DEFAULT_QUEUE_MAX_SEND_PER_TICK)): vol.All(int, vol.Range(min=0)),
        }

        for conf_key, _api_key_name in ADV_FIELDS:
            if current.get(conf_key):
                adv_schema_dict[vol.Optional(conf_key, default=current.get(conf_key))] = _entity_sel(domains=["sensor", "number", "input_number"])
            else:
                adv_schema_dict[vol.Optional(conf_key)] = _entity_sel(domains=["sensor", "number", "input_number"])

        return self.async_show_form(step_id="advanced", data_schema=vol.Schema(adv_schema_dict))
