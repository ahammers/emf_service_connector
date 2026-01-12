from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, CALLBACK_TYPE, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers import entity_platform
from homeassistant.helpers import service
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .api import EmfApi
from .const import (
    DOMAIN,
    PLATFORMS,
    CONF_BASE_URL,
    CONF_API_KEY,
    CONF_SITE_FID,
    CONF_DATAPOINT_TS_MODE,
    CONF_DATAPOINT_TS_ENTITY,
    CONF_EM_POWER_GRID_ENTITY,
    ADV_FIELDS,
    FIELD_SPECS,
    SEND_EVERY_MINUTES,
    SIGNAL_STATUS_UPDATED,
    EVENT_PAYLOAD,
    EVENT_RESULT,
    EVENT_STATUS,
    SERVICE_SEND_NOW,
    SERVICE_GET_STATUS,
)

_LOGGER = logging.getLogger(__name__)


def _mask_secret(s: str | None) -> str | None:
    if not s:
        return None
    s = s.strip()
    if len(s) <= 4:
        return "*" * len(s)
    return "*" * (len(s) - 4) + s[-4:]


def _now_utc_iso() -> str:
    return dt_util.utcnow().isoformat()


def _format_ts_local(dt: datetime) -> str:
    local = dt_util.as_local(dt)
    return local.strftime("%Y-%m-%d %H:%M:%S")


def _state_obj(hass: HomeAssistant, entity_id: str | None):
    if not entity_id:
        return None
    return hass.states.get(entity_id)


def _parse_float(s: str) -> float | None:
    try:
        return float(s.replace(",", ".").strip())
    except Exception:
        return None


def _unit(state) -> str | None:
    if not state:
        return None
    u = state.attributes.get("unit_of_measurement")
    return str(u) if u else None


def _scale_value(value: float, from_unit: str | None, to_unit: str | None) -> float:
    if to_unit is None:
        return value

    fu = (from_unit or "").strip()
    tu = to_unit.strip()

    if fu == "" or fu == tu:
        return value

    # Power -> W
    if tu == "W":
        if fu == "kW":
            return value * 1000.0
        if fu == "MW":
            return value * 1_000_000.0

    # Energy -> kWh
    if tu == "kWh":
        if fu == "Wh":
            return value / 1000.0
        if fu == "MWh":
            return value * 1000.0

    # Voltage -> V
    if tu == "V":
        if fu == "mV":
            return value / 1000.0
        if fu == "kV":
            return value * 1000.0

    # Current -> A
    if tu == "A":
        if fu == "mA":
            return value / 1000.0
        if fu == "kA":
            return value * 1000.0

    # Temperature
    if tu in ("°C", "C"):
        return value

    # Percent
    if tu == "%":
        if fu == "%":
            return value
        if fu in ("", "ratio", "1"):
            return value * 100.0 if value <= 1.0 else value

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

    if target_type == "int":
        return int(round(v2))
    return float(v2)


def _ensure_entry_data(hass: HomeAssistant, entry_id: str) -> dict[str, Any]:
    hass.data.setdefault(DOMAIN, {})
    entry_data = hass.data[DOMAIN].setdefault(entry_id, {})
    entry_data.setdefault("status", {
        "last_attempt_utc": None,
        "last_success_utc": None,
        "last_error_utc": None,
        "last_error_message": None,
        "last_http_status": None,
        "last_response_text": None,
        "last_payload": None,         # unmasked (internal)
        "last_payload_masked": None,  # safe for events/diagnostics
    })
    return entry_data


