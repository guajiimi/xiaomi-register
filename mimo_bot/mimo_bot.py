#!/usr/bin/env python3
"""
Xiaomi MiMo UltraSpeed Beta Apply
==================================
Single-account flow: Login Xiaomi → SSO to MiMo → Bind referral → Apply UltraSpeed.

Usage:
    python mimo_bot.py                          # uses .env credentials
    python mimo_bot.py --email user@x.com --password 'pw'
    python mimo_bot.py --dry-run                # test without side-effects
"""

import os
import sys
import re
import json
import time
import hashlib
import base64
import random
import subprocess
import argparse
import urllib.parse
from pathlib import Path
from typing import Optional, Dict, Any

from dotenv import load_dotenv
from curl_cffi import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

# ═══════════════════════════════════════════════════════════════════════════════
#  Console helpers
# ═══════════════════════════════════════════════════════════════════════════════

class C:
    RESET   = "\033[0m"
    RED     = "\033[91m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    BLUE    = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN    = "\033[96m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"


def info(msg):   print(f"{C.CYAN}[*]{C.RESET} {msg}")
def ok(msg):     print(f"{C.GREEN}[✓]{C.RESET} {msg}")
def warn(msg):   print(f"{C.YELLOW}[!]{C.RESET} {msg}")
def err(msg):    print(f"{C.RED}[✗]{C.RESET} {msg}")
def step(msg):   print(f"{C.MAGENTA}[▸]{C.RESET} {msg}")


def banner():
    print(f"""
{C.BOLD}{C.CYAN}┌──────────────────────────────────────────────┐
│   MiMo UltraSpeed Beta — Auto-Apply Tool    │
└──────────────────────────────────────────────┘{C.RESET}""")


# ═══════════════════════════════════════════════════════════════════════════════
#  Constants
# ═══════════════════════════════════════════════════════════════════════════════

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/148.0.0.0 Safari/537.36"
)

PROXY = "socks5://127.0.0.1:40000"
IMPERSONATE = "chrome124"

# Xiaomi auth
LOGIN_URL        = "https://account.xiaomi.com/pass/serviceLoginAuth2"
SSO_LOGIN_URL    = "https://account.xiaomi.com/pass/serviceLogin"

# Captcha (Xiaomi reCAPTCHA Enterprise)
CAPTCHA_SITEKEY  = "6LeBM0ocAAAAAEwYcFUjtxpVbs-0rnbSVXBBXmh4"
CAPTCHA_DATA_TPL = "https://verify.sec.xiaomi.com/captcha/v2/data?k=8027422fb0eb42fbac1b521ec4a7961f&locale=en_US&_t={ts}"
CAPTCHA_VERIFY_TPL = "https://verify.sec.xiaomi.com/captcha/v2/recaptcha/verify?k=8027422fb0eb42fbac1b521ec4a7961f&locale=en_US&_t={ts}"

# 2Captcha API
TWOCAPTCHA_CREATE  = "https://2captcha.com/in.php"
TWOCAPTCHA_RESULT  = "https://2captcha.com/res.php"

# MiMo platform
MIMO_BASE          = "https://platform.xiaomimimo.com"
MIMO_REFERRAL_BIND = f"{MIMO_BASE}/api/v1/invitation/bind"
MIMO_ULTRASPEED    = f"{MIMO_BASE}/api/v1/mimo-speed/apply"

# encrypt.cjs for EUI encryption (email field)
ENCRYPT_CJS = "/root/xiaomi-register/encrypt.cjs"

