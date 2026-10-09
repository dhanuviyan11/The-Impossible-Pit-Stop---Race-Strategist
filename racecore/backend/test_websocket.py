import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_websocket_endpoint_exists():
    """Test that the WebSocket endpoint exists (basic test)"""
    # We can't easily test WebSockets with TestClient in a simple way
    # but we can at least verify the route exists
    from main import app
    routes = [route.path for route in app.routes]
    assert any("/race/{session_id}" in route for route in routes)


def test_inject_endpoint_exists():
    """Test that the inject endpoint exists"""
    from main import app
    routes = [route.path for route in app.routes]
    assert any("/race/{session_id}/inject" in route for route in routes)


def test_override_endpoint_exists():
    """Test that the override endpoint exists"""
    from main import app
    routes = [route.path for route in app.routes]
    assert any("/race/{session_id}/override" in route for route in routes)


def test_decisions_endpoint_exists():
    """Test that the decisions endpoint exists"""
    from main import app
    routes = [route.path for route in app.routes]
    assert any("/race/{session_id}/decisions" in route for route in routes)


def test_replay_endpoint_exists():
    """Test that the replay endpoint exists"""
    from main import app
    routes = [route.path for route in app.routes]
    assert any("/race/{session_id}/replay" in route for route in routes)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])