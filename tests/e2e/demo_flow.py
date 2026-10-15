"""
End-to-end browser test of the SRS demo scenario against the RUNNING system
(React on :5173 → Django on :8000 → MySQL, Django → Flask on :5001).

    python tests/e2e/demo_flow.py --django-log /path/to/runserver.log

Requires: demo data seeded, the three servers running, Django using the console email backend with its output
written to the log file passed in (the script reads verification / reset links from it), `pip install playwright`.
Every step uses real clicks, real file uploads and the real email link — nothing is mocked.
"""
import argparse
import re
import sys
import time
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from apps.core.sample_files import jpeg_bytes, pdf_bytes  # noqa: E402

BASE = "http://127.0.0.1:5173"
PASSWORD = "Demo@1234"
RUN = str(int(time.time()))[-5:]
EMAIL = f"aisha.khan{RUN}@example.com"
REG = f"MH47ZZ{RUN[-4:]}"


def step(msg):
    print(f"  ✓ {msg}", flush=True)


def files(tmp: Path):
    tmp.mkdir(parents=True, exist_ok=True)
    out = {}
    for name, data in {"kyc.pdf": pdf_bytes("KYC — Aadhaar"), "address.pdf": pdf_bytes("Electricity bill"),
                       "rc.pdf": pdf_bytes("Registration certificate"), "front.jpg": jpeg_bytes("Bumper damage"),
                       "estimate.pdf": pdf_bytes("Repair estimate", ["Bumper 21,000", "Labour 6,500"])}.items():
        (tmp / name).write_bytes(data)
        out[name] = str(tmp / name)
    (tmp / "malware.pdf").write_bytes(b"MZ\x90\x00 not a pdf")
    out["malware.pdf"] = str(tmp / "malware.pdf")
    return out


def link_from_log(log: Path, pattern, after: int):
    for _ in range(40):
        text = log.read_text(errors="ignore")[after:]
        text = re.sub(r"=\r?\n", "", text)  # quoted-printable soft breaks
        m = re.findall(pattern, text)
        if m:
            return m[-1]
        time.sleep(0.25)
    raise AssertionError(f"No email matching {pattern} in the Django log")


def login(page, email, password=PASSWORD):
    page.goto(f"{BASE}/login")
    page.fill("#email", email)
    page.fill("#password", password)
    page.click("button:has-text('Sign in')")
    page.wait_for_url(re.compile(r"/(dashboard|staff|siu|admin)$"))


def pick(select, contains):
    """Choose the <option> whose text contains `contains`."""
    value = select.evaluate("(s, t) => [...s.options].find(o => o.text.includes(t)).value", contains)
    select.select_option(value)


def toast(page, text):
    expect(page.get_by_role("status").filter(has_text=text).first).to_be_visible(timeout=15000)


PAGES = []


@contextmanager
def screenshots_on_failure():
    """Exits before Playwright closes the browser, so failing pages can still be captured."""
    try:
        yield
    except Exception:
        for i, pg in enumerate(PAGES):
            try:
                pg.screenshot(path=f"/tmp/e2e-failure-{i}.png", full_page=True)
            except Exception:
                pass
        print("Screenshots of open pages saved to /tmp/e2e-failure-*.png")
        raise


