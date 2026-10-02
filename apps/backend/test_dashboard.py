"""
Quick test script to verify dashboard connectivity and generate test alerts.
"""

import json
import time

import requests

BASE_URL = "http://localhost:8000"

def test_backend():
    """Test backend connectivity."""
    print("[*] Testing backend connectivity...")

    try:
        response = requests.get(f"{BASE_URL}/health")
        print(f"[+] Backend is running: {response.json()}")
    except Exception as e:
        print(f"[-] Backend is not running: {e}")
        return False

    return True


def test_dashboard_routes():
    """Test dashboard routes."""
    print("\n[*] Testing dashboard routes...")

    # Test streams endpoint
    try:
        response = requests.get(f"{BASE_URL}/dashboard/streams")
        print(f"[+] Dashboard streams: {response.json()}")
    except Exception as e:
        print(f"[!] Dashboard streams not available (may need restart): {e}")

    # Test status endpoint
    try:
        response = requests.get(f"{BASE_URL}/dashboard/status")
        print(f"[+] Dashboard status: {response.json()}")
    except Exception as e:
        print(f"[!] Dashboard status not available (may need restart): {e}")


def create_test_alert():
    """Create a test alert."""
    print("\n[*] Creating test alert...")

    try:
        response = requests.post(f"{BASE_URL}/dashboard/test-alert")
        result = response.json()
        print(f"[+] Test alert created: {result}")
        return True
    except Exception as e:
        print(f"[!] Could not create test alert (routes may not be loaded): {e}")
        return False


def create_multiple_test_alerts():
    """Create multiple test alerts."""
    print("\n[*] Creating multiple test alerts...")

    test_alerts = [
        {
            "service": "auth-service",
            "severity": "critical",
            "message": "Authentication failure rate spike detected",
            "error_rate": 12.5
        },
        {
            "service": "api-gateway",
            "severity": "warning",
            "message": "High latency detected on /api/users endpoint",
            "error_rate": 3.2
        },
        {
            "service": "database",
            "severity": "info",
            "message": "Scheduled maintenance completed successfully",
        }
    ]

    for alert in test_alerts:
        try:
            # Simulate alert by making request (will fail if routes not loaded)
            response = requests.post(f"{BASE_URL}/dashboard/test-alert")
            if response.status_code == 200:
                print(f"[+] Created alert for {alert['service']}")
            else:
                print("[!] Routes not loaded yet")
                break
        except Exception as e:
            print(f"[!] Dashboard routes not available: {e}")
            break

        time.sleep(0.5)  # Small delay between alerts


if __name__ == "__main__":
    print("=" * 60)
    print("DevRelAgent Dashboard Connectivity Test")
    print("=" * 60)

    if test_backend():
        test_dashboard_routes()
        create_test_alert()
        create_multiple_test_alerts()

    print("\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. If dashboard routes are not available, restart the backend:")
    print("   - Stop the current backend process (Ctrl+C)")
    print("   - Run: python main.py")
    print("2. Open your browser to: http://localhost:3000/dashboard")
    print("3. You should see real-time alerts appearing in the dashboard")
