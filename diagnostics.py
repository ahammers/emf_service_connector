from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_API_KEY


def _mask_secret(s: str | None) -> str | None:
    if not s:
        return None
    s = s.strip()
    if len(s) <= 4:
        return "*" * len(s)
    return "*" * (len(s) - 4) + s[-4:]


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    status = data.get("status", {})

    # copy config, mask secrets
    cfg = dict(entry.data)
    if CONF_API_KEY in cfg:
        cfg[CONF_API_KEY] = _mask_secret(cfg.get(CONF_API_KEY))

    return {
        "entry": {
            "entry_id": entry.entry_id,
            "title": entry.title,
        },
        "config": cfg,
        "status": {
            # safe payload only
            "last_attempt_utc": status.get("last_attempt_utc"),
            "last_success_utc": status.get("last_success_utc"),
            "last_error_utc": status.get("last_error_utc"),
            "last_error_message": status.get("last_error_message"),
            "last_http_status": status.get("last_http_status"),
            "last_response_text": status.get("last_response_text"),
            "last_payload": status.get("last_payload_masked"),
        },
    }