def run(log_path: Path, headed=False):
    f = files(Path("/tmp/e2e-files"))
    with sync_playwright() as p, screenshots_on_failure():
        browser = p.chromium.launch(headless=not headed)
        def new():
            page = browser.new_context(viewport={"width": 1366, "height": 900}).new_page()
            PAGES.append(page)
            return page

        print("Customer onboarding")
        c = new()
        c.goto(f"{BASE}/register")
        for k, v in {"full_name": "Aisha Khan", "email": EMAIL, "phone": "+919833344455", "date_of_birth": "1994-02-14",
                     "address_line": "4 Carter Road, Bandra", "city": "Mumbai", "state": "Maharashtra",
                     "postal_code": "400050", "password": PASSWORD, "confirm_password": PASSWORD}.items():
            c.fill(f"#{k}", v)
        offset = log_path.stat().st_size
        c.click("button:has-text('Create account')")
        expect(c.get_by_text("Check your inbox")).to_be_visible()
        step("registered")
        c.goto(f"{BASE}/login"); c.fill("#email", EMAIL); c.fill("#password", PASSWORD)
        c.click("button:has-text('Sign in')")
        expect(c.get_by_text("verify your email")).to_be_visible()
        step("login blocked until email is verified")
        token = link_from_log(log_path, r"/verify-email\?token=([\w:\-]+)", offset)
        c.goto(f"{BASE}/verify-email?token={token}")
        expect(c.get_by_text("Your email is verified")).to_be_visible()
        step("verified via the emailed link")
        login(c, EMAIL)
        step("signed in")

        c.goto(f"{BASE}/vehicles?add=1")
        for k, v in {"registration_number": REG, "make": "Hyundai", "model": "Venue SX", "manufacturing_year": "2023",
                     "registration_date": "2023-05-02", "purchase_date": "2023-04-28", "engine_number": f"G4LC{RUN}",
                     "chassis_number": f"MALC381{RUN}", "color": "Typhoon Silver"}.items():
            c.fill(f"#{k}", v)
        c.select_option("#vehicle_type", "SUV")
        c.click("button:has-text('Add vehicle') >> nth=-1")
        toast(c, "Vehicle added")
        step(f"vehicle {REG} added")

        c.goto(f"{BASE}/vehicles?add=1")
        for k, v in {"registration_number": REG, "make": "X", "model": "Y", "manufacturing_year": "2022",
                     "registration_date": "2022-01-01", "purchase_date": "2022-01-01", "engine_number": "DUP1",
                     "chassis_number": "DUP2", "color": "Red"}.items():
            c.fill(f"#{k}", v)
        c.click("button:has-text('Add vehicle') >> nth=-1")
        expect(c.get_by_text("already registered").first).to_be_visible()
        c.click("button:has-text('Cancel')")
        step("duplicate registration number rejected by the server")

        c.goto(f"{BASE}/policies?request=1")
        dialog = c.get_by_role("dialog")
        pick(dialog.locator("select").nth(0), REG)
        pick(dialog.locator("select").nth(1), "Comprehensive Standard")
        dialog.locator("input[type=number]").fill("900000")
        expect(dialog.get_by_text("Estimated premium")).to_be_visible()
        dialog.get_by_role("button", name="Send request").click()
        toast(c, "Policy request sent")
        step("policy requested")

        print("Administrator issues the policy")
        a = new()
        login(a, "admin@claims.local")
        a.goto(f"{BASE}/admin/policy-requests")
        row = a.locator("tr", has_text=REG)
        row.get_by_role("button", name="Approve").click()
        a.get_by_role("button", name="Issue policy").click()
        toast(a, "issued")
        step("policy issued")

        c.goto(f"{BASE}/policies")
        card = c.locator("article", has_text=REG)
        expect(card.get_by_text("Active")).to_be_visible()
        step("customer sees the Active policy")

        print("Claim submission")
        c.goto(f"{BASE}/claims/new")
        c.locator("label", has_text=REG).click()
        c.click("button:has-text('Continue')")
        c.fill("#requested_amount", "27500")
        # the policy was issued today, so the incident must be today (earlier than now) to fall inside its period
        c.fill("#incident_date", date.today().isoformat())
        c.fill("#incident_time", "00:05")
        c.fill("#incident_location", "Linking Road, Bandra West, Mumbai")
        c.fill("#description", "A taxi reversed into my parked car outside a shop. Front bumper cracked, left fog lamp broken.")
        c.click("button:has-text('Continue')")
        c.click("button:has-text('Continue')")
        expect(c.get_by_text("Upload: KYC details")).to_be_visible()
        step("submission blocked without mandatory documents")
        rows = c.locator("ul.divide-y > li")
        rows.nth(0).locator("input[type=file]").set_input_files(f["malware.pdf"])
        rows.nth(0).locator("input[type=file]").set_input_files(f["kyc.pdf"])
        rows.nth(1).locator("input[type=file]").set_input_files(f["address.pdf"])
        rows.nth(2).locator("input[type=file]").set_input_files(f["rc.pdf"])
        rows.nth(3).locator("input[type=file]").set_input_files(f["front.jpg"])
        c.click("button:has-text('Continue')")
        c.click("button:has-text('Submit claim')")
        c.get_by_role("dialog").get_by_role("button", name="Submit claim").click()
        c.wait_for_url(re.compile(r"/claims/\d+$"))
        claim_url = c.url
        claim_id = claim_url.rsplit("/", 1)[-1]
        claim_no = c.locator("h1").inner_text()
        expect(c.get_by_text("You can edit or withdraw this claim")).to_be_visible()
        step(f"{claim_no} submitted with 4 documents; edit window shown")

        c.get_by_role("button", name="Edit claim").click()
        c.fill("#requested_amount", "29000")
        c.click("button:has-text('Save changes')")
        toast(c, "Claim updated")
        step("customer edited the claim inside the 30-minute window")
        api_claim = c.request.get(f"{BASE}/api/claims/{claim_id}/").text().lower()
        assert not any(w in api_claim for w in ("risk_score", "fraud_assess", "indicator", "is_flagged")), "fraud data leaked"
        step("customer API response contains no fraud data")

        print("Malicious upload is refused by the server")
        c.get_by_role("button", name="Upload document").click()
        dlg = c.get_by_role("dialog")
        dlg.locator("select").select_option("DAMAGE_PHOTO")
        renamed = Path("/tmp/e2e-files/fake.jpg"); renamed.write_bytes(b"%PDF-1.4 actually a pdf")
        dlg.locator("input[type=file]").set_input_files(str(renamed))
        dlg.get_by_role("button", name="Upload document").click()
        expect(dlg.get_by_text("does not match its extension")).to_be_visible()
        dlg.get_by_role("button", name="Cancel").click()
        step("JPEG-named PDF rejected by content check")

        print("Claim adjuster")
        j = new()
        login(j, "adjuster@claims.local")
        j.goto(f"{BASE}/staff/claims/{claim_id}")
        expect(j.get_by_text("Fraud assessment")).to_be_visible()
        expect(j.get_by_text(re.compile(r"/ 100"))).to_be_visible()
        step("fraud score from the Flask service is shown to the adjuster")
        j.get_by_role("button", name="Start review").click()
        toast(j, "Review started")
        c.reload()
        expect(c.get_by_role("button", name="Edit claim")).to_have_count(0)
        step("customer editing disabled the moment review started")

        docs = j.locator("li", has=j.get_by_role("button", name="Verify"))
        addr = j.locator("li", has_text="address.pdf")
        addr.get_by_role("button", name="Reject").click()
        j.get_by_role("dialog").locator("textarea").fill("Bill is older than three months.")
        j.get_by_role("dialog").get_by_role("button", name="Reject document").click()
        toast(j, "rejected")
        step("address proof rejected with a reason")

        c.reload()
        c.locator("li", has_text="address.pdf").get_by_role("button", name="Replace").click()
        c.get_by_role("dialog").locator("input[type=file]").set_input_files(f["address.pdf"])
        c.get_by_role("dialog").get_by_role("button", name="Replace document").click()
        toast(c, "Document replaced")
        step("customer replaced the rejected document")

        j.reload()
        j.get_by_role("button", name="Upload document").click()
        j.get_by_role("dialog").locator("select").select_option("REPAIR_ESTIMATE")
        j.get_by_role("dialog").locator("input[type=file]").set_input_files(f["estimate.pdf"])
        j.get_by_role("dialog").get_by_role("button", name="Upload document").click()
        toast(j, "Document uploaded")
        step("adjuster uploaded the repair estimate")
        docs = j.get_by_role("button", name="Verify")
        while docs.count():
            docs.first.click()
            j.wait_for_timeout(400)
        step("all current documents verified")

        j.get_by_role("button", name="Approve").first.click()
        dlg = j.get_by_role("dialog")
        dlg.locator("input[type=number]").fill("26800")
        dlg.locator("textarea").fill("Approved per estimate; fog lamp depreciation applied.")
        dlg.get_by_role("button", name=re.compile("^Approve")).click()
        toast(j, "Claim approved")
        expect(j.get_by_text("₹26,800").first).to_be_visible()
        step("claim approved for ₹26,800 (requested ₹29,000 kept)")

        c.goto(claim_url)
        expect(c.get_by_text("Approved ₹26,800")).to_be_visible()
        c.goto(f"{BASE}/policies")
        card = c.locator("article", has_text=REG)
        expect(card.get_by_text("Partially Claimed")).to_be_visible()
        expect(card.get_by_text("₹26,800").first).to_be_visible()
        step("policy is Partially Claimed with cumulative ₹26,800")
        c.goto(f"{BASE}/notifications")
        expect(c.get_by_text(f"Claim {claim_no} approved")).to_be_visible()
        step("customer notified")

        print("High-risk claim → SIU → adjuster decision")
        n = new()
        login(n, "adjuster@claims.local")
        n.goto(f"{BASE}/staff/claims?status=FRAUD_REVIEW")
        siu = new()
        login(siu, "siu@claims.local")
        siu.goto(f"{BASE}/siu")
        siu.locator("tr", has_text="CLM-2026-000008").click()
        siu.get_by_role("button", name="Take this investigation").click()
        toast(siu, "assigned to you")
        siu.locator("textarea").nth(0).fill("Fire brigade report confirms an electrical short circuit; CCTV shows no tampering.")
        siu.locator("select").select_option("LEGITIMATE")
        siu.get_by_role("button", name="Complete investigation").click()
        toast(siu, "Findings recorded")
        step("SIU recorded findings; claim returned to the adjuster")
        n.goto(f"{BASE}/staff/claims/8")
        expect(n.get_by_text("No fraud indicators confirmed").first).to_be_visible()
        expect(n.get_by_role("button", name="Escalate to SIU")).to_be_visible()
        expect(n.get_by_role("button", name="Reject").first).to_be_visible()
        step("adjuster sees SIU findings and can decide")

        print("Security checks in the browser")
        c.goto(f"{BASE}/staff/claims/{claim_id}")
        expect(c.get_by_text("You don't have access to this page")).to_be_visible()
        r = c.request.get(f"{BASE}/api/fraud/assessments/")
        assert r.status == 403, r.status
        r = c.request.get(f"{BASE}/api/claims/8/")
        assert r.status == 404, r.status
        step("customer blocked from staff pages, fraud API (403) and other customers' claims (404)")
        r = a.request.post(f"{BASE}/api/claims/{claim_id}/approve/", data={"approved_amount": "1"},
                           headers={"X-CSRFToken": next(x["value"] for x in a.context.cookies() if x["name"] == "csrftoken")})
        assert r.status == 403, r.status
        step("administrator cannot approve claims (403)")

        print("Administrator analytics")
        a.goto(f"{BASE}/admin")
        expect(a.get_by_text("Claims paid out")).to_be_visible()
        a.goto(f"{BASE}/admin/reports")
        a.locator("select").first.select_option("ACCIDENT")   # claim type filter
        expect(a.get_by_text(claim_no)).to_be_visible()
        with a.expect_download() as dl:
            a.get_by_role("button", name="Excel").click()
        assert dl.value.suggested_filename.endswith(".xlsx")
        a.goto(f"{BASE}/admin/audit")
        a.fill("input[placeholder^='Action']", "CLAIM_APPROVED")
        expect(a.get_by_text("adjuster@claims.local").first).to_be_visible()
        step("dashboard, filtered report, Excel export and audit trail all reflect the new claim")
        browser.close()
    print("\nEnd-to-end scenario passed.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--django-log", required=True, type=Path)
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    run(args.django_log, args.headed)
