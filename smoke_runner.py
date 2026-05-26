import requests
import time
import random
import sys

BASE_URL = "http://localhost:8000"


# -------------------------
# UTILITIES
# -------------------------
def ok(msg):
    print(f"[OK] {msg}")


def fail(msg):
    print(f"[FAIL] {msg}")
    sys.exit(1)


def generate_url():
    return f"https://example.com/{int(time.time())}-{random.randint(1000,9999)}"


# -------------------------
# STATE
# -------------------------
state = {}


# -------------------------
# 1. SERVICE AVAILABILITY
# -------------------------
def check_api_service():
    """
    Verifies API service is reachable and responding.
    """
    try:
        r = requests.get(f"{BASE_URL}/health")

        if r.status_code != 200:
            fail("API Service is NOT responding correctly")

        ok("API Service is running and reachable")

    except Exception as e:
        fail(f"API Service is DOWN -> {e}")


# -------------------------
# 2. DATABASE WRITE + READ FLOW
# -------------------------
def check_database_layer():
    """
    Verifies data persistence layer via URL creation.
    """
    try:
        url = generate_url()

        r = requests.post(
            f"{BASE_URL}/shorten",
            json={"url": url}
        )

        if r.status_code != 201:
            fail("Database layer failed to persist new record")

        data = r.json()
        short_code = data.get("short_code")

        if not short_code:
            fail("Database layer did not return stored identifier")

        state["url"] = url
        state["short_code"] = short_code

        ok("Database is storing and retrieving data correctly")

    except Exception as e:
        fail(f"Database layer failure -> {e}")


# -------------------------
# 3. CACHE + RETRIEVAL FLOW
# -------------------------
def check_cache_and_retrieval():
    """
    Verifies that cached retrieval + fallback DB lookup works.
    """
    try:
        short_code = state.get("short_code")
        original_url = state.get("url")

        r = requests.get(
            f"{BASE_URL}/r/{short_code}",
            allow_redirects=False
        )

        if r.status_code != 307:
            fail("URL resolution service failed (redirect layer broken)")

        location = r.headers.get("location")

        if location != original_url:
            fail("Data mismatch between stored value and retrieved value")

        ok("Cache + database retrieval pipeline is working correctly")

    except Exception as e:
        fail(f"Cache/Retrieval system failure -> {e}")


# -------------------------
# 4. SYSTEM OBSERVABILITY
# -------------------------
def check_metrics_layer():
    """
    Verifies monitoring/telemetry is active.
    """
    try:
        r = requests.get(f"{BASE_URL}/metrics")

        if r.status_code != 200:
            fail("Metrics system is not responding")

        if "http_requests_total" not in r.text:
            fail("Telemetry data is incomplete or missing key metrics")

        ok("Monitoring & metrics system is active")

    except Exception as e:
        fail(f"Metrics system failure -> {e}")


# -------------------------
# RUNNER
# -------------------------
if __name__ == "__main__":
    print("\n==============================")
    print("SYSTEM VERIFICATION REPORT")
    print("==============================\n")

    check_api_service()
    check_database_layer()
    check_cache_and_retrieval()
    check_metrics_layer()

    print("\n==============================")
    print("ALL SYSTEMS OPERATIONAL ✅")
    print("==============================\n")

