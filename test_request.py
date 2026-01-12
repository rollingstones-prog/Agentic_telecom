import requests

url = "http://localhost:8000/call/event"
payload = {
    "call_id": "test-123",
    "event_type": "CALL_STARTED"
}

try:
    response = requests.post(url, json=payload)
    print(f"Status Code: {response.status_code}")
    print(f"Response Body: {response.json()}")
except Exception as e:
    print(f"Error: {e}")
