# DriveDiagnostics

**Automotive telemetry dashboard and explainable fault detection — full-stack portfolio demo.**

DriveDiagnostics monitors four simulated vehicles, graphs sensor measurements, detects rule-based anomalies and tracks incident resolution. Designed as an educational demonstration of backend APIs, database persistence, diagnostics logic and frontend visualization.

> **Safety and provenance:** All sensor data is **synthetic**. Diagnostic thresholds are illustrative only; they are not manufacturer values and must never be used for real automotive diagnostics or driving decisions. The app does not connect to an ECU, CAN bus or OBD interface.

## Highlights

- Four demo vehicles with pre-seeded normal and abnormal driving sessions
- Six simulation scenarios: normal, overheat, low battery, oil pressure, excessive vibration and mixed
- Telemetry values: coolant temperature, oil pressure, voltage, vibration, RPM, speed and engine load
- Rule-based, explainable incident detection
- Incident workflow: open → investigating → resolved
- Responsive web dashboard with fleet health overview and interactive charts
- REST API and automatically generated Swagger documentation
- SQLite persistence, automated tests and GitHub Actions
- Docker and Docker Compose support

## Technology

Python 3.11+, FastAPI, Pydantic, SQLite, HTML, CSS, JavaScript, Canvas, pytest and Docker.

## Start locally

```bash
git clone https://github.com/petroviner-web/DriveDiagnostics.git
cd DriveDiagnostics
python -m venv .venv
```

Activate the virtual environment (PowerShell: `.venv\Scripts\Activate.ps1`; Linux/macOS: `source .venv/bin/activate`) and run:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open **http://localhost:8000** for the dashboard and **http://localhost:8000/docs** for the Swagger UI.

### Docker

```bash
docker compose up --build
```

The app runs on localhost:8000 and persists its SQLite database in a Docker volume.

## API endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Health check and synthetic-data flag |
| GET | `/api/summary` | Fleet health counts |
| GET | `/api/vehicles` | All vehicles and latest readings |
| GET | `/api/vehicles/{id}/telemetry?limit=90` | Chronological telemetry |
| GET | `/api/incidents?status=open` | Diagnostic incidents |
| PATCH | `/api/incidents/{id}` | Update incident status |
| POST | `/api/simulate` | Generate sensor readings |

To simulate a multi-fault drive:

```bash
curl -X POST http://127.0.0.1:8000/api/simulate -H "Content-Type: application/json" -d '{"vehicle_id":"DD-101","scenario":"mixed","samples":90}'
```

## Diagnostic rules

| Code | Example trigger | Severity |
|---|---|---|
| COOLANT_HIGH | Coolant over 110°C | Critical |
| OIL_PRESSURE_LOW | Oil pressure below 20 psi at ≥1500 RPM | Critical |
| BATTERY_LOW | Charging voltage below 12.2 V at ≥800 RPM | Warning |
| VIBRATION_HIGH | Vibration above 0.7 g | Warning |

These are **made-up demonstration thresholds**, not automotive standards.

## Architecture

```text
Browser
  └─ HTML / CSS / JavaScript dashboard
        └─ FastAPI REST API
              ├─ Synthetic telemetry generator
              ├─ Explainable rule evaluation
              ├─ Incident lifecycle
              └─ SQLite storage
```

## Tests

```bash
pytest -q
```

GitHub Actions runs tests on pushes and pull requests.

## Next steps

Time-series analytics, vehicle-specific threshold profiles, CSV export, configurable alerts, PostgreSQL migrations, and WebSocket streaming.

**Portfolio project — not for commercial or real-world vehicle diagnostics.**