def _status_for_event(entry: ConfigEntry, status: dict[str, Any]) -> dict[str, Any]:
    # safe representation for events/diagnostics
    return {
        "entry_id": entry.entry_id,
        "title": entry.title,
        "last_attempt_utc": status.get("last_attempt_utc"),
        "last_success_utc": status.get("last_success_utc"),
        "last_error_utc": status.get("last_error_utc"),
        "last_error_message": status.get("last_error_message"),
        "last_http_status": status.get("last_http_status"),
        "last_response_text": status.get("last_response_text"),
        "last_payload": status.get("last_payload_masked"),
    }


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    entry_data = _ensure_entry_data(hass, entry.entry_id)

    session = async_get_clientsession(hass)
    api = EmfApi(session=session, base_url=entry.data[CONF_BASE_URL])

    async def _send(now: datetime, reason: str) -> None:
        status = entry_data["status"]
        status["last_attempt_utc"] = _now_utc_iso()
        status["last_error_message"] = None
        status["last_http_status"] = None
        status["last_response_text"] = None

        api_key = (entry.data.get(CONF_API_KEY) or "").strip()
        site_fid = (entry.data.get(CONF_SITE_FID) or "").strip()

        if not api_key or not site_fid:
            status["last_error_utc"] = _now_utc_iso()
            status["last_error_message"] = "Missing api_key/site_fid"
            async_dispatcher_send(hass, f"{SIGNAL_STATUS_UPDATED}_{entry.entry_id}")
            return

        grid_ent = entry.data.get(CONF_EM_POWER_GRID_ENTITY)
        if not grid_ent:
            status["last_error_utc"] = _now_utc_iso()
            status["last_error_message"] = "Missing em_power_grid entity mapping"
            async_dispatcher_send(hass, f"{SIGNAL_STATUS_UPDATED}_{entry.entry_id}")
            return

        grid_val = _convert_for_field(hass, grid_ent, "em_power_grid")
        if grid_val is None:
            status["last_error_utc"] = _now_utc_iso()
            status["last_error_message"] = "em_power_grid unavailable/unparsable"
            async_dispatcher_send(hass, f"{SIGNAL_STATUS_UPDATED}_{entry.entry_id}")
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

        for conf_key, api_field in ADV_FIELDS:
            ent = entry.data.get(conf_key)
            if not ent:
                continue
            val = _convert_for_field(hass, ent, api_field)
            if val is None:
                continue
            payload[api_field] = val

        # masked payload for events/diagnostics
        masked = dict(payload)
        masked["api_key"] = _mask_secret(api_key)

        status["last_payload"] = payload
        status["last_payload_masked"] = masked

        # (2) Event: payload
        hass.bus.async_fire(EVENT_PAYLOAD, {
            "entry_id": entry.entry_id,
            "reason": reason,
            "payload": masked,
        })

        try:
            http_status, resp_text = await api.submit_energy_data(payload)
            status["last_success_utc"] = _now_utc_iso()
            status["last_http_status"] = http_status
            status["last_response_text"] = resp_text

            # (2) Event: result
            hass.bus.async_fire(EVENT_RESULT, {
                "entry_id": entry.entry_id,
                "reason": reason,
                "success": True,
                "http_status": http_status,
                "response_text": resp_text,
            })
        except Exception as err:
            status["last_error_utc"] = _now_utc_iso()
            status["last_error_message"] = str(err)

            hass.bus.async_fire(EVENT_RESULT, {
                "entry_id": entry.entry_id,
                "reason": reason,
                "success": False,
                "error": str(err),
            })

            _LOGGER.warning("EMF submit failed (%s): %s", entry.entry_id, err)

        # (3) Notify sensors
        async_dispatcher_send(hass, f"{SIGNAL_STATUS_UPDATED}_{entry.entry_id}")

    # store callable for services
    entry_data["send_func"] = _send

    async def _time_change(now: datetime) -> None:
        await _send(now, reason="schedule")

    unsub: CALLBACK_TYPE = async_track_time_change(
        hass,
        _time_change,
        minute=list(range(0, 60, SEND_EVERY_MINUTES)),
        second=0,
    )
    entry_data["unsub"] = unsub

    # (4) Debug entities via sensor platform
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services once
    if not hass.data[DOMAIN].get("_services_registered"):
        hass.data[DOMAIN]["_services_registered"] = True

        async def _iter_target_entries(call: ServiceCall):
            entry_id = call.data.get("entry_id")
            if entry_id:
                ce = hass.config_entries.async_get_entry(entry_id)
                if ce:
                    return [ce]
                return []

            # no entry_id provided -> all entries of this domain
            return [e for e in hass.config_entries.async_entries(DOMAIN)]

        async def handle_send_now(call: ServiceCall) -> None:
            targets = await _iter_target_entries(call)
            now = dt_util.utcnow()
            for ce in targets:
                ed = _ensure_entry_data(hass, ce.entry_id)
                send_func = ed.get("send_func")
                if send_func:
                    await send_func(now, reason="service_send_now")

        async def handle_get_status(call: ServiceCall) -> None:
            targets = await _iter_target_entries(call)
            for ce in targets:
                ed = _ensure_entry_data(hass, ce.entry_id)
                status = ed.get("status", {})
                hass.bus.async_fire(EVENT_STATUS, _status_for_event(ce, status))

        hass.services.async_register(
            DOMAIN,
            SERVICE_SEND_NOW,
            handle_send_now,
            schema=vol.Schema({vol.Optional("entry_id"): cv.string}),
        )
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_STATUS,
            handle_get_status,
            schema=vol.Schema({vol.Optional("entry_id"): cv.string}),
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    entry_data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    unload_ok = True

    if entry_data and (unsub := entry_data.get("unsub")):
        unsub()

    # unload platforms (sensors)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    return unload_ok
