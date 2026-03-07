import json
import io
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_mock_gov_portal():
    print("Testing /mock-gov-portal...")
    response = client.get("/mock-gov-portal")
    assert response.status_code == 200
    print("✅ /mock-gov-portal OK")

def test_api_agent_query():
    print("Testing /api/agent with query intent...")
    # Simulated form data
    data = {
        "user_text": "What is PM Awas Yojana?",
        "user_id": "test_123",
        "user_name": "Test User",
        "session_id": "test_session_1"
    }

    response = client.post(
        "/api/agent",
        data=data
    )
    assert response.status_code == 200, f"Error: {response.text}"
    content = response.content.decode('utf-8')
    print("✅ /api/agent (query) returned data:", content[:100], "...")

def test_api_agent_apply():
    print("Testing /api/agent with apply intent (no files yet)...")
    data = {
        "user_text": "I want to apply",
        "user_id": "test_123",
        "user_name": "Test User",
    }
    response = client.post(
        "/api/agent",
        data=data
    )
    assert response.status_code == 200, f"Error: {response.text}"
    json_resp = response.json()
    assert json_resp["intent"] == "apply"
    print("✅ /api/agent (apply) returned:", json_resp)

if __name__ == "__main__":
    test_mock_gov_portal()
    test_api_agent_query()
    test_api_agent_apply()
    print("All basic tests passed!")
