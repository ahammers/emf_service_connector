from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_STATUS_UPDATED, CONF_SITE_FID


@dataclass(frozen=True)
class _Field:
    key: str
    name: str


# These are "status/diagnostic" fields: useful in UI, but should NOT be recorded long-term.
STATUS_FIELDS = [
    _Field("last_success_utc", "Last successful transmission (UTC)"),
    _Field("last_attempt_utc", "Last transmission attempt (UTC)"),
    _Field("last_error_utc", "Last transmission failure (UTC)"),
    _Field("last_error_message", "Last transmission failure reason"),
]

# This field SHOULD be recorded to visualize outages/backlog.
QUEUE_FIELD = _Field("queue_len", "Payload queue length")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    entities: list[SensorEntity] = [EmfStatusSensor(hass, entry, f) for f in STATUS_FIELDS]
    entities.append(EmfQueueLengthSensor(hass, entry, QUEUE_FIELD))
    async_add_entities(entities, update_before_add=False)


class _BaseEmfSensor(SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, field: _Field) -> None:
        self.hass = hass
        self.entry = entry
        self.field = field

        self._attr_unique_id = f"{entry.entry_id}_{field.key}"

        cfg = {**entry.data, **entry.options}  # options win
        site = (cfg.get(CONF_SITE_FID) or "UNKNOWN").strip()
        self._attr_name = f"{site}_{field.name}"

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

    def _handle_update(self, *args: Any) -> None:
        # Dispatcher callbacks can be invoked from worker threads depending on caller.
        # async_write_ha_state MUST run on the event loop -> schedule thread-safely.
        self.hass.loop.call_soon_threadsafe(self.async_write_ha_state)


class EmfStatusSensor(_BaseEmfSensor):
    """Diagnostic/status sensors that should not be recorded by the Recorder."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def should_record(self) -> bool:
        return False


class EmfQueueLengthSensor(_BaseEmfSensor):
    """Queue length should be recorded/statistics-enabled to visualize outages/backlog."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "items"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
