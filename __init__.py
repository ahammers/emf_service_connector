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
from homeassistant.helpers.issue_registry import IssueSeverity
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.helpers import issue_registry as ir


from .api import EmfApi
from .const import (
    DOMAIN,
    PLATFORMS,
    CONF_BASE_URL,
    CONF_API_KEY,
    CONF_SITE_FID,
    CONF_EM_POWER_GRID_ENTITY,
    CONF_QUEUE_MAX_LEN,
    CONF_QUEUE_MAX_SEND_PER_TICK,
    DEFAULT_BASE_URL,
    DEFAULT_QUEUE_MAX_LEN,
    DEFAULT_QUEUE_MAX_SEND_PER_TICK,
    ADV_FIELDS,
    FIELD_SPECS,
    SEND_EVERY_MINUTES,
    SIGNAL_STATUS_UPDATED,
    EVENT_PAYLOAD,
    EVENT_RESULT,
    EVENT_STATUS,
    EVENT_ALL,
    SERVICE_SEND_NOW,
    SERVICE_GET_STATUS,
    SERVICE_CLEAR_QUEUE,
)

_LOGGER = logging.getLogger(__name__)

_STORE_VERSION = 1


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

def _format_ts_utc(dt: datetime) -> str:
    utc_dt = dt_util.as_utc(dt)
    return utc_dt.strftime("%Y-%m-%d %H:%M:%S")

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


def _notify_status_updated(hass: HomeAssistant, entry_id: str) -> None:
    hass.loop.call_soon_threadsafe(
        async_dispatcher_send,
        hass,
        f"{SIGNAL_STATUS_UPDATED}_{entry_id}",
    )


def _issue_id(entry_id: str) -> str:
    return f"send_failed_{entry_id}"


def _create_or_update_issue(hass: HomeAssistant, entry: ConfigEntry, message: str) -> None:
    # One stable issue per config entry (same issue_id every time) -> gets updated, not duplicated.
    ir.async_create_issue(
        hass,
        DOMAIN,
        _issue_id(entry.entry_id),
        is_fixable=False,
        severity=IssueSeverity.WARNING,
        translation_key="send_failed",
        translation_placeholders={
            "title": entry.title or "EMF Service Connector",
            "message": message,
        },
    )


def _delete_issue(hass: HomeAssistant, entry: ConfigEntry) -> None:
    ir.async_delete_issue(hass, DOMAIN, _issue_id(entry.entry_id))


def _store_for_entry(hass: HomeAssistant, entry_id: str) -> Store:
    return Store(hass, _STORE_VERSION, f"{DOMAIN}.{entry_id}")


def _ensure_entry_data(hass: HomeAssistant, entry_id: str) -> dict[str, Any]:
    hass.data.setdefault(DOMAIN, {})
    entry_data = hass.data[DOMAIN].setdefault(entry_id, {})
    entry_data.setdefault(
        "status",
        {
            "last_attempt_utc": None,
            "last_success_utc": None,
            "last_error_utc": None,
            "last_error_message": None,
            "outage_since_utc": None,
            "last_http_status": None,
            "last_response_text": None,
            "queue_len": 0,
            "dropped_422_count": 0,
            "dropped_queue_full_count": 0,
            "last_drop_reason": None,
        },
    )
    entry_data.setdefault("queue", [])  # list[dict] oldest..newest
    entry_data.setdefault("store", _store_for_entry(hass, entry_id))
    return entry_data


async def _load_queue(hass: HomeAssistant, entry: ConfigEntry) -> None:
    entry_data = _ensure_entry_data(hass, entry.entry_id)
    store: Store = entry_data["store"]
    data = await store.async_load()
    if isinstance(data, dict) and isinstance(data.get("queue"), list):
        entry_data["queue"] = data["queue"]
    entry_data["status"]["queue_len"] = len(entry_data["queue"])


async def _save_queue(hass: HomeAssistant, entry: ConfigEntry) -> None:
    entry_data = _ensure_entry_data(hass, entry.entry_id)
    store: Store = entry_data["store"]
    await store.async_save({"queue": entry_data["queue"]})


async def _entry_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _safe_err_message(err: Exception) -> str:
    msg = str(err).strip()
    if msg:
        return msg
    msg = repr(err).strip()
    if msg:
        return msg
    return type(err).__name__


