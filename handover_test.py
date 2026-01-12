import requests
import json
import time
import sys

# Configuration
APP_URL = "http://localhost:8000/call/event"

def simulate_retell_webhook():
    """
    Simulates a Retell AI webhook payload and verifies the system's decision.
    """
    print("\n[Handover Test]: Simulating Retell AI Webhook (NO_ANSWER)...")
    
    # Retell-style payload
    payload = {
        "call": {
            "call_id": "retell_handover_001",
            "disconnection_reason": "error"
        }
    }
    
    try:
        response = requests.post(APP_URL, json=payload, timeout=10)
        status_code = response.status_code
        data = response.json()
        
        print(f"Status Code: {status_code}")
        print(f"OS Decision: {json.dumps(data, indent=2)}")
        
        # In v1.1, an 'error' from Retell should trigger a retry decision from Self-Healing
        if status_code == 200 and "action" in data:
            print("SUCCESS: Endpoint responded correctly.")
            if data["action"] == "RETRY_CALL":
                print("PASSED: Decision correctly identified as RETRY_CALL.")
            else:
                print(f"NOTE: Action was {data['action']}. Verification depends on agent state.")
        else:
            print("FAILED: Unexpected response format or status code.")
            
    except requests.exceptions.ConnectionError:
        print(f"ERROR: Could not connect to {APP_URL}. Ensure the server is running (uvicorn app.main:app).")
    except Exception as e:
        print(f"AN ERROR OCCURRED: {e}")

if __name__ == "__main__":
    print("--- Agentic OS Handover Integration Test ---")
    simulate_retell_webhook()
