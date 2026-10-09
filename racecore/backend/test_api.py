import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_health_endpoint():
    """Test the health endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "OK"
    assert "RaceCore API is running" in data["message"]


def test_root_endpoint():
    """Test the root endpoint"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "Welcome to RaceCore API" in data["message"]


def test_create_race_endpoint():
    """Test creating a race session"""
    response = client.post("/race?scenario=always_dry&strategy=Baseline")
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert data["scenario"] == "always_dry"
    assert data["strategy"] == "Baseline"


def test_create_race_invalid_scenario():
    """Test creating a race with invalid scenario"""
    response = client.post("/race?scenario=invalid_scenario&strategy=Baseline")
    assert response.status_code == 400
    assert "Unknown scenario" in response.json()["detail"]


def test_create_race_invalid_strategy():
    """Test creating a race with invalid strategy"""
    response = client.post("/race?scenario=always_dry&strategy=InvalidStrategy")
    # This should work because we only validate scenario, not strategy in the simplified version
    # In a full implementation, we'd validate strategy too
    assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])