#!/usr/bin/env python3
"""
Xiaomi Account Registration Script v3 — 100% Browserless
Based on captured browser traffic analysis.
"""

import json
import time
import uuid
import random
import string
import base64
import re
import imaplib
import email as email_lib
from urllib.parse import urlencode, quote, parse_qs, urlparse

from curl_cffi import requests as cffi_requests
from Crypto.Cipher import AES
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5
from Crypto.Util.Padding import pad

# ─── CONFIG ──────────────────────────────────────────────────────────────────
CAPTCHA_API_KEY = "49c0890fbd8c1506c04b58e53752cf2f"
CAPTCHA_SITE_KEY = "6LeBM0ocAAAAAEwYcFUjtxpVbs-0rnbSVXBBXmh4"
CAPTCHA_PARAM_K = "8027422fb0eb42fbac1b521ec4a7961f"

REGISTER_URL = "https://global.account.xiaomi.com/fe/service/register?_locale=en_US&_uRegion=ID"

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

# EUI RSA key (1024-bit) — from encrypt.cjs
EUI_RSA_PEM = """-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCYEVrK/4Mahiv0pUJgTybx4J9P
5dUT/Y0PuwMbk+gMU+jrZnBiXGv6/hCH1avIhoBcE535F8nJQQN3UavZdFkYidso
XuEnat3+eVTp3FslyhRwIBDF09v4vDhRtxFOT+R7uH7h/mzmyA2/+lfIMWGIrffX
prYizbV76+YQKhoqFQIDAQAB
-----END PUBLIC KEY-----"""

AES_IV = b"0102030405060708"
KEY_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*"

TIMESTAMP = int(time.time())
EMAIL = f"stevenharis78+mi{TIMESTAMP}@gmail.com"
PASSWORD = "XiaomiGrace2026!"

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
IMAP_USER = "stevenharis78@gmail.com"
IMAP_PASS = "wtkx ntyr fwda plit"

SESSION = cffi_requests.Session(impersonate="chrome124")


# ─── CRYPTO HELPERS ──────────────────────────────────────────────────────────

def random_aes_key(length=16):
    return "".join(random.choices(KEY_CHARS, k=length))


def aes_encrypt(plaintext: str, aes_key: str) -> str:
    """AES-128-CBC with PKCS7 padding, returns base64 string."""
    cipher = AES.new(aes_key.encode("utf-8"), AES.MODE_CBC, AES_IV)
    ct = cipher.encrypt(pad(plaintext.encode("utf-8"), AES.block_size))
    return base64.b64encode(ct).decode("utf-8")


def rsa_encrypt(data_b64: str, pem: str) -> str:
    """RSA PKCS1v15 encrypt base64-encoded string, returns base64 string."""
    key = RSA.import_key(pem)
    cipher = PKCS1_v1_5.new(key)
    ct = cipher.encrypt(data_b64.encode("utf-8"))
    return base64.b64encode(ct).decode("utf-8")


def encrypt_captcha_payload(payload: dict) -> tuple:
    """Encrypt captcha fingerprint payload. Returns (s, d)."""
    aes_key = random_aes_key()
    payload_json = json.dumps(payload, separators=(",", ":"))
    d = aes_encrypt(payload_json, aes_key)
    s = rsa_encrypt(base64.b64encode(aes_key.encode()).decode(), CAPTCHA_RSA_PEM)
    return s, d


def build_eui(fields: dict) -> tuple:
    """Build EUI header value using pure Python. Returns (eui, encrypted_params)."""
    import sys
    sys.path.insert(0, "/root/xiaomi-register")
    from eui_encrypt import encrypt_form_fields
    result = encrypt_form_fields(fields)
    return result["EUI"], result["encryptedParams"]


# ─── STEP FUNCTIONS ──────────────────────────────────────────────────────────

def step1_warmup():
    """GET register page to collect cookies."""
    print("\n[Step 1] GET register page (warm-up)...")
    resp = SESSION.get(REGISTER_URL)
    print(f"  Status: {resp.status_code}")
    print(f"  Cookies: {dict(SESSION.cookies)}")
    return resp


