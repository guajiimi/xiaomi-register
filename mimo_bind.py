#!/usr/bin/env python3
"""
Post-registration flow for Xiaomi MiMo platform:
  1. SSO Login (cookie-based redirect chain)
  2. Confirm agreement
  3. Bind referral code
"""

import json
import time
import os
from urllib.parse import quote, urlencode
from typing import Optional

from dotenv import load_dotenv
from curl_cffi import requests as cffi_requests

__all__ = ["bind_referral_after_registration"]

# ─── ANSI HELPERS ─────────────────────────────────────────────────────────────
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_CYAN = "\033[36m"

_SEP = "━" * 60


def _banner(text: str) -> None:
    print(f"\n{_BOLD}{_CYAN}{_SEP}{_RESET}")
    print(f" {text}")
    print(f"{_BOLD}{_CYAN}{_SEP}{_RESET}")


def _step(n: int, icon: str, text: str) -> None:
    print(f"\n {icon} {_BOLD}Step {n}  {text}{_RESET}")


def _info(text: str) -> None:
    print(f"    {_DIM}↳ {_RESET}{text}")


def _ok(text: str) -> None:
    print(f"    {_GREEN}↳ {_RESET}{text}")


def _err(text: str) -> None:
    print(f"    {_RED}↳ {_RESET}{text}")


def _warn(text: str) -> None:
    print(f"    {_YELLOW}↳ {_RESET}{text}")


# ─── SSO LOGIN FLOW ───────────────────────────────────────────────────────────

def _sso_login(session: cffi_requests.Session) -> None:
    """
    Perform SSO login from account.xiaomi.com to platform.xiaomimimo.com.
    Uses passToken/cUserId cookies from registration to authenticate.

    CRITICAL: Must use allow_redirects=False and follow redirects manually.
    curl_cffi allow_redirects=True loses intermediate cookies!
    """
    _step(1, "🔗", "SSO Login to MiMo Platform...")

    # Step 1a: Get login URL from genLoginUrl
    _info("Requesting genLoginUrl...")
    resp = session.get(
        "https://platform.xiaomimimo.com/api/v1/genLoginUrl",
        params={"currentPath": "/overview"},
        allow_redirects=False,
    )
    data = resp.json()
    login_url = data.get("loginUrl") or data.get("data", {}).get("loginUrl", "")
    if not login_url:
        # Try to extract from redirect
        if resp.status_code in (301, 302) and resp.headers.get("location"):
            login_url = resp.headers["location"]
        else:
            raise RuntimeError(f"genLoginUrl failed: {data}")

    _info(f"Login URL: {login_url[:80]}...")

    # Step 1b: Follow login URL → account.xiaomi.com pass serviceLogin
    _info("Following login redirect chain...")
    resp = session.get(login_url, allow_redirects=False)
    _info(f"Status: {resp.status_code}")

    # Follow redirects manually (up to 10 hops)
    max_redirects = 10
    for i in range(max_redirects):
        if resp.status_code not in (301, 302, 303, 307, 308):
            break

        location = resp.headers.get("location", "")
        if not location:
            break

        _info(f"Redirect {i + 1}: {location[:80]}...")
        resp = session.get(location, allow_redirects=False)
        _info(f"Status: {resp.status_code}")
    else:
        _warn("Max redirects reached")

    _ok(f"SSO redirect chain complete (final: {resp.status_code})")

    # Step 1c: Refresh cookies — call genLoginUrl again and follow redirect
    _info("Refreshing cookies (second genLoginUrl call)...")
    resp = session.get(
        "https://platform.xiaomimimo.com/api/v1/genLoginUrl",
        params={"currentPath": "/overview"},
        allow_redirects=False,
    )
    data = resp.json()
    login_url2 = data.get("loginUrl") or data.get("data", {}).get("loginUrl", "")
    if login_url2:
        resp = session.get(login_url2, allow_redirects=False)
        for i in range(max_redirects):
            if resp.status_code not in (301, 302, 303, 307, 308):
                break
            location = resp.headers.get("location", "")
            if not location:
                break
            resp = session.get(location, allow_redirects=False)
        _ok("Cookie refresh complete")

    # Verify we have the platform cookies
    svc_token = session.cookies.get("api-platform_serviceToken")
    ph = session.cookies.get("api-platform_ph")
    if svc_token:
        _ok(f"api-platform_serviceToken: {svc_token[:30]}...")
    else:
        _warn("api-platform_serviceToken not found — SSO may have failed")
    if ph:
        _ok(f"api-platform_ph: {ph[:30]}...")
    else:
        _warn("api-platform_ph not found — POST requests may fail")


def _confirm_agreement(session: cffi_requests.Session) -> None:
    """Confirm user agreement on MiMo platform."""
    _step(2, "📜", "Confirming agreement...")

    resp = session.get("https://platform.xiaomimimo.com/api/v1/agreement")
    data = resp.json()

    if data.get("code") == 0:
        _ok("Agreement confirmed")
    else:
        _warn(f"Agreement response: {data}")
        # Not fatal — may already be confirmed


def _check_eligibility(session: cffi_requests.Session) -> bool:
    """Check if account is eligible to bind a referral code."""
    _info("Checking referral eligibility...")

    resp = session.get("https://platform.xiaomimimo.com/api/v1/invitation/eligible")
    data = resp.json()

    can_bind = data.get("data", {}).get("canBind", False)
    if can_bind:
        _ok("Account is eligible to bind referral code")
    else:
        _warn(f"Not eligible: {data}")
    return can_bind