# Captcha RSA public key (2048-bit) — encrypts AES key for fingerprint payload
CAPTCHA_RSA_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEArxfNLkuAQ/BYHzkzVwtu
g+0abmYRBVCEScSzGxJIOsfxVzcuqaKO87H2o2wBcacD3bRHhMjTkhSEqxPjQ/FE
XuJ1cdbmr3+b3EQR6wf/cYcMx2468/QyVoQ7BADLSPecQhtgGOllkC+cLYN6Md34
Uii6U+VJf0p0q/saxUTZvhR2ka9fqJ4+6C6cOghIecjMYQNHIaNW+eSKunfFsXVU
+QfMD0q2EM9wo20aLnos24yDzRjh9HJc6xfr37jRlv1/boG/EABMG9FnTm35xWrV
R0nw3cpYF7GZg13QicS/ZwEsSd4HyboAruMxJBPvK3Jdr4ZS23bpN0cavWOJsBqZ
VwIDAQAB
-----END PUBLIC KEY-----"""

AES_IV    = b"0102030405060708"
KEY_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz012456789!@#$%^&*"
# Fix: keep 0 in the charset
KEY_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*"


# ═══════════════════════════════════════════════════════════════════════════════
#  Encryption helpers
# ═══════════════════════════════════════════════════════════════════════════════

def encrypt_email(email: str) -> tuple:
    """Encrypt email field via encrypt.cjs (Node.js).
    Returns (encrypted_email, eui_string).
    """
    result = subprocess.run(
        ["node", ENCRYPT_CJS, json.dumps({"email": email})],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError(f"encrypt.cjs failed: {result.stderr.strip()}")
    data = json.loads(result.stdout)
    return data["encryptedParams"]["email"], data.get("EUI", "")


def md5_hash(text: str) -> str:
    """MD5 digest, uppercase hex."""
    return hashlib.md5(text.encode()).hexdigest().upper()


def random_fingerprint() -> str:
    """Random 32-hex device fingerprint."""
    return hashlib.md5(os.urandom(16)).hexdigest()


def encrypt_captcha_payload(payload: dict) -> tuple:
    """AES-CBC + RSA double encryption for captcha fingerprint.
    Returns (s, d) for POST body.
    """
    aes_key = "".join(random.choices(KEY_CHARS, k=16))
    cipher = AES.new(aes_key.encode(), AES.MODE_CBC, AES_IV)
    plaintext = json.dumps(payload, separators=(",", ":")).encode()
    d = base64.b64encode(cipher.encrypt(pad(plaintext, 16))).decode()

    rsa_key = RSA.import_key(CAPTCHA_RSA_PEM)
    cipher_rsa = PKCS1_v1_5.new(rsa_key)
    s = base64.b64encode(
        cipher_rsa.encrypt(base64.b64encode(aes_key.encode()).decode().encode())
    ).decode()
    return s, d


def build_fingerprint_payload() -> dict:
    """Build browser fingerprint for captcha/v2/data POST."""
    ts = int(time.time() * 1000)
    return {
        "type": 0,
        "startTs": ts,
        "endTs": ts + random.randint(500, 1500),
        "env": {
            "p1": "0.1", "p2": "pc-Chrome148", "p3": "Windows NT 10.0; Win64; x64",
            "p4": "Gecko", "p5": "en-US", "p6": "Netscape", "p7": "Mozilla",
            "p8": True, "p9": UA, "p10": 0, "p11": ts,
            "p12": 1280, "p13": 800, "p14": 1280, "p15": 800, "p16": 1280, "p17": 800,
            "p18": "https://account.xiaomi.com/fe/service/login/password",
            "p19": 5,
            "p20": hashlib.sha1(os.urandom(20)).hexdigest(),
            "p21": "P" + hashlib.sha1(os.urandom(20)).hexdigest(),
            "p22": 0,
            "p23": "da39a3ee5e6b4b0d3255bfef95601890afd80709",
            "p24": "",
            "p25": hashlib.sha1(os.urandom(20)).hexdigest(),
            "p26": hashlib.sha1(os.urandom(20)).hexdigest(),
            "p28": "", "p29": 107, "p30": 10, "p31": 10, "p32": "0.73",
            "p33": [],  # MUST be empty — ["webdriver"] = bot detected
            "p34": "https://account.xiaomi.com/fe/service/login/password",
        },
        "action": {
            "a1": [1280, 800], "a2": [],
            "a3": [[657, 599, 99], [827, 702, 690]],
            "a4": [], "a5": [[657, 599, 83], [827, 702, 685]],
            "a6": [], "a7": [], "a8": [99], "a9": [98, 689],
            "a10": [], "a11": [], "a12": [], "a13": [], "a14": [],
        },
        "force": True,
        "talkBack": False,
        "nonce": {"t": int(time.time()), "r": int.from_bytes(os.urandom(4), "big")},
        "version": "2.0",
        "scene": "login",
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  2Captcha reCAPTCHA Enterprise solver
# ═══════════════════════════════════════════════════════════════════════════════

def solve_captcha(api_key: str, e_token: str, timeout: int = 300) -> Optional[str]:
    """Solve reCAPTCHA Enterprise via 2Captcha. Returns g-token or None."""
    if not api_key:
        err("TWOCAPTCHA_API_KEY not set")
        return None

    step("Submitting captcha to 2Captcha…")
    payload = {
        "key": api_key,
        "method": "userrecaptcha",
        "googlekey": CAPTCHA_SITEKEY,
        "pageurl": "https://account.xiaomi.com/fe/service/login/password",
        "json": 1,
        "enterprise": 1,
        "v": "grecaptcha",
        "enterprisePayload": json.dumps({"s": e_token}),
    }

    try:
        resp = requests.post(TWOCAPTCHA_CREATE, data=payload, timeout=30, impersonate=IMPERSONATE)
        result = resp.json()
        if result.get("status") != 1:
            err(f"2Captcha submit failed: {result.get('request', '?')}")
            return None

        task_id = result["request"]
        info(f"Task ID: {task_id}")

        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(10)
            resp = requests.get(
                TWOCAPTCHA_RESULT,
                params={"key": api_key, "action": "get", "id": task_id, "json": 1},
                timeout=30, impersonate=IMPERSONATE,
            )
            result = resp.json()
            if result.get("status") == 1:
                ok("Captcha solved")
                return result["request"]
            if result.get("request") == "CAPCHA_NOT_READY":
                info("Not ready, waiting…")
                continue
            err(f"2Captcha error: {result.get('request')}")
            return None

        err("2Captcha timeout")
        return None
    except Exception as e:
        err(f"2Captcha exception: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
#  Captcha flow
# ═══════════════════════════════════════════════════════════════════════════════

def handle_captcha(session: requests.Session, api_key: str) -> Optional[str]:
    """Full captcha flow → get e-token from data endpoint, solve via 2Captcha, verify.
    Returns vToken string or None.
    """
    step("Initiating captcha challenge…")

    # 1. Get e_token from captcha/v2/data
    ts = int(time.time() * 1000)
    s, d = encrypt_captcha_payload(build_fingerprint_payload())
    url = CAPTCHA_DATA_TPL.format(ts=ts)

    e_token = None
    try:
        resp = session.post(
            url, data={"s": s, "d": d},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            impersonate=IMPERSONATE,
        )
        try:
            data = resp.json()
            if "url" in data:
                parsed = urllib.parse.urlparse(data["url"])
                params = urllib.parse.parse_qs(parsed.query)
                e_token = params.get("e", [None])[0]
            elif "e" in data:
                e_token = data["e"]
        except Exception:
            pass
        if not e_token:
            m = re.search(r"e=([a-zA-Z0-9_\-]+)", resp.text)
            if m:
                e_token = m.group(1)
    except Exception as e:
        err(f"Captcha data request failed: {e}")
        return None

    if not e_token:
        err(f"Could not extract e_token: {resp.text[:300]}")
        return None
    info(f"e_token: {e_token[:30]}…")

    # 2. Solve via 2Captcha
    g_token = solve_captcha(api_key, e_token)
    if not g_token:
        return None

    # 3. Verify and get vToken
    step("Verifying captcha solution…")
    ts = int(time.time() * 1000)
    url = CAPTCHA_VERIFY_TPL.format(ts=ts)
    try:
        resp = session.post(
            url, data={"e": e_token, "g": g_token, "type": "4"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            impersonate=IMPERSONATE,
        )
        data = resp.json()
        v_token = data.get("flag") or data.get("vtoken") or data.get("vToken") or data.get("token")
        if v_token:
            ok(f"vToken obtained: {v_token[:30]}…")
            return v_token
        err(f"Captcha verify failed: {resp.text[:300]}")
        return None
    except Exception as e:
        err(f"Captcha verify exception: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
#  Xiaomi Login
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_xiaomi(text: str) -> dict:
    """Strip &&&START&&& prefix and parse JSON."""
    clean = text.strip()
    if clean.startswith("&&&START&&&"):
        clean = clean[len("&&&START&&&"):].strip()
    return json.loads(clean)


def _extract_cookies(session: requests.Session) -> Dict[str, str]:
    return {c.name: c.value for c in session.cookies}


def login_xiaomi(
    email: str,
    password: str,
    *,
    twocaptcha_key: str = "",
    dry_run: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Login to Xiaomi via API.
    Returns dict with session cookies/tokens on success, None on failure.
    Keys: email, cookies, passToken, serviceToken, userId, cUserId, location, session
    """
    step(f"Logging in: {email}")

    session = requests.Session(impersonate=IMPERSONATE, proxy=PROXY)
    session.headers.update({
        "User-Agent": UA,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://account.xiaomi.com",
        "Referer": "https://account.xiaomi.com/fe/service/login/password",
    })

    # Warm-up: GET the login page (sets initial cookies)
    session.get(
        "https://account.xiaomi.com/fe/service/login/password",
        impersonate=IMPERSONATE,
    )

    enc_user, eui = encrypt_email(email)
    pw_hash = md5_hash(password)
    dev_fp = random_fingerprint()

    def do_login(capt_code: str = ""):
        data = {
            "sid": "api-platform",
            "callback": "https://account.xiaomi.com",
            "qs": "%3Fsid%3Dpassport",
            "serviceParam": "",
            "_sign": "",
            "user": enc_user,
            "cc": "+86",
            "hash": pw_hash,
            "_json": "true",
            "policyName": "globalmiaccount",
            "captCode": capt_code,
            "deviceFingerprint": dev_fp,
        }
        if eui:
            data["_EUI"] = eui
        return session.post(LOGIN_URL, data=data, impersonate=IMPERSONATE)

    if dry_run:
        ok(f"[DRY RUN] Would login as {email}")
        return {"email": email, "dry_run": True}

    # First attempt
    resp = do_login()
    try:
        result = _parse_xiaomi(resp.text)
    except json.JSONDecodeError:
        err(f"Login parse failed: {resp.text[:300]}")
        return None

    code = result.get("code", -1)
    location = result.get("location")

    # ── Success ──
    if code == 0 or location:
        ok(f"Login success (code={code})")
        cookies = _extract_cookies(session)
        return {
            "email": email,
            "cookies": cookies,
            "passToken": cookies.get("passToken", ""),
            "serviceToken": cookies.get("serviceToken", ""),
            "userId": cookies.get("userId", ""),
            "cUserId": cookies.get("cUserId", ""),
            "location": location,
            "session": session,
        }

    # ── Captcha required ──
    if code == 70016:
        warn("Captcha required (70016)")
        v_token = handle_captcha(session, twocaptcha_key)
        if not v_token:
            err("Captcha solving failed")
            return None

        resp = do_login(capt_code=v_token)
        try:
            result = _parse_xiaomi(resp.text)
        except json.JSONDecodeError:
            err(f"Login retry parse failed: {resp.text[:300]}")
            return None

        code = result.get("code", -1)
        location = result.get("location")
        if code == 0 or location:
            ok("Login success after captcha")
            cookies = _extract_cookies(session)
            return {
                "email": email,
                "cookies": cookies,
                "passToken": cookies.get("passToken", ""),
                "serviceToken": cookies.get("serviceToken", ""),
                "userId": cookies.get("userId", ""),
                "cUserId": cookies.get("cUserId", ""),
                "location": location,
                "session": session,
            }
        err(f"Login failed after captcha: code={code}")
        return None

    if code == 70002:
        err("Wrong password (70002)")
        return None

    err(f"Login failed: code={code} — {resp.text[:200]}")
    return None


