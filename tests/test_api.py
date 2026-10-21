from fastapi.testclient import TestClient
from app.main import app, evaluate
from unittest.mock import patch

def test_fault_rules():
    baseline={"coolant_c":90,"oil_pressure_psi":45,"battery_v":14,"vibration_g":0.2,"rpm":2000}
    assert evaluate(baseline)==[]
    assert evaluate({**baseline,"coolant_c":118})[0][0]=="COOLANT_HIGH"
    assert evaluate({**baseline,"rpm":0,"oil_pressure_psi":5})==[]
    assert evaluate({**baseline,"oil_pressure_psi":5})[0][0]=="OIL_PRESSURE_LOW"

def test_api(tmp_path):
    with patch("app.main.DB_PATH",tmp_path/"test.db"):
        with TestClient(app) as client:
            assert client.get("/").status_code==200
            assert client.get("/api/health").json()["source"]=="synthetic"
            assert len(client.get("/api/vehicles").json())==4
            assert client.get("/api/summary").json()["total_samples"]==360
            assert len(client.get("/api/vehicles/DD-101/telemetry").json())==90
            assert client.get("/api/vehicles/not-found/telemetry").status_code==404
            r=client.post("/api/simulate",json={"vehicle_id":"DD-101","scenario":"mixed","samples":90})
            assert r.status_code==201
            assert r.json()["created_incidents"]==4
            alert=client.get("/api/incidents?status=open").json()[0]
            result=client.patch(f"/api/incidents/{alert['id']}",json={"status":"resolved"})
            assert result.json()["status"]=="resolved"
            assert client.post("/api/simulate",json={"vehicle_id":"DD-101","scenario":"bad"}).status_code==422
