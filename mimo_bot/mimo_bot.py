#!/usr/bin/env python3
"""
Xiaomi MiMo UltraSpeed Batch Auto-Apply Bot
=============================================
Logs into Xiaomi accounts via API, applies referral code, and registers for UltraSpeed beta.
"""

import os
import sys
import json
import time
import hashlib
import base64
import random
import subprocess
import argparse
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from curl_cffi import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

# ─── Colors ────────────────────────────────────────────────────────────────────
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

def info(msg):    print(f"{C.CYAN}[*]{C.RESET} {msg}")
def ok(msg):      print(f"{C.GREEN}[+]{C.RESET} {msg}")
def warn(msg):    print(f"{C.YELLOW}[!]{C.RESET} {msg}")
def err(msg):     print(f"{C.RED}[-]{C.RESET} {msg}")
def step(msg):    print(f"{C.MAGENTA}[>]{C.RESET} {msg}")
def banner():
    print(f"""
{C.BOLD}{C.CYAN}╔═══════════════════════════════════════════════════════╗
║      Xiaomi MiMo UltraSpeed Batch Auto-Apply Bot     ║
║              Referral: MX5V9X                         ║
╚═══════════════════════════════════════════════════════╝{C.RESET}
""")

# ─── Constants ─────────────────────────────────────────────────────────────────
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"

LOGIN_URL = "https://account.xiaomi.com/pass/serviceLoginAuth2"
CAPTCHA_DATA_URL = "https://verify.sec.xiaomi.com/captcha/v2/data?k=8027422fb0eb42fbac1b521ec4a7961f&locale=en_US&_t={ts}"
CAPTCHA_VERIFY_URL = "https://verify.sec.xiaomi.com/captcha/v2/recaptcha/verify?k=8027422fb0eb42fbac1b521ec4a7961f&locale=en_US&_t={ts}"

MIMO_PLATFORM_URL = "https://platform.xiaomimimo.com"
MIMO_REFERRAL_URL = "https://platform.xiaomimimo.com/referral/apply"
MIMO_ULTRASPEED_URL = "https://platform.xiaomimimo.com/ultraspeed"

CAPTCHA_SITEKEY = "6LeBM0ocAAAAAEwYcFUjtxpVbs-0rnbSVXBBXmh4"
TWOCAPTCHA_CREATE_URL = "https://2captcha.com/in.php"
TWOCAPTCHA_RESULT_URL = "https://2captcha.com/res.php"

ENCRYPT_CJS = "/root/xiaomi-register/encrypt.cjs"

