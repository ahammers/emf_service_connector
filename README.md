# EMF Service Connector (Home Assistant)

Der **EMF Service Connector** ist eine Home-Assistant-Integration, die Energiewerte
(z. B. Netzbezug/-einspeisung) **periodisch an die EMF API
„Energiewende mit Freunden“** überträgt.

Die Integration ist für **zuverlässigen Dauerbetrieb** ausgelegt und enthält
u. a.:
- Queue mit Persistenz
- automatische Wiederholversuche
- Status- und Debug-Events
- Reparatur-Hinweise (Issues) bei Übertragungsfehlern

---

## Funktionen

- Periodisches Senden von Energiedaten (Standard: alle 5 Minuten)
- Unterstützung mehrerer EMF-Anlagen (mehrere Instanzen)
- Flexible Zuordnung von Home-Assistant-Entitäten zu EMF-API-Feldern
- Zeitstempel:
  - aktuelle Home-Assistant-Zeit
  - oder aus einer Entität
- Robuste Fehlerbehandlung mit Queue & Retry
- Manuelles Auslösen per Service
- Umfangreiche Debug-Events

---

## Installation (HACS)

### Voraussetzungen
- Home Assistant ≥ aktuelle Core-Version
- HACS installiert

### Schritte

1. **HACS → Integrationen**
2. **⋮ → Benutzerdefinierte Repositories**
3. Repository hinzufügen: https://github.com/ahammers/emf_service_connector Typ: **Integration**
4. Integration **EMF Service Connector** installieren
5. Home Assistant **neu starten**
6. **Einstellungen → Geräte & Dienste → Integration hinzufügen**
7. **EMF Service Connector** auswählen
8. **Instanz anlegen** (siehe Konfiguration)

---

## Konfiguration

Die Einrichtung erfolgt vollständig über den UI-Dialog.

### Standard-Konfiguration (Pflicht)

| Feld | Beschreibung |
|----|-------------|
| **API-Key** | Dein persönlicher EMF-API-Schlüssel |
| **Site ID** | Anlagen-Kennung bei EMF (z. B. `TESTSITE000`) |
| **Netzleistung-Entität** | Entität für Netzbezug/-einspeisung (W, kW, …) |

Nach dem Anlegen heißt die Instanz z. B.: EMF Service Connection to TESTSITE000

---

### Erweiterte Konfiguration (optional)

| Feld | Beschreibung |
|----|-------------|
| **Base URL** | EMF-API-URL (Standard vorbelegt) |
| **Zeitstempel-Modus** | `now` oder `entity` |
| **Zeitstempel-Entität** | Quelle für Zeitstempel |
| **Queue-Länge** | Maximale Anzahl gepufferter Datensätze |
| **Max. Sendungen pro Tick** | Begrenzung pro Sendezyklus |
| **Weitere Felder** | Optionale EMF-Felder aus Entitäten |

Alle Werte können später über **Optionen** geändert werden.

---

## Laufzeitverhalten

- Daten werden in eine **persistente Queue** geschrieben
- Gesendet wird **neuester Datensatz zuerst**
- Bei Fehlern:
  - Queue bleibt erhalten
  - Reparatur-Hinweis erscheint unter *Einstellungen → Reparaturen*
- Nach erfolgreicher Übertragung wird der Hinweis automatisch entfernt

---

## Services (Actions)

### `emf_service_connector.send_now`

Sendet sofort Daten (unabhängig vom Zeitplan).

**Parameter:**
- `entry_id` *(optional)* – nur für eine bestimmte Instanz

**Beispiel:**
```yaml
service: emf_service_connector.send_now
data:
  entry_id: abcdef123456

### `emf_service_connector.get_status`

Gibt den aktuellen Status per Event aus.

**Parameter:**

- `entry_id` *(optional)* – nur für eine bestimmte Instanz

## Events (Debug & Monitoring)

Die Integration feuert mehrere Events zur Diagnose.

### `emf_payload`

Wird vor dem Senden ausgelöst.

Enthält:

- maskiertes Payload

- Grund (schedule, service_send_now, …)

### `emf_result`

Ergebnis eines Sendeversuchs.

Feld	Bedeutung
- success	... true / false
- http_status	... HTTP-Status (falls vorhanden)
- response_text	... Antwort des Servers
- error	... Fehlermeldung (bei Fehlern)

### `emf_status`

Aktueller Status einer Instanz.

Enthält u. a.:
- letzter Sendeversuch
- letzter Erfolg
- letzte Fehlermeldung
- Queue-Länge
- Outage-Startzeit

### `emf_all`

Kombiniertes Event für alle oben genannten Typen
(empfohlen für einfache Debug-Abos im UI).

## Reparaturen / Issues

Bei anhaltenden Übertragungsfehlern wird pro Instanz genau ein
Reparatur-Eintrag erstellt.

- Kein Spam (stabile Issue-ID)
- Aktualisiert sich automatisch
- Verschwindet bei erfolgreicher Übertragung

## Mehrere Anlagen

Du kannst mehrere Instanzen anlegen, z. B.:

EMF Service Connection to SITE_A
EMF Service Connection to SITE_B

Jede Instanz:
- hat eigene Queue
- eigenen Zeitplan
- eigene Reparatur-Meldungen

## Sicherheit

- API-Keys werden nicht im Klartext geloggt
- Events enthalten nur maskierte Schlüssel
- Persistente Daten liegen verschlüsselt im HA-Storage

## Entwicklung & Support

- Repository: https://github.com/ahammers/emf_service_connector
- Issues & Feature-Requests bitte über GitHub














(Information updated with version 0.1.21)
