#!/usr/bin/env python3
"""
Xiaomi Account Registration — 100% Browserless (v4)
Based on captured browser traffic analysis.
"""

import json
import time
import uuid
import secrets
import base64
import re
import os
import imaplib
import email as email_lib
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode, quote, parse_qs, urlparse

from dotenv import load_dotenv
from curl_cffi import requests as cffi_requests
from Crypto.Cipher import AES
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5
from Crypto.Util.Padding import pad

__all__ = ["register_xiaomi_account"]

# ─── PATHS ────────────────────────────────────────────────────────────────────
_SCRIPT_DIR = Path(__file__).parent
_PAYLOAD_TEMPLATE = _SCRIPT_DIR / "capture" / "xiaomi" / "payload_template.json"

# ─── CONSTANTS ────────────────────────────────────────────────────────────────
CAPTCHA_SITE_KEY = "6LeBM0ocAAAAAEwYcFUjtxpVbs-0rnbSVXBBXmh4"
CAPTCHA_PARAM_K = "8027422fb0eb42fbac1b521ec4a7961f"
REGISTER_URL = "https://global.account.xiaomi.com/fe/service/register?_locale=en_US&_uRegion=ID"
IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
AES_IV = b"0102030405060708"

# Captcha RSA key (2048-bit)
CAPTCHA_RSA_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEArxfNLkuAQ/BYHzkzVwtu
g+0abmYRBVCEScSzGxJIOsfxVzcuqaKO87H2o2wBcacD3bRHhMjTkhSEqxPjQ/FE
XuJ1cdbmr3+b3EQR6wf/cYcMx2468/QyVoQ7BADLSPecQhtgGOllkC+cLYN6Md34
Uii6U+VJf0p0q/saxUTZvhR2ka9fqJ4+6C6cOghIecjMYQNHIaNW+eSKunfFsXVU
+QfMD0q2EM9wo20aLnos24yDzRjh9HJc6xfr37jRlv1/boG/EABMG9FnTm35xWrV
R0nw3cpYF7GZg13QicS/ZwEsSd4HyboAruMxJBPvK3Jdr4ZS23bpN0cavWOJsBqZ
VwIDAQAB
-----END PUBLIC KEY-----"""

# ─── ANSI HELPERS ─────────────────────────────────────────────────────────────
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_CYAN = "\033[36m"
_BLUE = "\033[34m"

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


# ─── CRYPTO HELPERS ───────────────────────────────────────────────────────────

_KEY_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*"


def _random_aes_key(length: int = 16) -> str:
    return "".join(secrets.choice(_KEY_CHARS) for _ in range(length))


def _aes_encrypt(plaintext: str, aes_key: str) -> str:
    """AES-128-CBC with PKCS7 padding, returns base64 string."""
    cipher = AES.new(aes_key.encode("utf-8"), AES.MODE_CBC, AES_IV)
    ct = cipher.encrypt(pad(plaintext.encode("utf-8"), AES.block_size))
    return base64.b64encode(ct).decode("utf-8")


def _rsa_encrypt(data_b64: str, pem: str) -> str:
    """RSA PKCS1v15 encrypt base64-encoded string, returns base64 string."""
    key = RSA.import_key(pem)
    cipher = PKCS1_v1_5.new(key)
    ct = cipher.encrypt(data_b64.encode("utf-8"))
    return base64.b64encode(ct).decode("utf-8")


def _encrypt_captcha_payload(payload: dict) -> tuple[str, str]:
    """Encrypt captcha fingerprint payload. Returns (s, d)."""
    aes_key = _random_aes_key()
    payload_json = json.dumps(payload, separators=(",", ":"))
    d = _aes_encrypt(payload_json, aes_key)
    s = _rsa_encrypt(base64.b64encode(aes_key.encode()).decode(), CAPTCHA_RSA_PEM)
    return s, d


def _build_eui(fields: dict) -> tuple[str, dict]:
    """Build EUI header value using eui_encrypt module. Returns (eui, encrypted_params)."""
    from eui_encrypt import encrypt_form_fields
    result = encrypt_form_fields(fields)
    return result["EUI"], result["encryptedParams"]


def _mask_email(email: str) -> str:
    """Mask email for display: ste***@gmail.com"""
    local, _, domain = email.partition("@")
    if len(local) > 3:
        return local[:3] + "***@" + domain
    return "***@" + domain


# ─── CAPTCHA SOLVER HELPERS ───────────────────────────────────────────────────

def _solve_capsolver(session: cffi_requests.Session, e_token: str, capsolver_key: str) -> str:
    """Solve reCAPTCHA Enterprise via CapSolver. Returns gRecaptchaResponse."""
    _info("Trying CapSolver...")

    # Check balance
    resp = session.post("https://api.capsolver.com/getBalance", json={"clientKey": capsolver_key})
    bal = resp.json()
    if bal.get("errorId", 0) != 0:
        raise RuntimeError(f"CapSolver balance check failed: {bal}")
    _info(f"CapSolver balance: ${bal.get('balance', '?')}")

    create_body = {
        "clientKey": capsolver_key,
        "task": {
            "type": "ReCaptchaV2EnterpriseTaskProxyLess",
            "websiteURL": REGISTER_URL,
            "websiteKey": CAPTCHA_SITE_KEY,
            "enterprisePayload": {"s": e_token},
        },
    }
    resp = session.post("https://api.capsolver.com/createTask", json=create_body)
    result = resp.json()

    if result.get("errorId", 0) != 0:
        _err(f"CapSolver createTask error: {result.get('errorDescription', result)}")
        raise RuntimeError(f"CapSolver createTask error: {result}")

    task_id = result["taskId"]
    _info(f"CapSolver task #{task_id} submitted")

    for attempt in range(60):
        time.sleep(3)
        poll_body = {"clientKey": capsolver_key, "taskId": task_id}
        resp = session.post("https://api.capsolver.com/getTaskResult", json=poll_body)
        result = resp.json()
        _info(f"CapSolver polling... (attempt {attempt + 1}/60)")

        if result.get("status") == "ready":
            g_recaptcha = result["solution"]["gRecaptchaResponse"]
            _ok("CapSolver solved ✓")
            return g_recaptcha
        elif result.get("errorId", 0) != 0:
            err_code = result.get("errorDescription", result.get("errorId"))
            _err(f"CapSolver: {err_code}")
            raise RuntimeError(f"CapSolver error: {result}")

    raise TimeoutError("CapSolver timed out after 300s")


def _solve_2captcha(session: cffi_requests.Session, e_token: str, twocaptcha_key: str) -> str:
    """Solve reCAPTCHA Enterprise via 2Captcha. Returns gRecaptchaResponse."""
    _info("Falling back to 2Captcha...")

    create_body = {
        "clientKey": twocaptcha_key,
        "task": {
            "type": "RecaptchaV2EnterpriseTaskProxyless",
            "websiteURL": REGISTER_URL,
            "websiteKey": CAPTCHA_SITE_KEY,
            "enterprisePayload": {"s": e_token},
        },
    }
    resp = session.post("https://api.2captcha.com/createTask", json=create_body)
    result = resp.json()

    if result.get("errorId", 0) != 0:
        _err(f"2Captcha createTask error: {result.get('errorDescription', result)}")
        raise RuntimeError(f"2Captcha createTask error: {result}")

    task_id = result["taskId"]
    _info(f"2Captcha task #{task_id} submitted")

    for attempt in range(60):
        time.sleep(5)
        poll_body = {"clientKey": twocaptcha_key, "taskId": task_id}
        resp = session.post("https://api.2captcha.com/getTaskResult", json=poll_body)
        result = resp.json()
        _info(f"2Captcha polling... (attempt {attempt + 1}/60)")

        if result.get("status") == "ready":
            g_recaptcha = result["solution"]["gRecaptchaResponse"]
            _ok("2Captcha solved ✓")
            return g_recaptcha
        elif result.get("errorId", 0) != 0:
            err_code = result.get("errorDescription", result.get("errorId"))
            _err(f"2Captcha: {err_code}")
            raise RuntimeError(f"2Captcha error: {result}")

    raise TimeoutError("2Captcha timed out after 300s")


# ─── STEP FUNCTIONS ───────────────────────────────────────────────────────────

def _step1_warmup(session: cffi_requests.Session) -> None:
    """GET register page to collect cookies."""
    _step(1, "⛔", "Warming up register page...")
    resp = session.get(REGISTER_URL)
    _ok(f"{resp.status_code} OK")
    if resp.status_code != 200:
        raise RuntimeError(f"Warmup failed: HTTP {resp.status_code}")


def _step2_captcha_data(session: cffi_requests.Session) -> str:
    """POST captcha/v2/data with encrypted fingerprint. Returns e_token."""
    _step(2, "🔑", "Generating captcha fingerprint...")

    with open(_PAYLOAD_TEMPLATE) as f:
        payload = json.load(f)

    now_ms = int(time.time() * 1000)
    payload["startTs"] = now_ms
    payload["endTs"] = now_ms + secrets.randbelow(1000) + 500
    payload["env"]["p11"] = now_ms
    payload["nonce"]["t"] = int(now_ms / 1000)
    payload["nonce"]["r"] = secrets.randbelow(9000000000) + 1000000000
    payload["env"]["p33"] = []  # No webdriver

    s, d = _encrypt_captcha_payload(payload)

    ts = int(time.time() * 1000)
    url = f"https://verify.sec.xiaomi.com/captcha/v2/data?k={CAPTCHA_PARAM_K}&locale=en_US&_t={ts}"
    body = f"s={quote(s)}&d={quote(d)}&a=register"

    resp = session.post(url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    data = resp.json()

    if data.get("code") != 0:
        raise RuntimeError(f"captcha/v2/data failed: {data}")

    e_token = parse_qs(urlparse(data["data"]["url"]).query)["e"][0]
    _ok(f"e_token: {e_token[:40]}...")
    return e_token


def _step3_solve_captcha(
    session: cffi_requests.Session,
    e_token: str,
    capsolver_key: str = "",
    twocaptcha_key: str = "",
) -> str:
    """Solve reCAPTCHA Enterprise. CapSolver primary, 2Captcha fallback. Returns gRecaptchaResponse."""
    _step(3, "🧩", "Solving reCAPTCHA Enterprise...")

    errors = []

    # Try CapSolver first
    if capsolver_key:
        try:
            return _solve_capsolver(session, e_token, capsolver_key)
        except (RuntimeError, TimeoutError) as e:
            _warn(f"CapSolver failed: {e}")
            errors.append(f"CapSolver: {e}")

    # Fallback to 2Captcha
    if twocaptcha_key:
        try:
            return _solve_2captcha(session, e_token, twocaptcha_key)
        except (RuntimeError, TimeoutError) as e:
            _warn(f"2Captcha failed: {e}")
            errors.append(f"2Captcha: {e}")

    raise RuntimeError(f"All captcha solvers failed: {'; '.join(errors)}")


def _step4_recaptcha_verify(session: cffi_requests.Session, e_token: str, g_recaptcha: str) -> str:
    """POST captcha/v2/recaptcha/verify. Returns vToken."""
    _step(4, "✅", "Verifying captcha...")

    ts = int(time.time() * 1000)
    url = f"https://verify.sec.xiaomi.com/captcha/v2/recaptcha/verify?k={CAPTCHA_PARAM_K}&locale=en_US&_t={ts}"
    body = f"e={quote(e_token)}&g={quote(g_recaptcha)}&type=4"

    resp = session.post(url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    data = resp.json()

    if data.get("code") != 0 or not data.get("data", {}).get("result"):
        raise RuntimeError(f"recaptcha verify failed: {data}")

    vtoken = data["data"]["token"]
    _ok(f"vToken obtained")
    return vtoken


def _step5_encrypt_credentials(email: str, password: str) -> tuple[str, str, str]:
    """Encrypt email+password for EUI. Returns (eui, enc_email, enc_password)."""
    _step(5, "🔒", "Encrypting credentials (EUI)...")

    eui, enc_params = _build_eui({"email": email, "password": password})
    enc_email = enc_params["email"]
    enc_password = enc_params["password"]

    _ok(f"EUI: {eui[:50]}...")
    return eui, enc_email, enc_password


def _step6_send_email_reg_ticket(
    session: cffi_requests.Session,
    register_url: str,
    vtoken: str,
    eui: str,
    enc_email: str,
    enc_password: str,
    email_masked: str,
) -> dict:
    """POST sendEmailRegTicket."""
    _step(6, "📧", "Sending registration ticket...")

    device_id = f"wb_{uuid.uuid4()}"
    url = "https://global.account.xiaomi.com/pass/sendEmailRegTicket"

    headers = {
        "eui": eui,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": register_url,
        "Origin": "https://global.account.xiaomi.com",
    }

    # Set cookies on session
    session.cookies.set("vToken", vtoken, domain="global.account.xiaomi.com")
    session.cookies.set("vAction", "register", domain="global.account.xiaomi.com")
    session.cookies.set("deviceId", device_id, domain="global.account.xiaomi.com")

    body = urlencode({
        "email": enc_email,
        "password": enc_password,
        "region": "ID",
        "sid": "",
        "icode": "",
    })

    resp = session.post(url, data=body, headers=headers)
    text = resp.text
    if text.startswith("&&&START&&&"):
        text = text[len("&&&START&&&"):]
    data = json.loads(text)

    if data.get("code") != 0:
        raise RuntimeError(f"sendEmailRegTicket failed: {data}")

    _ok(f"Code sent to {email_masked}")
    return data


def _step7_read_imap_code(email: str, imap_user: str, imap_pass: str, timeout: int = 120) -> str:
    """Read 6-digit verification code from Gmail IMAP."""
    _step(7, "📬", "Reading verification code from IMAP...")
    _info(f"Waiting for email... ({timeout}s timeout)")

    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
            imap.login(imap_user, imap_pass)
            imap.select("INBOX")

            try:
                _, data = imap.search(None, '(UNSEEN FROM "noreply@notice.xiaomi.com")')
                raw_ids = data[0]
                if not raw_ids or raw_ids == b"":
                    imap.logout()
                    time.sleep(5)
                    continue
                msg_ids = raw_ids.split()
            except Exception:
                try:
                    imap.logout()
                except Exception:
                    pass
                time.sleep(5)
                continue

            for msg_id in reversed(msg_ids[-20:]):
                _, msg_data = imap.fetch(msg_id, "(RFC822)")
                raw = msg_data[0][1]
                msg = email_lib.message_from_bytes(raw)

                to_addr = msg.get("To", "").lower()
                if email.lower() not in to_addr:
                    continue

                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        ct = part.get_content_type()
                        if ct in ("text/plain", "text/html"):
                            payload = part.get_payload(decode=True)
                            if payload:
                                body = payload.decode("utf-8", errors="replace")
                                break
                else:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        body = payload.decode("utf-8", errors="replace")

                body = body.replace("=\r\n", "")

                match = re.search(r"verification code is[:\s]*(\d{6})", body, re.IGNORECASE)
                if match:
                    code = match.group(1)
                    _ok(f"Code: {code}")
                    try:
                        imap.logout()
                    except Exception:
                        pass
                    return code

            try:
                imap.logout()
            except Exception:
                pass
        except Exception as e:
            _warn(f"IMAP error: {e}")

        time.sleep(5)

    raise TimeoutError("Did not receive verification code within timeout")


def _step8_verify_email_reg_ticket(
    session: cffi_requests.Session,
    vtoken: str,
    code: str,
    email: str,
    password: str,
) -> dict:
    """POST verifyEmailRegTicket — creates the account."""
    _step(8, "🎯", "Verifying & creating account...")

    eui, enc_params = _build_eui({"email": email, "password": password})
    enc_email = enc_params["email"]
    enc_password = enc_params["password"]

    device_fp = secrets.token_hex(16)

    url = "https://global.account.xiaomi.com/pass/verifyEmailRegTicket"

    headers = {
        "eui": eui,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
    }

    body = (
        f"ticket={code}"
        f"&region=ID"
        f"&email={quote(enc_email, safe='')}"
        f"&env=web"
        f"&qs=%253Fsid%253Dpassport"
        f"&isAcceptLicense=true"
        f"&sid="
        f"&password={quote(enc_password, safe='')}"
        f"&policyName=globalmiaccount"
        f"&callback="
        f"&deviceFingerprint={device_fp}"
    )

    resp = session.post(url, data=body, headers=headers)
    text = resp.text
    if text.startswith("&&&START&&&"):
        text = text[len("&&&START&&&"):]
    data = json.loads(text)

    if data.get("code") != 0:
        _err(f"Verification failed: code={data.get('code')}, desc={data.get('description', 'unknown')}")
        raise RuntimeError(f"verifyEmailRegTicket failed: {data}")

    # Extract userId from response
    user_id = data.get("data", {}).get("userId", "unknown")
    _ok(f"Account created! userId: {user_id}")
    return data


def _pre_cleanup(imap_user: str, imap_pass: str) -> None:
    """Mark all existing Xiaomi emails as read to avoid stale codes."""
    try:
        imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        imap.login(imap_user, imap_pass)
        imap.select("INBOX")
        _, data = imap.search(None, '(UNSEEN FROM "noreply@notice.xiaomi.com")')
        if data[0] and data[0] != b"":
            msg_ids = data[0].split()
            for mid in msg_ids:
                imap.store(mid, "+FLAGS", "\\Seen")
            _info(f"Marked {len(msg_ids)} old emails as read")
        else:
            _info("No stale emails found")
        imap.logout()
    except Exception as e:
        _warn(f"Cleanup error: {e}")


# ─── PUBLIC API ───────────────────────────────────────────────────────────────

def register_xiaomi_account(
    email: str,
    password: str,
    session: Optional[cffi_requests.Session] = None,
) -> dict:
    """
    Register a Xiaomi account end-to-end.

    Args:
        email: Full email address for the account
        password: Password for the account
        session: Optional pre-configured session (creates fresh one if None)

    Returns:
        dict with keys: email, password, userId, passToken, cUserId, created_at

    Raises:
        RuntimeError: If any registration step fails
        TimeoutError: If captcha solve or email verification times out
    """
    load_dotenv()

    capsolver_key = os.environ.get("CAPSOLVER_API_KEY", "")
    twocaptcha_key = os.environ.get("TWOCAPTCHA_API_KEY", "")
    imap_user = os.environ.get("IMAP_USER")
    imap_pass = os.environ.get("IMAP_PASS")

    if not capsolver_key and not twocaptcha_key:
        raise ValueError("Missing environment variables: CAPSOLVER_API_KEY or TWOCAPTCHA_API_KEY (at least one required)")
    missing = []
    if not imap_user:
        missing.append("IMAP_USER")
    if not imap_pass:
        missing.append("IMAP_PASS")
    if missing:
        raise ValueError(f"Missing environment variables: {', '.join(missing)}")

    # Create fresh session if none provided
    own_session = session is None
    if own_session:
        session = cffi_requests.Session(impersonate="chrome124")

    email_masked = _mask_email(email)

    # ─── Banner ────────────────────────────────────────────────────────────
    _banner(f"🔐 {_BOLD}Xiaomi Account Registration{_RESET}")

    try:
        # Step 1: Warm-up
        _step1_warmup(session)

        # Pre-cleanup
        _pre_cleanup(imap_user, imap_pass)

        # Steps 2-4 with retry loop (up to 4 attempts)
        vtoken = None
        max_attempts = 4
        for attempt in range(max_attempts):
            try:
                e_token = _step2_captcha_data(session)
                g_recaptcha = _step3_solve_captcha(session, e_token, capsolver_key, twocaptcha_key)
                vtoken = _step4_recaptcha_verify(session, e_token, g_recaptcha)
                break
            except RuntimeError as e:
                err_msg = str(e)
                if "captcha" in err_msg.lower() or "recaptcha" in err_msg.lower():
                    _err(f"{err_msg[:80]} — retrying ({attempt + 1}/{max_attempts})")
                else:
                    _err(f"{err_msg[:80]}")
                if attempt < max_attempts - 1:
                    time.sleep(2)
                else:
                    raise

        # Step 5: Encrypt credentials
        eui, enc_email, enc_password = _step5_encrypt_credentials(email, password)

        # Step 6: Send registration ticket
        _step6_send_email_reg_ticket(session, REGISTER_URL, vtoken, eui, enc_email, enc_password, email_masked)

        # Step 7: Read verification code
        code = _step7_read_imap_code(email, imap_user, imap_pass)

        # Step 8: Verify and create account
        result = _step8_verify_email_reg_ticket(session, vtoken, code, email, password)

        # Extract cookies
        user_id = result.get("data", {}).get("userId", "")
        pass_token = session.cookies.get("passToken", domain="account.xiaomi.com") or session.cookies.get("passToken", "")
        c_user_id = session.cookies.get("cUserId", domain="account.xiaomi.com") or session.cookies.get("cUserId", "")

        account = {
            "email": email,
            "password": password,
            "userId": str(user_id),
            "passToken": pass_token or "",
            "cUserId": c_user_id or "",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        # ─── Success Banner ────────────────────────────────────────────────
        print(f"\n{_BOLD}{_GREEN}{_SEP}{_RESET}")
        print(f" ✨ {_BOLD}Registration Complete{_RESET}")
        print(f"{_BOLD}{_GREEN}{_SEP}{_RESET}")
        print(f"    {_DIM}Email:{_RESET}     {email}")
        print(f"    {_DIM}Password:{_RESET}  {password}")
        print(f"    {_DIM}UserId:{_RESET}    {user_id}")
        if pass_token:
            print(f"    {_DIM}passToken:{_RESET} {pass_token[:30]}... (truncated)")
        print(f"{_BOLD}{_GREEN}{_SEP}{_RESET}\n")

        return account

    finally:
        if own_session:
            session.close()


# ─── CLI MODE ─────────────────────────────────────────────────────────────────

def main() -> None:
    load_dotenv()

    email_prefix = os.environ.get("EMAIL_PREFIX", "stevenharis78")
    default_password = os.environ.get("DEFAULT_PASSWORD", "XiaomiGrace2026!")

    timestamp = int(time.time())
    email = os.environ.get("EMAIL") or f"{email_prefix}+mi{timestamp}@gmail.com"
    password = os.environ.get("PASSWORD") or default_password

    try:
        account = register_xiaomi_account(email, password)
    except (RuntimeError, TimeoutError, ValueError) as e:
        print(f"\n {_RED}❌ Registration failed: {e}{_RESET}\n")
        return

    out_path = _SCRIPT_DIR / "xiaomi_account.json"
    with open(out_path, "w") as f:
        json.dump(account, f, indent=2)
    _info(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