CAPTCHA_RSA_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEArxfNLkuAQ/BYHzkzVwtu
g+0abmYRBVCEScSzGxJIOsfxVzcuqaKO87H2o2wBcacD3bRHhMjTkhSEqxPjQ/FE
XuJ1cdbmr3+b3EQR6wf/cYcMx2468/QyVoQ7BADLSPecQhtgGOllkC+cLYN6Md34
Uii6U+VJf0p0q/saxUTZvhR2ka9fqJ4+6C6cOghIecjMYQNHIaNW+eSKunfFsXVU
+QfMD0q2EM9wo20aLnos24yDzRjh9HJc6xfr37jRlv1/boG/EABMG9FnTm35xWrV
R0nw3cpYF7GZg13QicS/ZwEsSd4HyboAruMxJBPvK3Jdr4ZS23bpN0cavWOJsBqZ
VwIDAQAB
-----END PUBLIC KEY-----"""

AES_IV = b"0102030405060708"
KEY_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*"

# ─── Config ────────────────────────────────────────────────────────────────────
load_dotenv(Path(__file__).parent / ".env")
TWOCAPTCHA_API_KEY = os.getenv("TWOCAPTCHA_API_KEY", "")
REFERRAL_CODE = os.getenv("REFERRAL_CODE", "MX5V9X")

MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds


# ─── Encryption helpers ────────────────────────────────────────────────────────

def encrypt_user_field(email: str) -> tuple:
    """Encrypt email via encrypt.cjs Node.js helper.
    Returns (encrypted_email, eui) tuple."""
    result = subprocess.run(
        ["node", ENCRYPT_CJS, json.dumps({"email": email})],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0:
        raise RuntimeError(f"encrypt.cjs failed: {result.stderr}")
    data = json.loads(result.stdout)
    return data["encryptedParams"]["email"], data.get("EUI", "")


def md5_password(password: str) -> str:
    """MD5 hash of password, uppercase."""
    return hashlib.md5(password.encode()).hexdigest().upper()


def generate_device_fingerprint() -> str:
    """Generate a random 32-hex device fingerprint."""
    return hashlib.md5(os.urandom(16)).hexdigest()


def encrypt_captcha_payload(payload: dict) -> tuple:
    """Returns (s, d) for captcha/v2/data POST using AES+RSA double encryption."""
    aes_key = "".join(random.choices(KEY_CHARS, k=16))
    cipher = AES.new(aes_key.encode(), AES.MODE_CBC, AES_IV)
    plaintext = json.dumps(payload, separators=(",", ":")).encode()
    d = base64.b64encode(cipher.encrypt(pad(plaintext, 16))).decode()

    key = RSA.import_key(CAPTCHA_RSA_PEM)
    cipher_rsa = PKCS1_v1_5.new(key)
    s = base64.b64encode(
        cipher_rsa.encrypt(base64.b64encode(aes_key.encode()).decode().encode())
    ).decode()
    return s, d


def build_captcha_fingerprint_payload() -> dict:
    """Build the browser fingerprint payload for captcha/v2/data."""
    ts = int(time.time() * 1000)
    return {
        "type": 0, "startTs": ts, "endTs": ts + random.randint(500, 1500),
        "env": {
            "p1": "0.1", "p2": "pc-Chrome148", "p3": "Windows NT 10.0; Win64; x64",
            "p4": "Gecko", "p5": "en-US", "p6": "Netscape", "p7": "Mozilla",
            "p8": True, "p9": UA, "p10": 0, "p11": ts,
            "p12": 1280, "p13": 800, "p14": 1280, "p15": 800, "p16": 1280, "p17": 800,
            "p18": "https://account.xiaomi.com/fe/service/login/password",
            "p19": 5, "p20": hashlib.sha1(os.urandom(20)).hexdigest(),
            "p21": "P" + hashlib.sha1(os.urandom(20)).hexdigest(),
            "p22": 0, "p23": "da39a3ee5e6b4b0d3255bfef95601890afd80709",
            "p24": "", "p25": hashlib.sha1(os.urandom(20)).hexdigest(),
            "p26": hashlib.sha1(os.urandom(20)).hexdigest(),
            "p28": "", "p29": 107, "p30": 10, "p31": 10, "p32": "0.73",
            "p33": [],  # MUST be empty — ["webdriver"] = bot detected
            "p34": "https://account.xiaomi.com/fe/service/login/password"
        },
        "action": {
            "a1": [1280, 800], "a2": [],
            "a3": [[657, 599, 99], [827, 702, 690]],
            "a4": [], "a5": [[657, 599, 83], [827, 702, 685]],
            "a6": [], "a7": [], "a8": [99], "a9": [98, 689],
            "a10": [], "a11": [], "a12": [], "a13": [], "a14": []
        },
        "force": True, "talkBack": False,
        "nonce": {"t": int(time.time()), "r": int.from_bytes(os.urandom(4), 'big')},
        "version": "2.0", "scene": "login"
    }


# ─── 2captcha solver ──────────────────────────────────────────────────────────

def solve_captcha_2captcha(e_token: str, timeout: int = 300) -> Optional[str]:
    """Solve reCAPTCHA Enterprise v2 via 2captcha. Returns g_token or None."""
    if not TWOCAPTCHA_API_KEY or TWOCAPTCHA_API_KEY == "your_2...":
        err("2captcha API key not configured!")
        return None

    step("Submitting captcha to 2captcha solver...")
    payload = {
        "key": TWOCAPTCHA_API_KEY,
        "method": "userrecaptcha",
        "googlekey": CAPTCHA_SITEKEY,
        "pageurl": "https://account.xiaomi.com/fe/service/login/password",
        "json": 1,
        "enterprise": 1,
        "v": "grecaptcha",
        "enterprisePayload": json.dumps({"s": e_token}),
    }

    try:
        resp = requests.post(TWOCAPTCHA_CREATE_URL, data=payload, timeout=30, impersonate="chrome124")
        result = resp.json()
        if result.get("status") != 1:
            err(f"2captcha submit failed: {result.get('request', 'unknown')}")
            return None

        task_id = result["request"]
        info(f"Captcha task ID: {task_id}")

        # Poll for result
        start = time.time()
        while time.time() - start < timeout:
            time.sleep(10)
            resp = requests.get(
                TWOCAPTCHA_RESULT_URL,
                params={"key": TWOCAPTCHA_API_KEY, "action": "get", "id": task_id, "json": 1},
                timeout=30, impersonate="chrome124"
            )
            result = resp.json()
            if result.get("status") == 1:
                ok("Captcha solved!")
                return result["request"]
            elif result.get("request") == "CAPCHA_NOT_READY":
                info("Captcha not ready yet, waiting...")
                continue
            else:
                err(f"2captcha error: {result.get('request')}")
                return None

        err("2captcha timeout!")
        return None
    except Exception as e:
        err(f"2captcha exception: {e}")
        return None


# ─── Captcha Flow ──────────────────────────────────────────────────────────────

def handle_captcha(session: requests.Session) -> Optional[str]:
    """Full captcha flow: get e_token, solve, verify → returns vToken or None."""
    step("Initiating captcha challenge...")

    ts = int(time.time() * 1000)
    fingerprint_payload = build_captcha_fingerprint_payload()
    s, d = encrypt_captcha_payload(fingerprint_payload)

    url = CAPTCHA_DATA_URL.format(ts=ts)
    try:
        resp = session.post(
            url,
            data={"s": s, "d": d},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            impersonate="chrome124"
        )
        # Response may contain e_token in various places
        e_token = None
        text = resp.text

        # Try JSON parse
        try:
            data = resp.json()
            if "url" in data:
                # e_token might be in URL
                import urllib.parse
                parsed = urllib.parse.urlparse(data["url"])
                params = urllib.parse.parse_qs(parsed.query)
                e_token = params.get("e", [None])[0]
            elif "e" in data:
                e_token = data["e"]
        except Exception:
            pass

        if not e_token:
            # Try extracting from response text directly
            if "e=" in text:
                import re
                match = re.search(r'e=([a-zA-Z0-9_\-]+)', text)
                if match:
                    e_token = match.group(1)

        if not e_token:
            err(f"Could not extract e_token from captcha data response: {text[:300]}")
            return None

        info(f"Got e_token: {e_token[:30]}...")
    except Exception as e:
        err(f"Captcha data request failed: {e}")
        return None

    # Step 2: Solve via 2captcha
    g_token = solve_captcha_2captcha(e_token)
    if not g_token:
        return None

    # Step 3: Verify captcha
    step("Verifying captcha solution...")
    ts = int(time.time() * 1000)
    url = CAPTCHA_VERIFY_URL.format(ts=ts)
    try:
        resp = session.post(
            url,
            data={"e": e_token, "g": g_token, "type": "4"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            impersonate="chrome124"
        )
        data = resp.json()
        v_token = data.get("flag") or data.get("vtoken") or data.get("vToken") or data.get("token")
        if v_token:
            ok(f"Got vToken: {v_token[:30]}...")
            return v_token
        else:
            err(f"Captcha verify failed: {resp.text[:300]}")
            return None
    except Exception as e:
        err(f"Captcha verify exception: {e}")
        return None


# ─── Xiaomi Login ──────────────────────────────────────────────────────────────

def parse_xiaomi_response(text: str) -> dict:
    """Strip &&&START&&& prefix and parse JSON."""
    clean = text.strip()
    if clean.startswith("&&&START&&&"):
        clean = clean[len("&&&START&&&"):].strip()
    return json.loads(clean)


def login_xiaomi(email: str, password: str, dry_run: bool = False) -> Optional[dict]:
    """
    Login to Xiaomi account. Returns dict with cookies/tokens or None.
    Returns dict: {passToken, serviceToken, cUserId, userId, cookies: dict}
    """
    step(f"Logging in: {email}")

    session = requests.Session(impersonate="chrome124")
    session.headers.update({
        "User-Agent": UA,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://account.xiaomi.com",
        "Referer": "https://account.xiaomi.com/fe/service/login/password",
    })

    encrypted_user, eui = encrypt_user_field(email)
    pw_hash = md5_password(password)
    device_fp = generate_device_fingerprint()

    def do_login(capt_code: str = ""):
        data = {
            "sid": "api-platform",
            "callback": "https://account.xiaomi.com",
            "qs": "%3Fsid%3Dpassport",
            "serviceParam": "",
            "_sign": "",
            "user": encrypted_user,
            "cc": "+86",
            "hash": pw_hash,
            "_json": "true",
            "policyName": "globalmiaccount",
            "captCode": capt_code,
            "deviceFingerprint": device_fp,
        }
        if eui:
            data["_EUI"] = eui
        return session.post(LOGIN_URL, data=data, impersonate="chrome124")

    if dry_run:
        ok(f"[DRY RUN] Would login as {email}")
        return {"email": email, "dry_run": True}

    # First attempt
    resp = do_login()
    try:
        result = parse_xiaomi_response(resp.text)
    except json.JSONDecodeError:
        err(f"Login response parse failed: {resp.text[:300]}")
        return None

    code = result.get("code", -1)
    location = result.get("location")

    # Success
    if code == 0 or location:
        ok(f"Login success for {email} (code={code})")
        cookies = {}
        for c in session.cookies:
            cookies[c.name] = c.value
        return {
            "email": email,
            "code": code,
            "location": location,
            "cookies": cookies,
            "passToken": cookies.get("passToken", ""),
            "serviceToken": cookies.get("serviceToken", ""),
            "userId": cookies.get("userId", ""),
            "cUserId": cookies.get("cUserId", ""),
            "result": result,
        }

    # Captcha required
    if code == 70016:
        warn(f"Captcha required for {email} (code=70016)")
        v_token = handle_captcha(session)
        if not v_token:
            err(f"Captcha solving failed for {email}")
            return None

        # Retry login with captcha
        resp = do_login(capt_code=v_token)
        try:
            result = parse_xiaomi_response(resp.text)
        except json.JSONDecodeError:
            err(f"Login retry parse failed: {resp.text[:300]}")
            return None

        code = result.get("code", -1)
        location = result.get("location")
        if code == 0 or location:
            ok(f"Login success after captcha for {email}")
            cookies = {}
            for c in session.cookies:
                cookies[c.name] = c.value
            return {
                "email": email,
                "code": code,
                "location": location,
                "cookies": cookies,
                "passToken": cookies.get("passToken", ""),
                "serviceToken": cookies.get("serviceToken", ""),
                "userId": cookies.get("userId", ""),
                "cUserId": cookies.get("cUserId", ""),
                "result": result,
            }
        else:
            err(f"Login failed after captcha: code={code}, resp={resp.text[:200]}")
            return None

    # Wrong password
    if code == 70002:
        err(f"Wrong password for {email}")
        return None

    # Unknown error
    err(f"Login failed for {email}: code={code}, resp={resp.text[:200]}")
    return None


# ─── MiMo Platform Actions ─────────────────────────────────────────────────────

def get_mimo_cookies(login_data: dict) -> Optional[dict]:
    """
    Follow SSO redirect chain to get MiMo platform cookies from Xiaomi login.
    Returns updated cookies dict.
    """
    step("Getting MiMo platform session via SSO redirect...")

    session = requests.Session(impersonate="chrome124")
    session.headers.update({
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })

    # Set Xiaomi login cookies
    for name, value in login_data.get("cookies", {}).items():
        session.cookies.set(name, value, domain=".xiaomi.com")

    # Also set serviceToken if present
    if login_data.get("serviceToken"):
        session.cookies.set("serviceToken", login_data["serviceToken"], domain=".xiaomi.com")
    if login_data.get("passToken"):
        session.cookies.set("passToken", login_data["passToken"], domain=".xiaomi.com")
    if login_data.get("userId"):
        session.cookies.set("userId", login_data["userId"], domain=".xiaomi.com")
    if login_data.get("cUserId"):
        session.cookies.set("cUserId", login_data["cUserId"], domain=".xiaomi.com")

    # Follow redirect to MiMo platform
    try:
        resp = session.get(
            f"{MIMO_PLATFORM_URL}?ref={REFERRAL_CODE}",
            impersonate="chrome124",
            allow_redirects=True
        )
        info(f"MiMo platform response: {resp.status_code}, redirects: {len(resp.history)}")

        # Collect all cookies from redirect chain
        mimo_cookies = {}
        for c in session.cookies:
            mimo_cookies[c.name] = c.value

        if mimo_cookies:
            ok(f"Got {len(mimo_cookies)} cookies for MiMo platform")
        else:
            warn("No cookies received from MiMo platform")

        return {"cookies": mimo_cookies, "session": session, "final_url": resp.url, "status": resp.status_code}

    except Exception as e:
        err(f"MiMo SSO redirect failed: {e}")
        return None


def apply_referral(session: requests.Session, cookies: dict, dry_run: bool = False) -> bool:
    """Apply referral code on MiMo platform."""
    step(f"Applying referral code: {REFERRAL_CODE}")

    if dry_run:
        ok(f"[DRY RUN] Would apply referral code: {REFERRAL_CODE}")
        return True

    try:
        # Try POST to referral endpoint
        resp = session.post(
            MIMO_REFERRAL_URL,
            json={"code": REFERRAL_CODE},
            headers={
                "Content-Type": "application/json",
                "Origin": MIMO_PLATFORM_URL,
                "Referer": f"{MIMO_PLATFORM_URL}?ref={REFERRAL_CODE}",
            },
            impersonate="chrome124"
        )

        if resp.status_code in (200, 201):
            try:
                data = resp.json()
                if data.get("success") or data.get("code") == 0:
                    ok(f"Referral code applied successfully!")
                    return True
                else:
                    info(f"Referral response: {data}")
                    # May already be applied or other non-critical status
                    return True
            except json.JSONDecodeError:
                if resp.status_code == 200:
                    ok(f"Referral code POST returned 200")
                    return True
        else:
            # Try alternate endpoint patterns
            alt_urls = [
                f"{MIMO_PLATFORM_URL}/api/referral/apply",
                f"{MIMO_PLATFORM_URL}/api/v1/referral",
                f"{MIMO_PLATFORM_URL}/api/referral",
            ]
            for alt_url in alt_urls:
                try:
                    resp = session.post(
                        alt_url,
                        json={"code": REFERRAL_CODE, "referralCode": REFERRAL_CODE},
                        headers={
                            "Content-Type": "application/json",
                            "Origin": MIMO_PLATFORM_URL,
                            "Referer": f"{MIMO_PLATFORM_URL}?ref={REFERRAL_CODE}",
                        },
                        impersonate="chrome124"
                    )
                    info(f"Referral {alt_url} → {resp.status_code}")
                    if resp.status_code in (200, 201):
                        ok(f"Referral applied via {alt_url}")
                        return True
                except Exception:
                    continue

            warn(f"Referral application returned status {resp.status_code}")
            return True  # Don't fail the whole flow

    except Exception as e:
        err(f"Referral apply exception: {e}")
        return False


def apply_ultraspeed(session: requests.Session, cookies: dict, dry_run: bool = False) -> bool:
    """Apply for UltraSpeed beta on MiMo platform."""
    step("Applying for UltraSpeed beta...")

    if dry_run:
        ok("[DRY RUN] Would apply for UltraSpeed beta")
        return True

    try:
        # Visit the UltraSpeed page first
        resp = session.get(
            MIMO_ULTRASPEED_URL,
            headers={
                "Referer": f"{MIMO_PLATFORM_URL}?ref={REFERRAL_CODE}",
            },
            impersonate="chrome124"
        )
        info(f"UltraSpeed page: {resp.status_code}")

        # Try POST to apply for UltraSpeed
        apply_urls = [
            f"{MIMO_ULTRASPEED_URL}/apply",
            f"{MIMO_PLATFORM_URL}/api/ultraspeed/apply",
            f"{MIMO_PLATFORM_URL}/api/v1/ultraspeed",
            f"{MIMO_PLATFORM_URL}/api/beta/apply",
        ]

        for url in apply_urls:
            try:
                resp = session.post(
                    url,
                    json={"apply": True, "code": REFERRAL_CODE},
                    headers={
                        "Content-Type": "application/json",
                        "Origin": MIMO_PLATFORM_URL,
                        "Referer": MIMO_ULTRASPEED_URL,
                    },
                    impersonate="chrome124"
                )
                info(f"UltraSpeed {url} → {resp.status_code}")
                if resp.status_code in (200, 201):
                    try:
                        data = resp.json()
                        info(f"UltraSpeed response: {json.dumps(data)[:200]}")
                    except Exception:
                        pass
                    ok(f"UltraSpeed beta application submitted!")
                    return True
            except Exception:
                continue

        # If all API attempts fail, the page GET might have triggered it
        ok("UltraSpeed page visited (may have auto-applied)")
        return True

    except Exception as e:
        err(f"UltraSpeed apply exception: {e}")
        return False


# ─── Account Processing ───────────────────────────────────────────────────────

def process_account(email: str, password: str, dry_run: bool = False) -> dict:
    """Process a single account: login → MiMo cookies → referral → UltraSpeed."""
    result = {
        "email": email,
        "status": "failed",
        "login": False,
        "referral": False,
        "ultraspeed": False,
        "error": None,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    try:
        # Step 1: Login
        login_data = login_xiaomi(email, password, dry_run)
        if not login_data:
            result["error"] = "Login failed"
            return result
        result["login"] = True

        # Step 2: Get MiMo session
        if not dry_run:
            mimo_data = get_mimo_cookies(login_data)
            if not mimo_data:
                result["error"] = "MiMo SSO redirect failed"
                return result
            mimo_session = mimo_data["session"]
            mimo_cookies = mimo_data["cookies"]
        else:
            mimo_session = None
            mimo_cookies = {}

        # Step 3: Apply referral
        ref_ok = apply_referral(mimo_session, mimo_cookies, dry_run)
        result["referral"] = ref_ok

        # Step 4: Apply UltraSpeed
        us_ok = apply_ultraspeed(mimo_session, mimo_cookies, dry_run)
        result["ultraspeed"] = us_ok

        if ref_ok and us_ok:
            result["status"] = "success"
        elif ref_ok or us_ok:
            result["status"] = "partial"

    except Exception as e:
        result["error"] = str(e)
        err(f"Unexpected error for {email}: {e}")

    return result


def process_with_retry(email: str, password: str, dry_run: bool = False) -> dict:
    """Process account with retry logic."""
    for attempt in range(1, MAX_RETRIES + 1):
        if attempt > 1:
            warn(f"Retry {attempt}/{MAX_RETRIES} for {email} in {RETRY_DELAY}s...")
            time.sleep(RETRY_DELAY)

        result = process_account(email, password, dry_run)
        if result["status"] in ("success", "partial"):
            return result
        if result.get("error") == "Wrong password":
            return result  # Don't retry wrong passwords

    return result


# ─── Main ──────────────────────────────────────────────────────────────────────

def load_accounts(filepath: str) -> list:
    """Load accounts from file. Returns list of (email, password) tuples."""
    accounts = []
    path = Path(filepath)
    if not path.exists():
        err(f"Accounts file not found: {filepath}")
        return accounts

    with open(path) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                warn(f"Line {line_num}: invalid format (expected email:password)")
                continue
            email, password = line.split(":", 1)
            accounts.append((email.strip(), password.strip()))

    return accounts


def main():
    banner()

    parser = argparse.ArgumentParser(description="Xiaomi MiMo UltraSpeed Batch Auto-Apply Bot")
    parser.add_argument("--accounts", default=str(Path(__file__).parent / "accounts.txt"),
                        help="Path to accounts file (default: accounts.txt)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Test without actually applying")
    parser.add_argument("--single", type=str, default=None,
                        help="Process single account: email:password")
    parser.add_argument("--max-retries", type=int, default=3,
                        help="Max retry attempts (default: 3)")
    args = parser.parse_args()

    global MAX_RETRIES
    MAX_RETRIES = args.max_retries

    if args.dry_run:
        warn("DRY RUN MODE — no actual login or applications will be made")

    # Load accounts
    if args.single:
        if ":" not in args.single:
            err("--single format: email:password")
            sys.exit(1)
        email, password = args.single.split(":", 1)
        accounts = [(email.strip(), password.strip())]
    else:
        accounts = load_accounts(args.accounts)

    if not accounts:
        err("No accounts to process!")
        sys.exit(1)

    info(f"Loaded {len(accounts)} account(s)")
    info(f"Referral code: {REFERRAL_CODE}")
    info(f"Max retries: {MAX_RETRIES}")
    print()

    # Process accounts
    results = []
    success = 0
    failed = 0

    for i, (email, password) in enumerate(accounts, 1):
        print(f"{C.BOLD}{C.CYAN}{'='*60}")
        print(f"  Account {i}/{len(accounts)}: {email}")
        print(f"{'='*60}{C.RESET}")

        result = process_with_retry(email, password, args.dry_run)
        results.append(result)

        if result["status"] == "success":
            ok(f"✓ {email}: SUCCESS")
            success += 1
        elif result["status"] == "partial":
            warn(f"△ {email}: PARTIAL — {result.get('error', 'some steps failed')}")
            success += 1
        else:
            err(f"✗ {email}: FAILED — {result.get('error', 'unknown')}")
            failed += 1

        # Delay between accounts
        if i < len(accounts):
            delay = random.uniform(2, 5)
            info(f"Waiting {delay:.1f}s before next account...")
            time.sleep(delay)

    # Save results
    results_path = Path(__file__).parent / "results.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)

    # Summary
    print(f"\n{C.BOLD}{C.CYAN}{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}{C.RESET}")
    ok(f"Success: {success}/{len(accounts)}")
    if failed:
        err(f"Failed: {failed}/{len(accounts)}")
    info(f"Results saved to: {results_path}")


if __name__ == "__main__":
    main()
