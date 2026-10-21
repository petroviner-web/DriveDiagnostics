"""DriveDiagnostics - self-contained fleet diagnostics API.

All telemetry is synthetic; thresholds are educational examples, NOT vehicle specifications.
"""
from __future__ import annotations
import os
import math
import random
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from contextlib import asynccontextmanager, contextmanager
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Literal

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("DRIVEDIAGNOSTICS_DB", "drivediagnostics.db"))
VEHICLES = [
    ("DD-101", "Audi A4", "40 TFSI", "2023", "normal"),
    ("DD-102", "BMW 320d", "M Sport", "2022", "overheat"),
    ("DD-103", "Mercedes C200", "AMG Line", "2021", "low_battery"),
    ("DD-104", "VW Golf GTI", "Performance", "2024", "oil_pressure"),
]
SCENARIOS = ["normal", "overheat", "low_battery", "oil_pressure", "excess_vibration", "mixed"]
RULES = {
    "COOLANT_HIGH": ("critical", "Engine overheating", 110, "°C"),
    "OIL_PRESSURE_LOW": ("critical", "Oil pressure below range", 20, "psi"),
    "BATTERY_LOW": ("warning", "Charging voltage below range", 12.2, "V"),
    "VIBRATION_HIGH": ("warning", "Excessive vibration", 0.7, "g"),
}

@contextmanager
def connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
        db.commit()
    finally:
        db.close()