def _since_local_str(outage_since_utc: str) -> str:
    # outage_since_utc is ISO string, parse to local display
    dt = dt_util.parse_datetime(outage_since_utc)
    if dt is None:
        return outage_since_utc
    local = dt_util.as_local(dt)
    return local.strftime("%H:%M am %d.%m.%Y")

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    entry_data = _ensure_entry_data(hass, entry.entry_id)

    # options win over data
    cfg = {**entry.data, **entry.options}

    session = async_get_clientsession(hass)
    base_url = (cfg.get(CONF_BASE_URL) or DEFAULT_BASE_URL)
    api = EmfApi(session=session, base_url=base_url)

    await _load_queue(hass, entry)

    async def _build_queue_item(now: datetime) -> dict[str, Any] | None:
        """Build a queue item WITHOUT api_key/site_fid. Contains datapoint_ts + fields."""
        grid_ent = cfg.get(CONF_EM_POWER_GRID_ENTITY)
        if not grid_ent:
            return None

        grid_val = _convert_for_field(hass, grid_ent, "em_power_grid")
        if grid_val is None:
            return None

        item: dict[str, Any] = {"em_power_grid": grid_val}
        item["datapoint_ts"] = _format_ts_utc(now)
        item["submit_cli"] = f"emf_0.1"

        for conf_key, api_field in ADV_FIELDS:
            ent = cfg.get(conf_key)
            if not ent:
                continue
            val = _convert_for_field(hass, ent, api_field)
            if val is None:
                continue
            item[api_field] = val

        return item

    def _queue_limits() -> tuple[int, int]:
        max_len = int(cfg.get(CONF_QUEUE_MAX_LEN, DEFAULT_QUEUE_MAX_LEN) or 0)
        max_send = int(cfg.get(CONF_QUEUE_MAX_SEND_PER_TICK, DEFAULT_QUEUE_MAX_SEND_PER_TICK) or 0)
        return max_len, max_send

    def _trim_queue() -> None:
        max_len, _ = _queue_limits()
        q = entry_data["queue"]

        if max_len <= 0:
            q.clear()
            return

        while len(q) > max_len:
            q.pop(0)  # drop oldest
            entry_data["status"]["dropped_queue_full_count"] = int(entry_data["status"].get("dropped_queue_full_count", 0)) + 1
            entry_data["status"]["last_drop_reason"] = "queue_full (dropped oldest)"

    def _status_update_queue_len() -> None:
        entry_data["status"]["queue_len"] = len(entry_data["queue"])

    def _fire_all(event_type: str, payload: dict[str, Any]) -> None:
        hass.bus.async_fire(event_type, payload)
        # Optional: one combined event to subscribe once in UI
        hass.bus.async_fire(EVENT_ALL, {"type": event_type, **payload})

    async def _try_send_queue(reason: str) -> None:
        """Try sending newest-first. Stop on first failure. Up to max_send_per_tick."""
        status = entry_data["status"]
        status["last_attempt_utc"] = _now_utc_iso()
        status["last_http_status"] = None
        status["last_response_text"] = None

        api_key = (cfg.get(CONF_API_KEY) or "").strip()
        site_fid = (cfg.get(CONF_SITE_FID) or "").strip()

        if not api_key or not site_fid:
            now_iso = _now_utc_iso()
            status["last_error_utc"] = now_iso
            status["last_error_message"] = "Missing api_key/site_fid"
            if not status.get("outage_since_utc"):
                status["outage_since_utc"] = now_iso
            msg = f"Übertragung zum Service seit {_since_local_str(status['outage_since_utc'])} unterbrochen: {status['last_error_message']}"
            _create_or_update_issue(hass, entry, msg)
            _status_update_queue_len()
            _notify_status_updated(hass, entry.entry_id)
            return

        q = entry_data["queue"]
        _trim_queue()
        _status_update_queue_len()

        _, max_send = _queue_limits()
        if max_send <= 0:
            _notify_status_updated(hass, entry.entry_id)
            return

        processed_count = 0

        while q and processed_count < max_send:
            item = q[-1]  # newest-first
            full_payload = {"api_key": api_key, "site_fid": site_fid, **item}

            masked = dict(full_payload)
            masked["api_key"] = _mask_secret(api_key)

            _fire_all(
                EVENT_PAYLOAD,
                {
                    "entry_id": entry.entry_id,
                    "reason": reason,
                    "payload": masked,
                },
            )

            try:
                http_status, resp_text = await api.submit_energy_data(full_payload)

                # 2xx -> success
                if 200 <= http_status < 300:
                    status["last_success_utc"] = _now_utc_iso()
                    status["last_http_status"] = http_status
                    status["last_response_text"] = resp_text

                    # success -> clear outage markers
                    status["last_error_utc"] = None
                    status["last_error_message"] = None
                    status["outage_since_utc"] = None

                    _fire_all(
                        EVENT_RESULT,
                        {
                            "entry_id": entry.entry_id,
                            "reason": reason,
                            "success": True,
                            "http_status": http_status,
                            "response_text": resp_text,
                        },
                    )

                    # remove newest, continue
                    q.pop()
                    processed_count += 1
                    _status_update_queue_len()
                    await _save_queue(hass, entry)
                    continue

                # 422 -> permanent validation error -> drop record and continue with next
                if http_status == 422:
                    status["dropped_422_count"] = int(status.get("dropped_422_count", 0)) + 1
                    status["last_drop_reason"] = f"HTTP 422: {resp_text}"
                    status["last_http_status"] = http_status
                    status["last_response_text"] = resp_text

                    _fire_all(
                        EVENT_RESULT,
                        {
                            "entry_id": entry.entry_id,
                            "reason": reason,
                            "success": False,
                            "http_status": http_status,
                            "response_text": resp_text,
                            "dropped": True,
                            "dropped_reason": status["last_drop_reason"],
                        },
                    )

                    # drop newest and continue
                    q.pop()
                    processed_count += 1
                    _status_update_queue_len()
                    await _save_queue(hass, entry)
                    continue

                # other non-2xx -> treat as failure, keep queue, stop (newest-first rule)
                status["last_http_status"] = http_status
                status["last_response_text"] = resp_text
                raise RuntimeError(f"EMF submit failed: HTTP {http_status}: {resp_text}")
            except Exception as err:
                now_iso = _now_utc_iso()
                status["last_error_utc"] = now_iso
                status["last_error_message"] = _safe_err_message(err)

                if not status.get("outage_since_utc"):
                    status["outage_since_utc"] = now_iso

                since_str = _since_local_str(status["outage_since_utc"])
                issue_msg = f"Übertragung zum Service seit {since_str} unterbrochen: {status['last_error_message']}"
                _create_or_update_issue(hass, entry, issue_msg)

                _fire_all(
                    EVENT_RESULT,
                    {
                        "entry_id": entry.entry_id,
                        "reason": reason,
                        "success": False,
                        "error": status["last_error_message"],
                    },
                )

                _LOGGER.warning("EMF submit failed (%s): %s", entry.entry_id, status["last_error_message"])

                # newest-first rule: stop on first failure
                break

        # If queue is empty and no current outage -> clear issue
        if not q and status.get("outage_since_utc") is None:
            _delete_issue(hass, entry)

        _notify_status_updated(hass, entry.entry_id)

    async def _tick(now: datetime, reason: str) -> None:
        # Build one item and enqueue
        item = await _build_queue_item(now)

        max_len, _ = _queue_limits()
        if max_len > 0 and item is not None:
            entry_data["queue"].append(item)
            _trim_queue()
            _status_update_queue_len()
            await _save_queue(hass, entry)
        else:
            # queue disabled OR no item -> keep queue as-is but ensure trim
            _trim_queue()
            _status_update_queue_len()

        await _try_send_queue(reason=reason)

    # Expose for services
    entry_data["send_func"] = _tick

    async def _time_change(now: datetime) -> None:
        await _tick(now, reason="schedule")

    unsub: CALLBACK_TYPE = async_track_time_change(
        hass,
        _time_change,
        minute=list(range(0, 60, SEND_EVERY_MINUTES)),
        second=0,
    )
    entry_data["unsub"] = unsub

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_entry_updated))

    # Register services once globally
    if not hass.data[DOMAIN].get("_services_registered"):
        hass.data[DOMAIN]["_services_registered"] = True

        async def _iter_target_entries(call: ServiceCall):
            entry_id = call.data.get("entry_id")
            if entry_id:
                ce = hass.config_entries.async_get_entry(entry_id)
                return [ce] if ce else []
            return [e for e in hass.config_entries.async_entries(DOMAIN)]

        async def handle_send_now(call: ServiceCall) -> None:
            targets = await _iter_target_entries(call)
            now = dt_util.utcnow().replace(tzinfo=dt_util.UTC)
            for ce in targets:
                ed = _ensure_entry_data(hass, ce.entry_id)
                func = ed.get("send_func")
                if func:
                    await func(now, reason="service_send_now")

        async def handle_get_status(call: ServiceCall) -> None:
            targets = await _iter_target_entries(call)
            for ce in targets:
                ed = _ensure_entry_data(hass, ce.entry_id)
                st = ed.get("status", {})
                hass.bus.async_fire(
                    EVENT_STATUS,
                    {
                        "entry_id": ce.entry_id,
                        "title": ce.title,
                        **st,
                    },
                )

        async def handle_clear_queue(call: ServiceCall) -> None:
            targets = await _iter_target_entries(call)
            for ce in targets:
                ed = _ensure_entry_data(hass, ce.entry_id)
                ed["queue"].clear()
                ed["status"]["queue_len"] = 0
                # persist immediately
                store: Store = ed["store"]
                await store.async_save({"queue": ed["queue"]})
                _notify_status_updated(hass, ce.entry_id)

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
        hass.services.async_register(
            DOMAIN,
            SERVICE_CLEAR_QUEUE,
            handle_clear_queue,
            schema=vol.Schema({vol.Optional("entry_id"): cv.string}),
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    entry_data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)

    if entry_data and (unsub := entry_data.get("unsub")):
        unsub()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    return unload_ok
