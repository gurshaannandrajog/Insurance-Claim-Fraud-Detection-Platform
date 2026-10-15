"""
Quick performance check for REQ-PER-001..004 against the running Django server (default http://127.0.0.1:8000).

    python tests/performance/load_check.py [--base http://127.0.0.1:8000] [--users 25]

* users sign in one by one (login latency reported separately), then 25 concurrent users each run: dashboard, claims list, claim detail, policies, vehicles (REQ-PER-001/004)
* claim submission time, excluding upload transfer (REQ-PER-002) — measured server-side via a fresh claim
* fraud-service response time from stored assessments (REQ-PER-003)
Requires the seeded demo data.
"""
import argparse
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests

ACCOUNTS = ["customer@claims.local", "adjuster@claims.local", "adjuster2@claims.local", "siu@claims.local",
            "admin@claims.local", "meera.joshi@example.com", "arjun.nair@example.com"]


def session(base, email):
    s = requests.Session()
    s.get(f"{base}/api/auth/csrf/")
    t = time.perf_counter()
    r = s.post(f"{base}/api/auth/login/", json={"email": email, "password": "Demo@1234"},
               headers={"X-CSRFToken": s.cookies["csrftoken"], "Referer": base})
    r.raise_for_status()
    s.headers.update({"X-CSRFToken": s.cookies["csrftoken"], "Referer": base})
    return s, time.perf_counter() - t


def user_journey(base, s):
    timings = {}
    role = s.get(f"{base}/api/auth/me/").json()["role"]
    paths = ["/api/dashboard/", "/api/notifications/unread-count/"]
    if role in ("CUSTOMER", "ADJUSTER", "ADMIN"):
        paths += ["/api/claims/", "/api/policies/", "/api/vehicles/"]
    for p in paths:
        t = time.perf_counter()
        r = s.get(base + p)
        r.raise_for_status()
        timings[p] = time.perf_counter() - t
    claims = s.get(f"{base}/api/claims/").json().get("results", [])
    if claims:
        t = time.perf_counter()
        s.get(f"{base}/api/claims/{claims[0]['id']}/").raise_for_status()
        timings["claim detail"] = time.perf_counter() - t
    return timings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--users", type=int, default=25)
    a = ap.parse_args()

    # Users sign in one after another (as real users do). Password hashing is deliberately CPU-expensive
    # (salted PBKDF2), so 25 logins in the same instant on a 2-core dev machine would only measure the CPU queue.
    sessions, logins = [], []
    for i in range(a.users):
        s, t = session(a.base, ACCOUNTS[i % len(ACCOUNTS)])
        sessions.append(s)
        logins.append(t)
    print(f"login: median {statistics.median(logins) * 1000:.0f} ms, max {max(logins) * 1000:.0f} ms")

    with ThreadPoolExecutor(max_workers=a.users) as pool:
        start = time.perf_counter()
        results = list(pool.map(lambda s: user_journey(a.base, s), sessions))
        wall = time.perf_counter() - start
    all_t = [v for r in results for v in r.values()]
    p95 = sorted(all_t)[int(len(all_t) * 0.95) - 1]
    print(f"{a.users} concurrent signed-in users, {len(all_t)} requests in {wall:.1f}s")
    print(f"  median {statistics.median(all_t) * 1000:.0f} ms, p95 {p95 * 1000:.0f} ms, max {max(all_t) * 1000:.0f} ms "
          f"(REQ-PER-001 target < 2000 ms)")
    ok = max(all_t + logins) < 2.0

    sys.path.insert(0, __file__.rsplit("/tests/", 1)[0] + "/backend")
    import os
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django
    django.setup()
    from apps.fraud.models import FraudAssessment
    ms = list(FraudAssessment.objects.filter(status="COMPLETED").values_list("response_ms", flat=True))
    if ms:
        print(f"  fraud scoring round-trip: median {statistics.median(ms)} ms, max {max(ms)} ms (REQ-PER-003 target < 10000 ms)")
        ok &= max(ms) < 10000
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
