from __future__ import annotations

DOMAIN = "emf_service_connector"

CONF_BASE_URL = "base_url"
CONF_API_KEY = "api_key"
CONF_SITE_FID = "site_fid"
CONF_DATAPOINT_TS_MODE = "datapoint_ts_mode"  # "now" | "entity"
CONF_DATAPOINT_TS_ENTITY = "datapoint_ts_entity"
CONF_EM_POWER_GRID_ENTITY = "em_power_grid_entity"

# Queue options
CONF_QUEUE_MAX_LEN = "queue_max_len"
CONF_QUEUE_MAX_SEND_PER_TICK = "queue_max_send_per_tick"

DEFAULT_BASE_URL = "http://ems001.amberquest.at:8444"
SUBMIT_PATH = "/api/submit_energy_data"

SEND_EVERY_MINUTES = 5

DEFAULT_QUEUE_MAX_LEN = 4032            # ~ 2 Wochen bei 5min
DEFAULT_QUEUE_MAX_SEND_PER_TICK = 144   # ~ 0.5 Tage pro Tick nachsenden

PLATFORMS = ["sensor"]

SIGNAL_STATUS_UPDATED = "emf_service_connector_status_updated"

EVENT_PAYLOAD = "emf_service_connector_payload"
EVENT_RESULT = "emf_service_connector_result"
EVENT_STATUS = "emf_service_connector_status"
EVENT_ALL = "emf_service_connector_event"  # optional: Sammel-Event

SERVICE_SEND_NOW = "send_now"
SERVICE_GET_STATUS = "get_status"

# Advanced (optional, entity per field)
ADV_FIELDS = [
    ("em_power_consumption_entity", "em_power_consumption"),
    ("em_power_pv_entity", "em_power_pv"),
    ("em_power_battery_entity", "em_power_battery"),
    ("em_power_evcharger_entity", "em_power_evcharger"),
    ("em_power_heatpump_entity", "em_power_heatpump"),
    ("em_power_bhkw_entity", "em_power_bhkw"),
    ("bat_soc_entity", "bat_soc"),
    ("bat_kwh_remaining_entity", "bat_kwh_remaining"),
    ("bat_dc_power_entity", "bat_dc_power"),
    ("bat_dc_voltage_entity", "bat_dc_voltage"),
    ("bat_dc_current_entity", "bat_dc_current"),
    ("bat_dc_temperature_entity", "bat_dc_temperature"),
]

# API field specs for conversion
FIELD_SPECS: dict[str, dict[str, str]] = {
    "em_power_grid": {"unit": "W", "type": "int"},
    "em_power_consumption": {"unit": "W", "type": "int"},
    "em_power_pv": {"unit": "W", "type": "int"},
    "em_power_battery": {"unit": "W", "type": "int"},
    "em_power_evcharger": {"unit": "W", "type": "int"},
    "em_power_heatpump": {"unit": "W", "type": "int"},
    "em_power_bhkw": {"unit": "W", "type": "int"},
    "bat_dc_power": {"unit": "W", "type": "int"},
    "bat_soc": {"unit": "%", "type": "float"},
    "bat_kwh_remaining": {"unit": "kWh", "type": "float"},
    "bat_dc_voltage": {"unit": "V", "type": "float"},
    "bat_dc_current": {"unit": "A", "type": "float"},
    "bat_dc_temperature": {"unit": "°C", "type": "float"},
}
