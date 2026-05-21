import requests
import time
import random
import sys
import os

# -------------------------------------------------
# CONFIG (CI-friendly)
# -------------------------------------------------

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
TIMEOUT = int(os.getenv("TIMEOUT", "5"))

state = {}

# -------------------------------------------------
# UTILITIES
# -------------------------------------------------

def ok(msg):
    print(f"[OK] {msg}")


def fail(msg):
    print(f"[FAIL] {msg}")
    sys.exit(1)


def wait_for_service():
    """
    Wait until API becomes ready before running tests.
    Important for docker-compose startup delay.
    """
    print("[INFO] Waiting for API to be ready...")

    for i in range(1, 31):
        try:
            r = requests.get(f"{BASE_URL}/health", timeout=TIMEOUT)
            if r.status_code == 200:
                ok("API is ready")
                return
        except:
            pass

        time.sleep(1)

    fail("API did not become ready in time")


def generate_url():
    return f"https://example.com/{int(time.time())}-{random.randint(1000,9999)}"

# -------------------------------------------------
# TEST 1: HEALTH CHECK
# -------------------------------------------------

def check_api_service():
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=TIMEOUT)

        if r.status_code != 200:
            fail("API health check failed")

        ok("API is reachable")

    except Exception as e:
        fail(f"API unreachable -> {e}")

# -------------------------------------------------
# TEST 2: CREATE FLOW
# -------------------------------------------------

def check_database_layer():
    try:
        url = generate_url()

        r = requests.post(
            f"{BASE_URL}/shorten",
            json={"url": url},
            timeout=TIMEOUT
        )

        if r.status_code != 201:
            fail("Create URL failed (DB layer issue)")

        data = r.json()
        short_code = data.get("short_code")

        if not short_code:
            fail("No short_code returned")

        state["url"] = url
        state["short_code"] = short_code

        ok("Create flow works (DB OK)")

    except Exception as e:
        fail(f"Create flow failed -> {e}")

# -------------------------------------------------
# TEST 3: REDIRECT FLOW
# -------------------------------------------------

def check_cache_and_retrieval():
    try:
        short_code = state["short_code"]
        original_url = state["url"]

        r = requests.get(
            f"{BASE_URL}/r/{short_code}",
            allow_redirects=False,
            timeout=TIMEOUT
        )

        if r.status_code not in (302, 307):
            fail("Redirect failed")

        location = r.headers.get("location")

        if location != original_url:
            fail("Redirect mismatch")

        ok("Redirect flow works (cache/db OK)")

    except Exception as e:
        fail(f"Redirect test failed -> {e}")

# -------------------------------------------------
# TEST 4: METRICS
# -------------------------------------------------

def check_metrics_layer():
    try:
        r = requests.get(f"{BASE_URL}/metrics", timeout=TIMEOUT)

        if r.status_code != 200:
            fail("Metrics endpoint failed")

        if "http_requests_total" not in r.text:
            fail("Metrics data missing")

        ok("Metrics working")

    except Exception as e:
        fail(f"Metrics failed -> {e}")

# -------------------------------------------------
# RUNNER
# -------------------------------------------------

if __name__ == "__main__":
    print("\n==============================")
    print(" CI SMOKE TEST SUITE ")
    print("==============================\n")

    wait_for_service()

    check_api_service()
    check_database_layer()
    check_cache_and_retrieval()
    check_metrics_layer()

    print("\n==============================")
    print(" ALL SYSTEMS GREEN ")
    print("==============================\n")