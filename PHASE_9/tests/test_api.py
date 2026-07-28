"""tests/test_api.py"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    """Build a fresh TestClient and preload the pipeline singleton with synthetic data."""
    from api.main import app
    from pipeline import pipeline

    # Reset any state from a previous test module
    pipeline.scored_trips_df = None
    pipeline.events_df = None
    pipeline.raw_df = None

    csv_content = (
        "DayNum,VehId,Trip,Timestamp(ms),Latitude[deg],Longitude[deg],"
        "Vehicle Speed[km/h],MAF[g/sec],Engine RPM[RPM],Absolute Load[%],"
        "OAT[DegC],Fuel Rate[L/hr],Air Conditioning Power[kW],"
        "Air Conditioning Power[Watts],Heater Power[Watts],HV Battery Current[A],"
        "HV Battery SOC[%],HV Battery Voltage[V],Short Term Fuel Trim Bank 1[%],"
        "Short Term Fuel Trim Bank 2[%],Long Term Fuel Trim Bank 1[%],"
        "Long Term Fuel Trim Bank 2[%]\n"
    )
    rows = []
    for i in range(30):
        rows.append(f"1.5,42,7,{i*300},42.28,{-83.70 + i*0.0002},{15+i%20},10,2000,50,,2,,,,,,,,,,\n")
    csv_content += "".join(rows)
    file_path = tmp_path / "sample.csv"
    file_path.write_text(csv_content)

    test_client = TestClient(app)
    test_client.post("/pipeline/run", params={"source": str(file_path)})
    return test_client


class TestHealthEndpoint:
    def test_health_ok(self):
        from api.main import app
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        assert "status" in response.json()


class TestDriverEndpoints:
    def test_driver_profile(self, client):
        response = client.get("/driver/profile", params={"veh_id": 42})
        assert response.status_code == 200
        body = response.json()
        assert body["veh_id"] == 42
        assert body["profile"] in {
            "Safe Driver", "Eco Driver", "Normal Driver",
            "Aggressive Driver", "High Risk Driver",
        }

    def test_driver_score(self, client):
        response = client.get("/driver/score", params={"veh_id": 42})
        assert response.status_code == 200
        assert 0 <= response.json()["driver_score"] <= 100

    def test_driver_coaching(self, client):
        response = client.get("/driver/coaching", params={"veh_id": 42, "use_llm": False})
        assert response.status_code == 200
        assert len(response.json()["cards"]) >= 1

    def test_driver_statistics(self, client):
        response = client.get("/driver/statistics", params={"veh_id": 42})
        assert response.status_code == 200
        assert response.json()["trip_count"] >= 1

    def test_driver_trips(self, client):
        response = client.get("/driver/trips", params={"veh_id": 42})
        assert response.status_code == 200
        assert response.json()["trip_count"] >= 1

    def test_unknown_driver_returns_404(self, client):
        response = client.get("/driver/profile", params={"veh_id": 999999})
        assert response.status_code == 404