def step2_captcha_data():
    """POST captcha/v2/data with encrypted fingerprint."""
    print("\n[Step 2] POST captcha/v2/data...")

    # Load and refresh payload template
    with open("/root/xiaomi-register/capture/xiaomi/payload_template.json") as f:
        payload = json.load(f)

    now_ms = int(time.time() * 1000)
    payload["startTs"] = now_ms
    payload["endTs"] = now_ms + random.randint(500, 1500)
    payload["env"]["p11"] = now_ms
    payload["nonce"]["t"] = int(now_ms / 1000)
    payload["nonce"]["r"] = random.randint(1000000000, 9999999999)
    payload["env"]["p33"] = []  # No webdriver

    s, d = encrypt_captcha_payload(payload)

    ts = int(time.time() * 1000)
    url = f"https://verify.sec.xiaomi.com/captcha/v2/data?k={CAPTCHA_PARAM_K}&locale=en_US&_t={ts}"
    body = f"s={quote(s)}&d={quote(d)}&a=register"

    resp = SESSION.post(url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    data = resp.json()
    print(f"  Response code: {data.get('code')}")

    if data.get("code") != 0:
        raise RuntimeError(f"captcha/v2/data failed: {data}")

    e_token = parse_qs(urlparse(data["data"]["url"]).query)["e"][0]
    print(f"  e_token: {e_token[:40]}...")
    return e_token


def step3_solve_captcha(e_token: str) -> str:
    """Solve reCAPTCHA Enterprise via 2Captcha v2 API."""
    print("\n[Step 3] Solving reCAPTCHA Enterprise via 2Captcha...")

    # createTask
    create_body = {
        "clientKey": CAPTCHA_API_KEY,
        "task": {
            "type": "RecaptchaV2EnterpriseTaskProxyless",
            "websiteURL": REGISTER_URL,
            "websiteKey": CAPTCHA_SITE_KEY,
            "enterprisePayload": {"s": e_token}
        }
    }
    resp = SESSION.post("https://api.2captcha.com/createTask", json=create_body)
    result = resp.json()
    print(f"  createTask: {result}")

    if result.get("errorId", 0) != 0:
        raise RuntimeError(f"2Captcha createTask error: {result}")

    task_id = result["taskId"]

    # Poll getTaskResult
    for attempt in range(60):
        time.sleep(5)
        poll_body = {"clientKey": CAPTCHA_API_KEY, "taskId": task_id}
        resp = SESSION.post("https://api.2captcha.com/getTaskResult", json=poll_body)
        result = resp.json()
        print(f"  Poll {attempt+1}: status={result.get('status')}")

        if result.get("status") == "ready":
            g_recaptcha = result["solution"]["gRecaptchaResponse"]
            print(f"  gRecaptchaResponse: {g_recaptcha[:50]}...")
            return g_recaptcha
        elif result.get("errorId", 0) != 0:
            raise RuntimeError(f"2Captcha error: {result}")

    raise TimeoutError("2Captcha timed out after 300s")


def step4_recaptcha_verify(e_token: str, g_recaptcha: str) -> str:
    """POST captcha/v2/recaptcha/verify. Returns vToken."""
    print("\n[Step 4] POST captcha/v2/recaptcha/verify...")

    ts = int(time.time() * 1000)
    url = f"https://verify.sec.xiaomi.com/captcha/v2/recaptcha/verify?k={CAPTCHA_PARAM_K}&locale=en_US&_t={ts}"
    body = f"e={quote(e_token)}&g={quote(g_recaptcha)}&type=4"

    resp = SESSION.post(url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    data = resp.json()
    print(f"  Response: code={data.get('code')}, result={data.get('data', {}).get('result')}")

    if data.get("code") != 0 or not data.get("data", {}).get("result"):
        raise RuntimeError(f"recaptcha verify failed: {data}")

    vtoken = data["data"]["token"]
    print(f"  vToken: {vtoken[:50]}...")
    return vtoken


def step5_encrypt_email_password():
    """Encrypt email+password for EUI. Returns (eui, enc_email, enc_password)."""
    print("\n[Step 5] Encrypting email+password (EUI)...")

    eui, enc_params = build_eui({"email": EMAIL, "password": PASSWORD})
    enc_email = enc_params["email"]
    enc_password = enc_params["password"]

    print(f"  EUI: {eui[:50]}...")
    print(f"  enc_email: {enc_email[:40]}...")
    return eui, enc_email, enc_password


def step6_send_email_reg_ticket(vtoken: str, eui: str, enc_email: str, enc_password: str) -> dict:
    """POST sendEmailRegTicket."""
    print("\n[Step 6] POST sendEmailRegTicket...")

    device_id = f"wb_{uuid.uuid4()}"
    url = "https://global.account.xiaomi.com/pass/sendEmailRegTicket"

    headers = {
        "eui": eui,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": REGISTER_URL,
        "Origin": "https://global.account.xiaomi.com",
    }

    cookies = {
        "vToken": vtoken,
        "vAction": "register",
        "deviceId": device_id,
    }

    body = urlencode({
        "email": enc_email,
        "password": enc_password,
        "region": "ID",
        "sid": "",
        "icode": "",
    })

    # Set cookies on session
    SESSION.cookies.set("vToken", vtoken, domain="global.account.xiaomi.com")
    SESSION.cookies.set("vAction", "register", domain="global.account.xiaomi.com")
    SESSION.cookies.set("deviceId", device_id, domain="global.account.xiaomi.com")

    resp = SESSION.post(url, data=body, headers=headers)
    text = resp.text
    print(f"  Raw response: {text[:200]}")
    if text.startswith("&&&START&&&"):
        text = text[len("&&&START&&&"):]
    data = json.loads(text)
    print(f"  Response: {data}")

    if data.get("code") != 0:
        raise RuntimeError(f"sendEmailRegTicket failed: {data}")

    print(f"  Verification code length: {data.get('data', {}).get('vCodeLen')}")
    return data


def step7_read_imap_code(timeout=120) -> str:
    """Read 6-digit verification code from Gmail IMAP."""
    print("\n[Step 7] Reading verification code from IMAP...")
    print(f"  Waiting for email to {EMAIL}...")

    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
            imap.login(IMAP_USER, IMAP_PASS)
            imap.select("INBOX")

            # Search recent unseen from xiaomi
            _, data = imap.search(None, '(UNSEEN FROM "noreply@notice.xiaomi.com")')
            msg_ids = data[0].split()

            for msg_id in reversed(msg_ids[-20:]):
                _, msg_data = imap.fetch(msg_id, "(RFC822)")
                raw = msg_data[0][1]
                msg = email_lib.message_from_bytes(raw)

                # Check if it's for our exact email
                to_addr = msg.get("To", "").lower()
                if EMAIL.lower() not in to_addr:
                    print(f"    Skipping email to: {to_addr[:50]}")
                    continue
                print(f"    Matched email to: {to_addr[:50]}")

                # Get body
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

                # Remove MIME soft-breaks
                body = body.replace("=\r\n", "")

                match = re.search(r"verification code is[:\s]*(\d{6})", body, re.IGNORECASE)
                if match:
                    code = match.group(1)
                    print(f"  Found code: {code}")
                    imap.logout()
                    return code

            imap.logout()
        except Exception as e:
            print(f"  IMAP error: {e}")

        print(f"  No code yet, retrying in 5s...")
        time.sleep(5)

    raise TimeoutError("Did not receive verification code within timeout")


def step8_verify_email_reg_ticket(vtoken: str, code: str) -> dict:
    """POST verifyEmailRegTicket — creates the account."""
    print("\n[Step 8] POST verifyEmailRegTicket (creating account)...")

    # Re-encrypt with fresh AES key
    eui, enc_params = build_eui({"email": EMAIL, "password": PASSWORD})
    enc_email = enc_params["email"]
    enc_password = enc_params["password"]

    device_fp = "".join(random.choices("0123456789abcdef", k=32))

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

    resp = SESSION.post(url, data=body, headers=headers)
    text = resp.text
    print(f"  Raw response: {text[:300]}")
    if text.startswith("&&&START&&&"):
        text = text[len("&&&START&&&"):]
    data = json.loads(text)
    print(f"  Response: {data}")

    if data.get("code") != 0:
        raise RuntimeError(f"verifyEmailRegTicket failed: {data}")

    return data


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Xiaomi Account Registration v3 — Browserless")
    print(f"Email: {EMAIL}")
    print(f"Password: {PASSWORD}")
    print("=" * 60)

    # Step 1: Warm-up
    step1_warmup()

    # Pre-cleanup: mark all existing Xiaomi emails as read
    print("\n[Cleanup] Marking old Xiaomi emails as read...")
    try:
        imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        imap.login(IMAP_USER, IMAP_PASS)
        imap.select("INBOX")
        _, data = imap.search(None, '(UNSEEN FROM "noreply@notice.xiaomi.com")')
        for mid in data[0].split():
            imap.store(mid, "+FLAGS", "\\Seen")
        print(f"  Marked {len(data[0].split()) if data[0] else 0} old emails as read")
        imap.logout()
    except Exception as e:
        print(f"  Cleanup error: {e}")

    # Steps 2-4 with retry loop (up to 4 attempts)
    vtoken = None
    for attempt in range(4):
        try:
            # Step 2: Captcha data
            e_token = step2_captcha_data()

            # Step 3: Solve captcha
            g_recaptcha = step3_solve_captcha(e_token)

            # Step 4: Verify captcha → get vToken
            vtoken = step4_recaptcha_verify(e_token, g_recaptcha)
            break
        except RuntimeError as e:
            print(f"\n  Attempt {attempt+1} failed: {e}")
            if attempt < 3:
                print("  Retrying from step 2...")
                time.sleep(2)
            else:
                raise

    # Step 5: Encrypt email+password
    eui, enc_email, enc_password = step5_encrypt_email_password()

    # Step 6: Send registration ticket
    step6_send_email_reg_ticket(vtoken, eui, enc_email, enc_password)

    # Step 7: Read verification code
    code = step7_read_imap_code()

    # Step 8: Verify and create account
    result = step8_verify_email_reg_ticket(vtoken, code)

    # Extract cookies
    cookies = {}
    for name in ("passToken", "serviceToken", "cUserId", "userId"):
        val = SESSION.cookies.get(name, domain="account.xiaomi.com") or SESSION.cookies.get(name)
        if val:
            cookies[name] = val

    print("\n" + "=" * 60)
    print("ACCOUNT CREATED SUCCESSFULLY!")
    print("=" * 60)
    print(f"Email:    {EMAIL}")
    print(f"Password: {PASSWORD}")
    print(f"Cookies:  {json.dumps(cookies, indent=2)}")

    # Save to file
    account_data = {
        "email": EMAIL,
        "password": PASSWORD,
        "cookies": cookies,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    out_path = "/root/xiaomi-register/xiaomi_account.json"
    with open(out_path, "w") as f:
        json.dump(account_data, f, indent=2)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
