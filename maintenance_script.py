import requests
import time
import sys

# Configuration
METRICS_URL = "http://localhost:8001/metrics"
FALLBACK_THRESHOLD = 5  # Alert if more than 5 fallbacks per check period

def check_metrics():
    """
    Parses Prometheus metrics to check for high fallback usage.
    """
    try:
        response = requests.get(METRICS_URL, timeout=5)
        response.raise_for_status()
        metrics_text = response.text

        # Simple parsing for fallback_usage_count
        # format: fallback_usage_count 1.0
        for line in metrics_text.splitlines():
            if line.startswith("fallback_usage_count"):
                value = float(line.split()[1])
                print(f"Current Fallback Usage: {value}")
                
                if value > FALLBACK_THRESHOLD:
                    print(f"ALERT: High fallback detected ({value} > {FALLBACK_THRESHOLD})!")
                    print("Action Needed: Optimize CrewAI or investigate Claude API latency.")
                else:
                    print("Status: Fallback usage within acceptable limits.")
                return

        print("fallback_usage_count metric not found.")

    except requests.exceptions.ConnectionError:
        print(f"Error: Could not connect to {METRICS_URL}. Is the Agentic OS running?")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    print("--- Agentic OS Maintenance Check ---")
    check_metrics()
