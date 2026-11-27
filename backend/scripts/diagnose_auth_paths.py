import getpass
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.sync_api import sync_playwright

from app.core.config import settings
from app.core.security import create_supabase_anon_client

ADMIN_EMAIL = "snehachavan0923@gmail.com"
EXPECTED_AUTH_ID = "8bf32e67-851c-41e0-898e-edaf58874bfb"
FASTAPI_LOGIN_URL = "http://127.0.0.1:8000/api/v1/auth/login"
FRONTEND_LOGIN_PAGE = "http://localhost:5173/login"


def main():
    print("=" * 70)
    print("PYQVERSE 3-PATH AUTHENTICATION ISOLATION TOOL")
    print(f"Target Administrator Email: {ADMIN_EMAIL}")
    print(f"Expected Supabase Auth UUID: {EXPECTED_AUTH_ID}")
    print("=" * 70)

    # 1. Collect password once via hidden terminal input
    password = os.getenv("DIAGNOSTIC_ADMIN_PASSWORD") or getpass.getpass("Enter administrator password: ")
    if not password:
        print("Error: Password cannot be empty.", file=sys.stderr)
        return 1

    # Compute non-sensitive ephemeral metrics
    pw_len = len(password)
    pw_fp = hashlib.sha256(password.encode("utf-8")).hexdigest()[:8]
    anon_key_fp = hashlib.sha256(settings.SUPABASE_ANON_KEY.encode("utf-8")).hexdigest()[:8]

    print(f"\n[Configuration & Input Metrics]")
    print(f"  Staging Supabase URL:   {settings.SUPABASE_URL}")
    print(f"  Anon-Key Fingerprint:   {anon_key_fp}")
    print(f"  Input Password Length:  {pw_len}")
    print(f"  Input Password Hash FP: {pw_fp}")

    results = {}

    # -------------------------------------------------------------------------
    # PATH A: Direct Supabase Anon-Client sign_in_with_password
    # -------------------------------------------------------------------------
    print("\n" + "-" * 70)
    print("PATH A: Direct Supabase Anon-Client (GoTrue SDK)")
    print("-" * 70)
    try:
        anon_client = create_supabase_anon_client()
        client_url = getattr(anon_client, "supabase_url", "unknown")
        print(f"  Client URL:             {client_url}")

        auth_response = anon_client.auth.sign_in_with_password({
            "email": ADMIN_EMAIL,
            "password": password,
        })
        user = getattr(auth_response, "user", None) or auth_response
        user_id = str(getattr(user, "id", None)).lower()
        user_email = str(getattr(user, "email", None)).lower()

        if user_id != EXPECTED_AUTH_ID.lower():
            results["path_a"] = (False, f"Returned UUID '{user_id}' does not match expected '{EXPECTED_AUTH_ID}'")
            print(f"  Result: FAILED - UUID mismatch ({user_id})")
        elif user_email != ADMIN_EMAIL.lower():
            results["path_a"] = (False, f"Returned email '{user_email}' does not match '{ADMIN_EMAIL}'")
            print(f"  Result: FAILED - Email mismatch ({user_email})")
        else:
            results["path_a"] = (True, f"Auth successful, verified UUID: {user_id}")
            print(f"  Result: SUCCESS (verified Auth UUID: {user_id})")

        # Cleanup verification session
        if hasattr(anon_client.auth, "sign_out"):
            try:
                anon_client.auth.sign_out({"scope": "local"})
            except Exception:
                pass
    except Exception as exc:
        status = getattr(exc, "status", None)
        code = getattr(exc, "code", None)
        err_type = type(exc).__name__
        results["path_a"] = (False, f"GoTrue rejected credentials: status={status}, code={code}, error={err_type}")
        print(f"  Result: FAILED - status={status}, code={code}, error={err_type}")

    # -------------------------------------------------------------------------
    # PATH B: FastAPI /api/v1/auth/login via HTTP
    # -------------------------------------------------------------------------
    print("\n" + "-" * 70)
    print(f"PATH B: FastAPI HTTP Endpoint ({FASTAPI_LOGIN_URL})")
    print("-" * 70)
    req_body = json.dumps({"email": ADMIN_EMAIL, "password": password}).encode("utf-8")
    req = urllib.request.Request(
        FASTAPI_LOGIN_URL,
        data=req_body,
        headers={"Content-Type": "application/json", "Origin": "http://localhost:5173"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            returned_role = data.get("profile", {}).get("role")
            returned_user_id = data.get("user", {}).get("id")
            has_token = bool(data.get("access_token"))

            if returned_role == "ADMIN_FACULTY" and has_token:
                results["path_b"] = (True, f"HTTP 200, role: {returned_role}, user_id: {returned_user_id}")
                print(f"  Result: SUCCESS (HTTP {resp.status}, Role: {returned_role}, User ID: {returned_user_id})")
            else:
                results["path_b"] = (False, f"HTTP 200 but unexpected body: role={returned_role}")
                print(f"  Result: FAILED - Incomplete profile payload: role={returned_role}")
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        try:
            err_json = json.loads(err_body)
            detail = err_json.get("detail", err_body)
        except Exception:
            detail = err_body
        results["path_b"] = (False, f"HTTP {exc.code}: {detail}")
        print(f"  Result: FAILED - HTTP {exc.code} ({detail})")
    except Exception as exc:
        results["path_b"] = (False, f"Connection failed: {exc}")
        print(f"  Result: FAILED - Connection error: {exc}")

    # -------------------------------------------------------------------------
    # PATH C: Browser Form Submission (Playwright Chromium)
    # -------------------------------------------------------------------------
    print("\n" + "-" * 70)
    print(f"PATH C: Browser Form Submission ({FRONTEND_LOGIN_PAGE})")
    print("-" * 70)

    intercepted_req = {}
    intercepted_res = {}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            def on_request(r):
                if "/auth/login" in r.url:
                    post_data = r.post_data or ""
                    try:
                        parsed = json.loads(post_data)
                        pw = parsed.get("password", "")
                        intercepted_req["email"] = parsed.get("email")
                        intercepted_req["password_len"] = len(pw)
                        intercepted_req["password_fp"] = hashlib.sha256(pw.encode("utf-8")).hexdigest()[:8]
                        intercepted_req["raw_keys"] = list(parsed.keys())
                    except Exception as e:
                        intercepted_req["parse_error"] = str(e)
                    intercepted_req["headers"] = dict(r.headers)

            def on_response(res):
                if "/auth/login" in res.url:
                    intercepted_res["status"] = res.status
                    try:
                        intercepted_res["data"] = res.json()
                    except Exception:
                        intercepted_res["text"] = res.text()[:200]

            page.on("request", on_request)
            page.on("response", on_response)

            print("  Navigating to frontend login page...")
            page.goto(FRONTEND_LOGIN_PAGE, wait_until="networkidle")

            # Click Password Login tab if present
            pw_tab = page.locator("button[role='tab']:has-text('Password Login')")
            if pw_tab.count() > 0:
                pw_tab.click()

            # Fill form
            email_input = page.locator("input[name='email']")
            pw_input = page.locator("input[name='password']")

            email_input.fill(ADMIN_EMAIL)
            pw_input.fill(password)

            dom_email = email_input.input_value()
            dom_pw_len = len(pw_input.input_value())

            print(f"  DOM email input value:      '{dom_email}'")
            print(f"  DOM password input length:  {dom_pw_len}")

            # Submit
            page.click("button:has-text('Sign in')")

            # Wait for either /admin navigation or network response
            navigated = False
            try:
                page.wait_for_url("**/admin", timeout=8000)
                navigated = True
            except Exception:
                navigated = False

            final_url = page.url
            status = intercepted_res.get("status")
            error_el = page.locator(".form-error, [role='alert']")
            visible_error = error_el.first.text_content() if error_el.count() > 0 and error_el.first.is_visible() else None

            print(f"  Sent Payload Email:         '{intercepted_req.get('email')}'")
            print(f"  Sent Payload PW Length:     {intercepted_req.get('password_len')}")
            print(f"  Sent Payload PW Hash FP:    {intercepted_req.get('password_fp')}")
            print(f"  Response HTTP Status:       {status}")
            print(f"  Final Browser URL:          {final_url}")
            if visible_error:
                print(f"  Visible Page Error:         '{visible_error}'")

            pw_matches = intercepted_req.get("password_fp") == pw_fp
            if not pw_matches:
                results["path_c"] = (False, f"Browser altered password: sent FP {intercepted_req.get('password_fp')} != input FP {pw_fp}")
                print(f"  Result: FAILED - Password altered in browser")
            elif navigated and status == 200:
                results["path_c"] = (True, f"HTTP 200, successfully navigated to {final_url}")
                print(f"  Result: SUCCESS (Navigated to /admin)")
            else:
                detail = intercepted_res.get("data", {}).get("detail") or visible_error or f"HTTP {status}"
                results["path_c"] = (False, f"Login failed (status={status}, detail={detail})")
                print(f"  Result: FAILED - status={status}, detail={detail}")

            browser.close()
    except Exception as exc:
        results["path_c"] = (False, f"Playwright error: {exc}")
        print(f"  Result: FAILED - Playwright error: {exc}")

    # -------------------------------------------------------------------------
    # SUMMARY REPORT
    # -------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("DIAGNOSTIC SUMMARY REPORT")
    print("=" * 70)
    print(f"Input Password Length:     {pw_len}")
    print(f"Input Password Hash FP:    {pw_fp}")
    print(f"Staging Supabase URL:      {settings.SUPABASE_URL}")
    print(f"Staging Anon Key FP:       {anon_key_fp}")
    print("-" * 70)
    print(f"Path A (Direct Supabase):  {'PASS' if results.get('path_a', (False,))[0] else 'FAIL'} -> {results.get('path_a', ('', ''))[1]}")
    print(f"Path B (FastAPI Endpoint): {'PASS' if results.get('path_b', (False,))[0] else 'FAIL'} -> {results.get('path_b', ('', ''))[1]}")
    print(f"Path C (Browser Form):     {'PASS' if results.get('path_c', (False,))[0] else 'FAIL'} -> {results.get('path_c', ('', ''))[1]}")
    print("=" * 70)

    # Root cause classification
    a_pass = results.get("path_a", (False,))[0]
    b_pass = results.get("path_b", (False,))[0]
    c_pass = results.get("path_c", (False,))[0]

    if not a_pass:
        print("\nROOT CAUSE DIAGNOSIS: Path A (Direct Supabase Auth) failed.")
        print("The entered password does not match what Supabase Auth has stored for this user.")
        print("Neither the API nor the browser can log in because GoTrue rejects the credentials at the source.")
    elif a_pass and not b_pass:
        print("\nROOT CAUSE DIAGNOSIS: Path A succeeded, but Path B (FastAPI) failed.")
        print("FastAPI is not reaching Supabase or has a configuration/middleware discrepancy.")
    elif a_pass and b_pass and not c_pass:
        print("\nROOT CAUSE DIAGNOSIS: Path A and Path B succeeded, but Path C (Browser) failed.")
        print("The frontend form/Playwright pipeline altered the password or failed navigation.")
    else:
        print("\nALL THREE PATHS SUCCEEDED!")

    return 0 if (a_pass and b_pass and c_pass) else 1


if __name__ == "__main__":
    raise SystemExit(main())