def _bind_referral(session: cffi_requests.Session, invite_code: str) -> bool:
    """
    Bind referral code to the account.

    CRITICAL: api-platform_ph cookie value MUST be passed as URL query parameter
    for POST requests! Without this, POST returns 401.

    Error codes:
        0     = success
        400906 = already bound (treat as success)
        400904 = cannot use own referral code
    """
    _step(3, "🎁", f"Binding referral code: {invite_code}...")

    # Get ph cookie value and URL-encode it for query param
    ph = session.cookies.get("api-platform_ph", "")
    if not ph:
        _err("api-platform_ph cookie not found — cannot bind referral")
        return False

    ph_encoded = quote(ph, safe="")

    url = f"https://platform.xiaomimimo.com/api/v1/invitation/bind?api-platform_ph={ph_encoded}"
    body = {"inviteCode": invite_code}

    resp = session.post(
        url,
        json=body,
        headers={"Content-Type": "application/json"},
    )
    data = resp.json()

    code = data.get("code", -1)
    if code == 0:
        _ok("Referral code bound successfully!")
        return True
    elif code == 400906:
        _warn("Referral code already bound (treating as success)")
        return True
    elif code == 400904:
        _err("Cannot bind own referral code")
        return False
    else:
        _err(f"Bind failed: {data}")
        return False


# ─── PUBLIC API ───────────────────────────────────────────────────────────────

def bind_referral_after_registration(
    email: str,
    password: str,
    pass_token: str = "",
    c_user_id: str = "",
    invite_code: str = "",
    session: Optional[cffi_requests.Session] = None,
) -> dict:
    """
    Post-registration flow: SSO login → confirm agreement → bind referral.

    Args:
        email: Account email
        password: Account password
        pass_token: passToken cookie from registration (optional if session has it)
        c_user_id: cUserId cookie from registration (optional if session has it)
        invite_code: Referral/invitation code to bind
        session: Optional pre-configured session with cookies

    Returns:
        dict with keys: sso_ok, agreement_ok, eligible, bound, invite_code
    """
    load_dotenv()

    if not invite_code:
        invite_code = os.environ.get("REFERRAL_CODE", "")
    if not invite_code:
        _warn("No referral code provided — skipping bind flow")
        return {"sso_ok": False, "agreement_ok": False, "eligible": False, "bound": False, "invite_code": ""}

    # Create fresh session if none provided
    own_session = session is None
    if own_session:
        session = cffi_requests.Session(impersonate="chrome124")

    # Set Xiaomi account cookies if provided and not already present
    if pass_token and not session.cookies.get("passToken"):
        session.cookies.set("passToken", pass_token, domain="account.xiaomi.com")
    if c_user_id and not session.cookies.get("cUserId"):
        session.cookies.set("cUserId", c_user_id, domain="account.xiaomi.com")

    _banner(f"🎁 {_BOLD}Post-Registration: Referral Bind{_RESET}")
    _info(f"Email: {email}")
    _info(f"Invite code: {invite_code}")

    result = {
        "sso_ok": False,
        "agreement_ok": False,
        "eligible": False,
        "bound": False,
        "invite_code": invite_code,
    }

    try:
        # Step 1: SSO Login
        try:
            _sso_login(session)
            result["sso_ok"] = True
        except Exception as e:
            _err(f"SSO login failed: {e}")
            return result

        # Step 2: Confirm Agreement
        try:
            _confirm_agreement(session)
            result["agreement_ok"] = True
        except Exception as e:
            _warn(f"Agreement confirm failed: {e}")

        # Step 3: Check eligibility and bind
        try:
            eligible = _check_eligibility(session)
            result["eligible"] = eligible

            if eligible:
                bound = _bind_referral(session, invite_code)
                result["bound"] = bound
            else:
                _warn("Not eligible for referral bind — skipping")
        except Exception as e:
            _err(f"Referral bind failed: {e}")

    finally:
        if own_session:
            session.close()

    # Summary
    if result["bound"]:
        _ok(f"✅ Referral {invite_code} bound to {email}")
    elif result["sso_ok"]:
        _warn(f"⚠️ SSO succeeded but referral bind incomplete")

    return result


# ─── CLI MODE ─────────────────────────────────────────────────────────────────

def main() -> None:
    """CLI entry point for testing the bind flow standalone."""
    import argparse

    parser = argparse.ArgumentParser(description="Bind referral code to existing Xiaomi account")
    parser.add_argument("--email", required=True, help="Account email")
    parser.add_argument("--password", required=True, help="Account password")
    parser.add_argument("--pass-token", default="", help="passToken cookie")
    parser.add_argument("--c-user-id", default="", help="cUserId cookie")
    parser.add_argument("--invite-code", default="", help="Referral code (or set REFERRAL_CODE env)")
    args = parser.parse_args()

    result = bind_referral_after_registration(
        email=args.email,
        password=args.password,
        pass_token=args.pass_token,
        c_user_id=args.c_user_id,
        invite_code=args.invite_code,
    )

    print(f"\nResult: {json.dumps(result, indent=2)}")


if __name__ == "__main__":
    main()
