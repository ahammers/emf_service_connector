<p align="center">
  <img src="icon.png" alt="EMF Service Connector Icon" width="128" height="128">
</p>

# EMF Service Connector (Home Assistant)

The **EMF Service Connector** is a Home Assistant integration that **periodically
transmits energy data** (e.g. grid consumption / feed-in) to the **EMF API
“Energiewende mit Freunden”**.

The integration is designed for **reliable long-term operation** and includes:

- Persistent queue
- Automatic retries
- Status and debug events
- Repair hints (Issues) in case of transmission errors

---

## Features

- Periodic transmission of energy data (default: every 5 minutes)
- Support for multiple EMF sites (multiple instances)
- Flexible mapping of Home Assistant entities to EMF API fields
- Timestamp handling:
  - current Home Assistant time
  - or timestamp taken from an entity
- Robust error handling using queue & retry logic
- Manual triggering via service
- Extensive debug events

---

## Installation (HACS)

### Requirements

- Home Assistant ≥ current Core version
- HACS installed

### Steps

1. **HACS → Integrations**
2. **⋮ → Custom repositories**
3. Add repository:  
   `https://github.com/ahammers/emf_service_connector`  
   Type: **Integration**
4. Install **EMF Service Connector**
5. **Restart** Home Assistant
6. **Settings → Devices & Services → Add Integration**
7. Select **EMF Service Connector**
8. **Create an instance** (see Configuration)

---

## Configuration

Configuration is done entirely via the UI dialog.

### Standard Configuration (required)

| Field | Description |
|------|-------------|
| **API Key** | Your personal EMF API key |
| **Site ID** | Site identifier at EMF (e.g. `TESTSITE000`) |
| **Grid Power Entity** | Entity representing grid import / export (W, kW, …) |

After creation, the instance will be named for example:  
**EMF Service Connection to TESTSITE000**

---

### Advanced Configuration (optional)

| Field | Description |
|------|-------------|
| **Base URL** | EMF API base URL (pre-filled by default) |
| **Timestamp Mode** | `now` or `entity` |
| **Timestamp Entity** | Entity used as timestamp source |
| **Queue Length** | Maximum number of buffered records |
| **Max Sends per Tick** | Limit per transmission cycle |
| **Additional Fields** | Optional EMF fields mapped from entities |

All values can be changed later via **Options**.

---

## Runtime Behavior

- Data is written to a **persistent queue**
- The **newest record is sent first**
- On errors:
  - The queue is preserved
  - A repair hint appears under *Settings → Repairs*
- After a successful transmission, the repair hint is removed automatically

---

## Services (Actions)

### `emf_service_connector.send_now`

Immediately sends data (independent of the schedule).

**Parameters:**

- `entry_id` *(optional)* – target a specific instance only

**Example:**
```yaml
service: emf_service_connector.send_now
data:
  entry_id: abcdef123456
```

---

### `emf_service_connector.get_status`

Emits the current status as an event.

**Parameters:**

- `entry_id` *(optional)* – target a specific instance only

---

## Events (Debug & Monitoring)

The integration emits several events for diagnostics.

### `emf_payload`

Triggered before sending data.

Contains:
- masked payload
- reason (`schedule`, `service_send_now`, …)

---

### `emf_result`

Result of a send attempt.

| Field | Meaning |
|------|--------|
| `success` | `true` / `false` |
| `http_status` | HTTP status (if available) |
| `response_text` | Server response |
| `error` | Error message (on failure) |

---

### `emf_status`

Current status of an instance.

Includes:
- last send attempt
- last successful transmission
- last error message
- queue length
- outage start time

---

### `emf_all`

Combined event containing all of the above  
(recommended for simple debug subscriptions in the UI).

---

## Repairs / Issues

If transmission errors persist, **exactly one repair entry per instance** is created.

- No spam (stable Issue ID)
- Automatically updated
- Removed after a successful transmission

---

## Multiple Sites

You can configure multiple instances, for example:

- EMF Service Connection to SITE_A
- EMF Service Connection to SITE_B

Each instance has its own:
- queue
- schedule
- repair notifications

---

## Security

- API keys are never logged in plain text
- Events only contain masked keys
- Persistent data is stored encrypted in Home Assistant storage

---

## Development & Support

- Repository: https://github.com/ahammers/emf_service_connector
- Issues & feature requests via GitHub

---

*(Information updated with version 0.1.32)*