# ═══════════════════════════════════════════════════════════════════════════════
#  SSO → MiMo platform cookies
# ═══════════════════════════════════════════════════════════════════════════════

def sso_to_mimo(login_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Follow SSO redirect chain: Xiaomi auth → MiMo platform.
    Returns dict with mimo cookies (api-platform_ph, api-platform_serviceToken) or None.
    """
    step("SSO → MiMo platform…")

    # Build STS callback URL for the SSO flow
    sts_url = f"{MIMO_BASE}/"

    session = requests.Session(impersonate=IMPERSONATE, proxy=PROXY)
    session.headers.update({
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })

    # Inject Xiaomi login cookies
    for name, value in login_data.get("cookies", {}).items():
        session.cookies.set(name, value, domain=".xiaomi.com")
    if login_data.get("passToken"):
        session.cookies.set("passToken", login_data["passToken"], domain=".xiaomi.com")
    if login_data.get("serviceToken"):
        session.cookies.set("serviceToken", login_data["serviceToken"], domain=".xiaomi.com")
    if login_data.get("userId"):
        session.cookies.set("userId", login_data["userId"], domain=".xiaomi.com")
    if login_data.get("cUserId"):
        session.cookies.set("cUserId", login_data["cUserId"], domain=".xiaomi.com")

    # GET serviceLogin with callback to MiMo STS
    sso_url = f"{SSO_LOGIN_URL}?callback={urllib.parse.quote(sts_url, safe='')}&sid=api-platform"
    try:
        resp = session.get(sso_url, impersonate=IMPERSONATE, allow_redirects=True)
        info(f"SSO redirects: {len(resp.history)} → {resp.status_code}")
    except Exception as e:
        err(f"SSO request failed: {e}")
        return None

    # Collect MiMo-specific cookies
    mimo_cookies = {c.name: c.value for c in session.cookies}

    ph = mimo_cookies.get("api-platform_ph", "")
    st = mimo_cookies.get("api-platform_serviceToken", "")
    if ph or st:
        ok(f"MiMo session established (ph={ph[:20]}…, serviceToken={st[:20]}…)")
    else:
        warn("No api-platform cookies found — may need manual redirect chain")
        info(f"Available cookies: {list(mimo_cookies.keys())}")

    return {"session": session, "cookies": mimo_cookies}


# ═══════════════════════════════════════════════════════════════════════════════
#  Referral binding
# ═══════════════════════════════════════════════════════════════════════════════

def bind_referral(
    session: requests.Session,
    referral_code: str,
    *,
    dry_run: bool = False,
) -> bool:
    """POST /api/v1/invitation/bind with referral code. Returns True on success."""
    step(f"Binding referral code: {referral_code}")

    if dry_run:
        ok(f"[DRY RUN] Would bind referral: {referral_code}")
        return True

    try:
        resp = session.post(
            MIMO_REFERRAL_BIND,
            json={"code": referral_code},
            headers={
                "Content-Type": "application/json",
                "Origin": MIMO_BASE,
                "Referer": f"{MIMO_BASE}/",
            },
            impersonate=IMPERSONATE,
        )
        info(f"Referral bind → {resp.status_code}")

        if resp.status_code in (200, 201):
            try:
                data = resp.json()
                info(f"Response: {json.dumps(data)[:200]}")
            except Exception:
                pass
            ok("Referral bound")
            return True

        # Non-fatal: may already be bound
        warn(f"Referral bind returned {resp.status_code} (may already be bound)")
        return True

    except Exception as e:
        err(f"Referral bind exception: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
#  UltraSpeed beta apply
# ═══════════════════════════════════════════════════════════════════════════════

def apply_ultraspeed(
    session: requests.Session,
    *,
    name: str = "",
    phone: str = "",
    email: str = "",
    company: str = "",
    industry: str = "",
    scenario: str = "",
    additional_info: str = "",
    dry_run: bool = False,
) -> bool:
    """POST /api/v1/mimo-speed/apply with form data. Returns True on success."""
    step("Applying for UltraSpeed beta…")

    if dry_run:
        ok("[DRY RUN] Would apply for UltraSpeed beta")
        return True

    payload = {
        "name": name,
        "phone": phone,
        "email": email,
        "company": company,
        "industry": industry,
        "scenario": scenario,
        "additionalInfo": additional_info,
    }

    try:
        resp = session.post(
            MIMO_ULTRASPEED,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Origin": MIMO_BASE,
                "Referer": f"{MIMO_BASE}/",
            },
            impersonate=IMPERSONATE,
        )
        info(f"UltraSpeed apply → {resp.status_code}")

        try:
            data = resp.json()
            info(f"Response: {json.dumps(data)[:200]}")
        except Exception:
            pass

        if resp.status_code in (200, 201):
            ok("UltraSpeed beta application submitted")
            return True

        # 401 is a known issue — report but don't crash
        if resp.status_code == 401:
            warn("UltraSpeed returned 401 (known issue, continuing)")
            return False

        warn(f"UltraSpeed returned {resp.status_code}")
        return False

    except Exception as e:
        err(f"UltraSpeed exception: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
#  Main flow
# ═══════════════════════════════════════════════════════════════════════════════

def run(
    email: str,
    password: str,
    referral_code: str = "",
    twocaptcha_key: str = "",
    *,
    dry_run: bool = False,
    # UltraSpeed optional fields
    name: str = "",
    phone: str = "",
    company: str = "",
    industry: str = "",
    scenario: str = "",
    additional_info: str = "",
) -> Dict[str, Any]:
    """
    Execute the full flow: login → SSO → bind referral → apply UltraSpeed.
    Returns a result dict with status for each step.
    """
    result = {
        "email": email,
        "login": False,
        "sso": False,
        "referral": False,
        "ultraspeed": False,
        "status": "failed",
        "error": None,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    try:
        # ── Step 1: Login ──
        login_data = login_xiaomi(
            email, password,
            twocaptcha_key=twocaptcha_key,
            dry_run=dry_run,
        )
        if not login_data:
            result["error"] = "Login failed"
            return result
        result["login"] = True

        if dry_run:
            result.update({"sso": True, "referral": True, "ultraspeed": True, "status": "dry_run"})
            return result

        # ── Step 2: SSO to MiMo ──
        mimo = sso_to_mimo(login_data)
        if not mimo:
            result["error"] = "SSO to MiMo failed"
            return result
        result["sso"] = True
        mimo_session = mimo["session"]

        # ── Step 3: Bind referral ──
        if referral_code:
            ref_ok = bind_referral(mimo_session, referral_code)
            result["referral"] = ref_ok
        else:
            warn("No referral code — skipping bind")
            result["referral"] = True

        # ── Step 4: Apply UltraSpeed ──
        us_ok = apply_ultraspeed(
            mimo_session,
            name=name, phone=phone, email=email,
            company=company, industry=industry,
            scenario=scenario, additional_info=additional_info,
        )
        result["ultraspeed"] = us_ok

        # Final status
        if result["login"] and result["sso"] and result["referral"] and result["ultraspeed"]:
            result["status"] = "success"
        elif result["login"] and result["sso"]:
            result["status"] = "partial"
        else:
            result["status"] = "failed"

    except Exception as e:
        result["error"] = str(e)
        err(f"Unexpected error: {e}")

    return result


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI entry point
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    banner()

    # Load .env from script directory or parent
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv(Path(__file__).parent.parent / ".env")

    parser = argparse.ArgumentParser(
        description="Xiaomi MiMo UltraSpeed Beta — Login, SSO, Referral, Apply",
    )
    parser.add_argument("--email",    default=os.getenv("EMAIL", ""),             help="Xiaomi account email")
    parser.add_argument("--password", default=os.getenv("XIAOMI_PASSWORD", ""),   help="Xiaomi account password")
    parser.add_argument("--referral", default=os.getenv("REFERRAL_CODE", ""),     help="Referral code to bind")
    parser.add_argument("--dry-run",  action="store_true",                        help="Test without side-effects")
    args = parser.parse_args()

    if not args.email or not args.password:
        err("Email and password required (via --email/--password or .env)")
        sys.exit(1)

    twocaptcha_key = os.getenv("TWOCAPTCHA_API_KEY", "")

    info(f"Email:     {args.email}")
    info(f"Referral:  {args.referral or '(none)'}")
    info(f"2Captcha:  {'configured' if twocaptcha_key else 'NOT SET'}")
    info(f"Proxy:     {PROXY}")
    if args.dry_run:
        warn("DRY RUN — no actual actions will be taken")
    print()

    result = run(
        email=args.email,
        password=args.password,
        referral_code=args.referral,
        twocaptcha_key=twocaptcha_key,
        dry_run=args.dry_run,
    )

    # Summary
    print(f"\n{C.BOLD}{'─' * 50}{C.RESET}")
    status_color = C.GREEN if result["status"] == "success" else C.YELLOW if result["status"] == "partial" else C.RED
    print(f"  Status: {status_color}{C.BOLD}{result['status'].upper()}{C.RESET}")
    for step_name in ("login", "sso", "referral", "ultraspeed"):
        icon = "✓" if result[step_name] else "✗"
        color = C.GREEN if result[step_name] else C.RED
        print(f"    {color}{icon}{C.RESET} {step_name}")
    if result.get("error"):
        print(f"    {C.RED}Error: {result['error']}{C.RESET}")
    print(f"{C.BOLD}{'─' * 50}{C.RESET}\n")

    sys.exit(0 if result["status"] in ("success", "partial", "dry_run") else 1)


if __name__ == "__main__":
    main()