def initialize():
    with connection() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS vehicles (
            id TEXT PRIMARY KEY, model TEXT NOT NULL, trim TEXT NOT NULL, year TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS telemetry (
            id INTEGER PRIMARY KEY AUTOINCREMENT, vehicle_id TEXT NOT NULL REFERENCES vehicles(id),
            captured_at TEXT NOT NULL, scenario TEXT NOT NULL, coolant_c REAL NOT NULL,
            oil_pressure_psi REAL NOT NULL, battery_v REAL NOT NULL,
            vibration_g REAL NOT NULL, rpm INTEGER NOT NULL, speed_kmh REAL NOT NULL,
            engine_load_pct REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS ix_telemetry_vehicle ON telemetry(vehicle_id,id);
        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT, vehicle_id TEXT NOT NULL REFERENCES vehicles(id),
            telemetry_id INTEGER NOT NULL REFERENCES telemetry(id),
            rule_code TEXT NOT NULL, severity TEXT NOT NULL, title TEXT NOT NULL,
            observed_value REAL NOT NULL, threshold REAL NOT NULL, unit TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open', detected_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS ix_incidents_vehicle ON incidents(vehicle_id,status);
        """)
        if not db.execute("SELECT 1 FROM vehicles LIMIT 1").fetchone():
            db.executemany("INSERT INTO vehicles VALUES (?,?,?,?)", [v[:4] for v in VEHICLES])
            for idx, v in enumerate(VEHICLES):
                generate(db, v[0], v[4], 90, seed=100+idx)

def evaluate(sample):
    faults = []
    if sample["coolant_c"] > 110:
        faults.append(("COOLANT_HIGH", sample["coolant_c"]))
    if sample["rpm"] >= 1500 and sample["oil_pressure_psi"] < 20:
        faults.append(("OIL_PRESSURE_LOW", sample["oil_pressure_psi"]))
    if sample["rpm"] >= 800 and sample["battery_v"] < 12.2:
        faults.append(("BATTERY_LOW", sample["battery_v"]))
    if sample["vibration_g"] > 0.7:
        faults.append(("VIBRATION_HIGH", sample["vibration_g"]))
    return faults

def generate(db, vehicle_id: str, scenario: str, samples: int, seed=None):
    rng = random.Random(seed)
    baseline = datetime.now(timezone.utc) - timedelta(seconds=samples * 10)
    new_incidents = set()
    for i in range(samples):
        progress = i / max(samples-1, 1)
        rpm = max(850, int(2200 + 650*math.sin(i/9) + rng.uniform(-200,200)))
        sample = {
            "vehicle_id": vehicle_id, "scenario": scenario,
            "captured_at": (baseline + timedelta(seconds=i*10)).isoformat(),
            "coolant_c": round(89+rng.uniform(-3,3),2),
            "oil_pressure_psi": round(46+rng.uniform(-6,6),2),
            "battery_v": round(14.1+rng.uniform(-0.25,0.25),2),
            "vibration_g": round(0.16+rng.uniform(0,0.12),3),
            "rpm": rpm, "speed_kmh": round(62+rng.uniform(-15,15),1),
            "engine_load_pct": round(45+rng.uniform(-18,18),1),
        }
        if scenario in ("overheat", "mixed"):
            sample["coolant_c"] = round(92 + 35*progress + rng.uniform(-1,1),2)
        if scenario in ("low_battery", "mixed"):
            sample["battery_v"] = round(14 - 2.9*progress + rng.uniform(-0.08,0.08),2)
        if scenario in ("oil_pressure", "mixed"):
            sample["oil_pressure_psi"] = round(45 - 34*progress + rng.uniform(-1,1),2)
        if scenario in ("excess_vibration", "mixed"):
            sample["vibration_g"] = round(0.2 + 0.8*progress + rng.uniform(-0.02,0.02),3)
        fields = list(sample)
        cursor = db.execute(
            "INSERT INTO telemetry ("+",".join(fields)+") VALUES ("+",".join("?" for _ in fields)+")",
            [sample[f] for f in fields])
        for code, observed in evaluate(sample):
            if code in new_incidents:
                continue
            new_incidents.add(code)
            severity, title, threshold, unit = RULES[code]
            db.execute("""INSERT INTO incidents
                (vehicle_id,telemetry_id,rule_code,severity,title,observed_value,threshold,unit,status,detected_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (vehicle_id,cursor.lastrowid,code,severity,title,observed,threshold,unit,"open",sample["captured_at"]))
    return {"created_samples":samples,"created_incidents":len(new_incidents)}

def rows(cursor):
    return [dict(x) for x in cursor.fetchall()]

def vehicle_list(db):
    result = rows(db.execute("SELECT * FROM vehicles ORDER BY id"))
    for v in result:
        v["latest"] = next(iter(rows(db.execute(
            "SELECT * FROM telemetry WHERE vehicle_id=? ORDER BY id DESC LIMIT 1",(v["id"],)))),None)
        active = rows(db.execute("SELECT severity FROM incidents WHERE vehicle_id=? AND status!='resolved'",(v["id"],)))
        v["active_incidents"] = len(active)
        v["health"] = ("critical" if any(x["severity"]=="critical" for x in active)
                       else "warning" if active else "healthy")
    return result

@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize()
    yield

app = FastAPI(title="DriveDiagnostics API",version="1.0.0",
              description="Synthetic automotive diagnostics; educational demo only.",lifespan=lifespan)
app.mount("/static",StaticFiles(directory=str(ROOT/"static")),name="static")

class SimulationRequest(BaseModel):
    vehicle_id: str
    scenario: Literal["normal","overheat","low_battery","oil_pressure","excess_vibration","mixed"] = "normal"
    samples: int = Field(default=90,ge=10,le=200)

class IncidentUpdate(BaseModel):
    status: Literal["open","investigating","resolved"]

@app.get("/",include_in_schema=False)
def home():
    return FileResponse(ROOT/"static"/"index.html")

@app.get("/api/health")
def health():
    return {"status":"ok","source":"synthetic","version":"1.0.0"}

@app.get("/api/vehicles")
def vehicles():
    with connection() as db:
        return vehicle_list(db)

@app.get("/api/summary")
def summary():
    with connection() as db:
        fleet=vehicle_list(db)
        incidents=rows(db.execute("SELECT * FROM incidents"))
        return {
            "total_vehicles":len(fleet),
            "healthy_vehicles":sum(v["health"]=="healthy" for v in fleet),
            "attention_vehicles":sum(v["health"]!="healthy" for v in fleet),
            "open_incidents":sum(x["status"]!="resolved" for x in incidents),
            "critical_incidents":sum(x["status"]!="resolved" and x["severity"]=="critical" for x in incidents),
            "total_samples":db.execute("SELECT COUNT(*) FROM telemetry").fetchone()[0],
        }

@app.get("/api/vehicles/{vehicle_id}/telemetry")
def telemetry(vehicle_id:str,limit:int=Query(default=90,ge=1,le=500)):
    with connection() as db:
        if not db.execute("SELECT 1 FROM vehicles WHERE id=?",(vehicle_id,)).fetchone():
            raise HTTPException(404,"Vehicle not found")
        return list(reversed(rows(db.execute(
            "SELECT * FROM telemetry WHERE vehicle_id=? ORDER BY id DESC LIMIT ?",(vehicle_id,limit)))))

@app.get("/api/incidents")
def incidents(status:Literal["open","investigating","resolved"]|None=None,
              vehicle_id:str|None=None,limit:int=Query(default=100,ge=1,le=500)):
    with connection() as db:
        clauses=[]; params=[]
        if status: clauses.append("status=?");params.append(status)
        if vehicle_id: clauses.append("vehicle_id=?");params.append(vehicle_id)
        sql="SELECT * FROM incidents"+(" WHERE "+" AND ".join(clauses) if clauses else "")
        return rows(db.execute(sql+" ORDER BY id DESC LIMIT ?",(*params,limit)))

@app.patch("/api/incidents/{incident_id}")
def update_incident(incident_id:int,payload:IncidentUpdate):
    with connection() as db:
        if not db.execute("SELECT 1 FROM incidents WHERE id=?",(incident_id,)).fetchone():
            raise HTTPException(404,"Incident not found")
        db.execute("UPDATE incidents SET status=? WHERE id=?",(payload.status,incident_id))
        return dict(db.execute("SELECT * FROM incidents WHERE id=?",(incident_id,)).fetchone())

@app.post("/api/simulate",status_code=201)
def simulate(payload:SimulationRequest):
    with connection() as db:
        if not db.execute("SELECT 1 FROM vehicles WHERE id=?",(payload.vehicle_id,)).fetchone():
            raise HTTPException(404,"Vehicle not found")
        return {"vehicle_id":payload.vehicle_id,"scenario":payload.scenario,
                **generate(db,payload.vehicle_id,payload.scenario,payload.samples)}
