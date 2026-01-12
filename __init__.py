from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, CALLBACK_TYPE
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from .api import EmfApi
from .const import (
    DOMAIN,
    CONF_BASE_URL,
    CONF_API_KEY,
    CONF_SITE_FID,
    CONF_DATAPOINT_TS_MODE,
    CONF_DATAPOINT_TS_ENTITY,
    CONF_EM_POWER_GRID_ENTITY,
    ADV_FIELDS,
    FIELD_SPECS,
    SEND_EVERY_MINUTES,
)

_LOGGER = logging.getLogger(__name__)


def _state_obj(hass: HomeAssistant, entity_id: str | None):
    if not entity_id:
        return None
    return hass.states.get(entity_id)


def _parse_float(s: str) -> float | None:
    try:
        return float(s.replace(",", ".").strip())
    except Exception:
        return None


def _unit(s) -> str | None:
    if not s:
        return None
    u = s.attributes.get("unit_of_measurement")
    return str(u) if u else None


def _scale_value(value: float, from_unit: str | None, to_unit: str | None) -> float | None:
    """Best effort unit conversion for the handful of units we need."""
    if to_unit is None:
        return value

    fu = (from_unit or "").strip()
    tu = to_unit.strip()

    if fu == "" or fu == tu:
        return value

    # --- Power to W
    if tu == "W":
        if fu == "kW":
            return value * 1000.0
        if fu == "MW":
            return value * 1_000_000.0

    # --- Energy to kWh
    if tu == "kWh":
        if fu == "Wh":
            return value / 1000.0
        if fu == "MWh":
            return value * 1000.0

    # --- Voltage to V
    if tu == "V":
        if fu == "mV":
            return value / 1000.0
        if fu == "kV":
            return value * 1000.0

    # --- Current to A
    if tu == "A":
        if fu == "mA":
            return value / 1000.0
        if fu == "kA":
            return value * 1000.0

    # --- Temperature (common HA uses °C already)
    if tu in ("°C", "C"):
        if fu in ("°C", "C"):
            return value

    # --- Percent
    if tu == "%":
        if fu == "%":
            return value
        # Some entities might be 0..1 "ratio"
        if fu in ("", "ratio", "1"):
            # Heuristic: if value <= 1.0 -> treat as fraction
            return value * 100.0 if value <= 1.0 else value

    # Unknown conversion -> keep numeric as-is
    return value


def _convert_for_field(hass: HomeAssistant, entity_id: str, api_field: str) -> int | float | None:
    st = _state_obj(hass, entity_id)
    if not st:
        return None

    s = (st.state or "").strip()
    if s in ("unknown", "unavailable", ""):
        return None

    v = _parse_float(s)
    if v is None:
        return None

    spec = FIELD_SPECS.get(api_field)
    target_unit = spec["unit"] if spec else None
    target_type = spec["type"] if spec else "float"

    v2 = _scale_value(v, _unit(st), target_unit)
    if v2 is None:
        return None

    if target_type == "int":
        # Power-Felder sind int(11) laut Tabelle/Doku. :contentReference[oaicite:2]{index=2}
        return int(round(v2))
    return float(v2)


def _format_ts_local(dt: datetime) -> str:
    # API erwartet "YYYY-MM-DD HH:MM:SS" :contentReference[oaicite:3]{index=3}
    local = dt_util.as_local(dt)
    return local.strftime("%Y-%m-%d %H:%M:%S")


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    api = EmfApi(session=session, base_url=entry.data[CONF_BASE_URL])

    async def _send(now: datetime) -> None:
        api_key = (entry.data.get(CONF_API_KEY) or "").strip()
        site_fid = (entry.data.get(CONF_SITE_FID) or "").strip()

        if not api_key or not site_fid:
            _LOGGER.debug("Skipping send: missing api_key/site_fid")
            return

        grid_ent = entry.data.get(CONF_EM_POWER_GRID_ENTITY)
        if not grid_ent:
            _LOGGER.debug("Skipping send: missing em_power_grid entity mapping")
            return

        grid_val = _convert_for_field(hass, grid_ent, "em_power_grid")
        if grid_val is None:
            _LOGGER.debug("Skipping send: em_power_grid is not available/parsable")
            return

        payload: dict[str, object] = {
            "api_key": api_key,
            "site_fid": site_fid,
            "em_power_grid": grid_val,
        }

        ts_mode = entry.data.get(CONF_DATAPOINT_TS_MODE, "now")
        if ts_mode == "entity":
            ts_entity = entry.data.get(CONF_DATAPOINT_TS_ENTITY)
            ts_state = None
            if ts_entity:
                st = _state_obj(hass, ts_entity)
                if st and (st.state or "").strip() not in ("unknown", "unavailable", ""):
                    ts_state = (st.state or "").strip()
            payload["datapoint_ts"] = ts_state or _format_ts_local(now)
        else:
            payload["datapoint_ts"] = _format_ts_local(now)

        # Advanced optional fields; missing ones werden weggelassen. :contentReference[oaicite:4]{index=4}
        for conf_key, api_field in ADV_FIELDS:
            ent = entry.data.get(conf_key)
            if not ent:
                continue
            val = _convert_for_field(hass, ent, api_field)
            if val is None:
                continue
            payload[api_field] = val

        try:
            await api.submit_energy_data(payload)
            _LOGGER.debug("Submitted EMF payload: %s", payload)
        except Exception as err:
            _LOGGER.warning("EMF submit failed: %s", err)

    async def _time_change(now: datetime) -> None:
        await _send(now)

    unsub: CALLBACK_TYPE = async_track_time_change(
        hass,
        _time_change,
        minute=list(range(0, 60, SEND_EVERY_MINUTES)),
        second=0,
    )

    hass.data[DOMAIN][entry.entry_id] = {"unsub": unsub}
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if data and (unsub := data.get("unsub")):
        unsub()
    return True
