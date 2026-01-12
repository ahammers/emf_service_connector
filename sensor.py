from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_STATUS_UPDATED


@dataclass(frozen=True)
class _Field:
    key: str
    name: str


FIELDS = [
    _Field("last_attempt_utc", "Last attempt (UTC)"),
    _Field("last_success_utc", "Last success (UTC)"),
    _Field("last_error_utc", "Last error (UTC)"),
    _Field("last_error_message", "Last error message"),
    _Field("last_http_status", "Last HTTP status"),
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([EmfDebugSensor(hass, entry, f) for f in FIELDS], update_before_add=False)


class EmfDebugSensor(SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, field: _Field) -> None:
        self.hass = hass
        self.entry = entry
        self.field = field

        self._attr_unique_id = f"{entry.entry_id}_{field.key}"
        self._attr_name = field.name

    @property
    def native_value(self) -> Any:
        data = self.hass.data.get(DOMAIN, {}).get(self.entry.entry_id, {})
        status = data.get("status", {})
        return status.get(self.field.key)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_STATUS_UPDATED}_{self.entry.entry_id}",
                self._handle_update,
            )
        )

    def _handle_update(self) -> None:
        self.async_write_ha_state()
