#!/usr/bin/env python3
"""
Xiaomi Account Login + MiMo Referral — Full API, No Browser
Endpoint: POST /pass/serviceLoginAuth2
Captcha: reCAPTCHA Enterprise v2 via miverify → 2captcha
"""

import json
import time
import uuid
import random
import base64
import os
import sys
import hashlib
import subprocess
from urllib.parse import urlencode, quote, parse_qs, urlparse, quote_plus

from curl_cffi import requests as cffi_requests
from Crypto.Cipher import AES
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5
from Crypto.Util.Padding import pad

# ─── CONFIG ──────────────────────────────────────────────────────────────────
TWOCAPTCHA_API_KEY = os.environ.get("TWOCAPTCHA_API_KEY", "")

CAPTCHA_SITE_KEY = "6LeBM0ocAAAAAEwYcFUjtxpVbs-0rnbSVXBBXmh4"
CAPTCHA_PARAM_K = "8027422fb0eb42fbac1b521ec4a7961f"

LOGIN_URL = "https://account.xiaomi.com/fe/service/login/password"
LOGIN_PAGE_PARAMS = "_locale=en&sid=api-platform"

# MiMo referral
MIMO_REFERRAL_CODE = "MX5V9X"

# Captcha RSA key (2048-bit) — for fingerprint encryption
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

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"


# ─── CRYPTO ──────────────────────────────────────────────────────────────────

def random_aes_key(length=16):
    return "".join(random.choices(KEY_CHARS, k=length))

def aes_encrypt(plaintext: str, aes_key: str) -> str:
    cipher = AES.new(aes_key.encode("utf-8"), AES.MODE_CBC, AES_IV)
    ct = cipher.encrypt(pad(plaintext.encode("utf-8"), AES.block_size))
    return base64.b64encode(ct).decode("utf-8")

def rsa_encrypt(data_b64: str, pem: str) -> str:
    key = RSA.import_key(pem)
    cipher = PKCS1_v1_5.new(key)
    ct = cipher.encrypt(data_b64.encode("utf-8"))
    return base64.b64encode(ct).decode("utf-8")

def encrypt_captcha_payload(payload: dict) -> tuple:
    """Encrypt captcha fingerprint. Returns (s, d)."""
    aes_key = random_aes_key()
    payload_json = json.dumps(payload, separators=(",", ":"))
    d = aes_encrypt(payload_json, aes_key)
    s = rsa_encrypt(base64.b64encode(aes_key.encode()).decode(), CAPTCHA_RSA_PEM)
    return s, d

def encrypt_user_field(email: str) -> str:
    """Encrypt email for 'user' field using Node.js encrypt.cjs."""
    result = subprocess.run(
        ["node", "/root/xiaomi-register/encrypt.cjs", json.dumps({"email": email})],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0:
        raise Exception(f"encrypt.cjs failed: {result.stderr}")
    data = json.loads(result.stdout)
    return data["encrypted"]["email"]

def md5_hash(text: str) -> str:
    """MD5 hash uppercase — matches Xiaomi's hash field."""
    return hashlib.md5(text.encode("utf-8")).hexdigest().upper()

def strip_xiaomi_prefix(text: str) -> dict:
    """Strip &&&START&&& prefix from Xiaomi responses."""
    if text.startswith("&&&START&&&"):
        text = text[len("&&&START&&&"):]
    return json.loads(text)


# ─── 2CAPTCHA ────────────────────────────────────────────────────────────────

def solve_recaptcha_enterprise(api_key: str, sitekey: str, page_url: str, e_token: str = "", max_wait: int = 300) -> str:
    """Solve reCAPTCHA v2 Enterprise via 2captcha createTask API."""
    print("[2captcha] Submitting RecaptchaV2EnterpriseTaskProxyless...")

    task = {
        "type": "RecaptchaV2EnterpriseTaskProxyless",
        "websiteURL": page_url,
        "websiteKey": sitekey,
    }
    if e_token:
        task["enterprisePayload"] = {"s": e_token}
        print(f"[2captcha] With enterprisePayload.s = {e_token[:30]}...")

    resp = cffi_requests.post("https://api.2captcha.com/createTask", json={
        "clientKey": api_key,
        "task": task,
    }, timeout=30)
    result = resp.json()

    if result.get("errorId", 0) != 0:
        raise Exception(f"2captcha createTask error: {result}")

    task_id = result["taskId"]
    print(f"[2captcha] Task ID: {task_id}")

    start = time.time()
    while time.time() - start < max_wait:
        time.sleep(10)
        resp = cffi_requests.post("https://api.2captcha.com/getTaskResult", json={
            "clientKey": api_key,
            "taskId": task_id,
        }, timeout=30)
        result = resp.json()

        if result.get("status") == "ready":
            token = result["solution"]["gRecaptchaResponse"]
            print(f"[2captcha] Solved! Token: {token[:40]}...")
            return token
        elif result.get("errorId", 0) != 0:
            raise Exception(f"2captcha error: {result}")
        else:
            elapsed = int(time.time() - start)
            print(f"[2captcha] Waiting... ({elapsed}s)")

    raise Exception(f"2captcha timeout after {max_wait}s")


# ─── XIAOMI LOGIN ────────────────────────────────────────────────────────────

class XiaomiLogin:
    def __init__(self, email: str, password: str, api_key: str):
        self.email = email
        self.password = password
        self.api_key = api_key
        self.session = cffi_requests.Session(impersonate="chrome124")
        self.session.headers.update({
            "User-Agent": UA,
            "Accept-Language": "en-US,en;q=0.9",
        })
        self.device_fp = hashlib.md5(os.urandom(16)).hexdigest()

    def step1_warm_up(self):
        """GET login page to warm up session + get cookies."""
        print("[1/6] Loading login page...")
        resp = self.session.get(
            f"{LOGIN_URL}?{LOGIN_PAGE_PARAMS}",
            timeout=30, allow_redirects=True
        )
        print(f"  Status: {resp.status_code}, Cookies: {list(dict(resp.cookies).keys())}")
        return resp

    def step2_get_captcha_data(self) -> str:
        """POST /captcha/v2/data → get e_token for reCAPTCHA Enterprise."""
        print("[2/6] Getting captcha e_token...")

        ts = int(time.time() * 1000)
        payload = {
            "type": 0,
            "startTs": ts,
            "endTs": ts + random.randint(500, 1500),
            "env": {
                "p1": "0.1", "p2": "pc-Chrome148", "p3": "Windows NT 10.0; Win64; x64",
                "p4": "Gecko", "p5": "en-US", "p6": "Netscape", "p7": "Mozilla",
                "p8": True, "p9": UA, "p10": 0, "p11": ts,
                "p12": 1280, "p13": 800, "p14": 1280, "p15": 800, "p16": 1280, "p17": 800,
                "p18": LOGIN_URL, "p19": 5,
                "p20": "b61165d7c387d373f59d977af2b3c5a090f61907",
                "p21": "Pd369809e2cf9b3e61d61254f48e6a98e6abe02ed",
                "p22": 0, "p23": "da39a3ee5e6b4b0d3255bfef95601890afd80709",
                "p24": "", "p25": "79c0c1eb2748f583a66ce654b4dc1685157963f8",
                "p26": "fbe83d766a4229e366d48d0096d8e26aaf852730",
                "p28": "", "p29": 107, "p30": 10, "p31": 10, "p32": "0.73",
                "p33": [],  # MUST be empty
                "p34": LOGIN_URL
            },
            "action": {
                "a1": [1280, 800], "a2": [], "a3": [[657, 599, 99], [827, 702, 690]],
                "a4": [], "a5": [[657, 599, 83], [827, 702, 685]],
                "a6": [], "a7": [], "a8": [99], "a9": [98, 689],
                "a10": [], "a11": [], "a12": [], "a13": [], "a14": []
            },
            "force": True, "talkBack": False,
            "nonce": {"t": int(time.time()), "r": int.from_bytes(os.urandom(4), 'big')},
            "version": "2.0", "scene": "login"
        }

        s_val, d_val = encrypt_captcha_payload(payload)

        ts_url = int(time.time() * 1000)
        resp = self.session.post(
            f"https://verify.sec.xiaomi.com/captcha/v2/data?k={CAPTCHA_PARAM_K}&locale=en_US&_t={ts_url}",
            data=f"s={quote_plus(s_val)}&d={quote_plus(d_val)}&a=login",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15
        )
        data = strip_xiaomi_prefix(resp.text)
        print(f"  Captcha data: code={data.get('code')}")

        if data.get("code") != 0:
            raise Exception(f"Captcha data failed: {data}")

        url = data["data"]["url"]
        e_token = parse_qs(urlparse(url).query)["e"][0]
        print(f"  e_token: {e_token[:40]}...")
        return e_token

    def step3_solve_captcha(self, e_token: str) -> str:
        """Solve reCAPTCHA Enterprise v2 via 2captcha."""
        print("[3/6] Solving reCAPTCHA Enterprise v2...")
        return solve_recaptcha_enterprise(
            self.api_key, CAPTCHA_SITE_KEY, LOGIN_URL, e_token
        )

    def step4_verify_captcha(self, e_token: str, g_token: str) -> str:
        """POST /captcha/v2/recaptcha/verify → get vToken (flag)."""
        print("[4/6] Verifying captcha → getting vToken...")

        ts = int(time.time() * 1000)
        resp = self.session.post(
            f"https://verify.sec.xiaomi.com/captcha/v2/recaptcha/verify?k={CAPTCHA_PARAM_K}&locale=en_US&_t={ts}",
            data=f"e={quote_plus(e_token)}&g={quote_plus(g_token)}&type=4",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15
        )
        data = strip_xiaomi_prefix(resp.text)
        print(f"  Verify: code={data.get('code')}, result={data.get('data', {}).get('result')}")

        if data.get("code") != 0 or not data.get("data", {}).get("result"):
            raise Exception(f"Captcha verify failed: {data}")

        v_token = data["data"]["token"]
        print(f"  vToken (flag): {v_token[:40]}...")
        return v_token

    def step5_login(self, v_token: str = "") -> dict:
        """
        POST /pass/serviceLoginAuth2 — actual login.
        
        Body (from captured browser traffic):
          sid=api-platform
          callback=https://account.xiaomi.com
          qs=%253Fsid%253Dpassport
          serviceParam=
          _sign=
          user=<AES_encrypted_email>
          cc=%2B86
          hash=<MD5_password_UPPERCASE>
          _json=true
          policyName=globalmiaccount
          captCode=<vToken_flag_or_empty>
          deviceFingerprint=<32hex>
        """
        print("[5/6] Logging in via /pass/serviceLoginAuth2...")

        encrypted_email = encrypt_user_field(self.email)
        pw_hash = md5_hash(self.password)

        body = (
            f"sid=api-platform"
            f"&callback=https%3A%2F%2Faccount.xiaomi.com"
            f"&qs=%253Fsid%253Dpassport"
            f"&serviceParam="
            f"&_sign="
            f"&user={quote_plus(encrypted_email)}"
            f"&cc=%2B86"
            f"&hash={pw_hash}"
            f"&_json=true"
            f"&policyName=globalmiaccount"
            f"&captCode={quote_plus(v_token) if v_token else ''}"
            f"&deviceFingerprint={self.device_fp}"
        )

        resp = self.session.post(
            "https://account.xiaomi.com/pass/serviceLoginAuth2",
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"{LOGIN_URL}?{LOGIN_PAGE_PARAMS}",
                "Origin": "https://account.xiaomi.com",
            },
            timeout=30,
            allow_redirects=True
        )

        print(f"  Status: {resp.status_code}")

        text = resp.text
        if text.startswith("&&&START&&&"):
            text = text[len("&&&START&&&"):]
        try:
            data = json.loads(text)
        except:
            data = {"raw": text[:500], "status": resp.status_code}

        code = data.get("code", data.get("result", "unknown"))
        print(f"  Login response code: {code}")

        if data.get("location"):
            print(f"  Redirect URL: {data['location'][:100]}...")

        return data

    def step6_apply_referral(self) -> dict:
        """Apply referral code on MiMo platform."""
        print("[6/6] Applying referral code on MiMo platform...")

        # Navigate to MiMo console
        resp = self.session.get(
            f"https://platform.xiaomimimo.com?ref={MIMO_REFERRAL_CODE}",
            timeout=30, allow_redirects=True
        )
        print(f"  MiMo status: {resp.status_code}, URL: {resp.url}")

        # Try to apply referral via API
        try:
            resp2 = self.session.post(
                "https://platform.xiaomimimo.com/api/referral/apply",
                json={"code": MIMO_REFERRAL_CODE},
                headers={"Content-Type": "application/json"},
                timeout=15
            )
            print(f"  Referral API: {resp2.status_code} — {resp2.text[:200]}")
        except Exception as e:
            print(f"  Referral API error: {e}")

        return {"cookies": dict(self.session.cookies)}

    def run(self) -> dict:
        """Full login flow with captcha retry."""
        max_retries = 4

        for attempt in range(1, max_retries + 1):
            try:
                print(f"\n{'='*60}")
                print(f"ATTEMPT {attempt}/{max_retries} — {self.email}")
                print(f"{'='*60}\n")

                self.step1_warm_up()

                # Steps 2-4: Captcha flow (may not always be needed)
                v_token = ""
                try:
                    e_token = self.step2_get_captcha_data()
                    g_token = self.step3_solve_captcha(e_token)
                    v_token = self.step4_verify_captcha(e_token, g_token)
                except Exception as e:
                    print(f"  ⚠️ Captcha flow error: {e}")
                    print(f"  Trying login without captcha...")

                login_result = self.step5_login(v_token)

                # Check success
                if isinstance(login_result, dict):
                    code = login_result.get("code", login_result.get("result", ""))
                    if code == 0 or code == "ok" or login_result.get("location"):
                        print("\n✅ LOGIN SUCCESS!")
                        cookies = self.step6_apply_referral()

                        account = {
                            "email": self.email,
                            "cookies": dict(self.session.cookies),
                            "login_result": login_result,
                            "referral_applied": True,
                            "logged_in_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        }
                        out_path = "/root/xiaomi-register/xiaomi_login_result.json"
                        with open(out_path, "w") as f:
                            json.dump(account, f, indent=2)
                        print(f"\n💾 Saved to {out_path}")
                        return account

                    # 87001 = captcha error → retry
                    if code == 87001 or code == "error":
                        desc = login_result.get("description", login_result.get("desc", ""))
                        print(f"  ❌ Login failed: {code} — {desc}")

                        # Check if it's a captcha issue
                        if "验证" in str(desc) or "captcha" in str(desc).lower():
                            print(f"  Retrying with fresh captcha...")
                            continue

                        # Wrong password?
                        if "密码" in str(desc) or "password" in str(desc).lower():
                            print(f"  ❌ Wrong password!")
                            return login_result

                        if attempt < max_retries:
                            continue
                        return login_result

                return login_result

            except Exception as e:
                print(f"  ❌ Error: {e}")
                if attempt < max_retries:
                    print(f"  Retrying in 5s...")
                    time.sleep(5)
                    continue
                raise

        raise Exception(f"Login failed after {max_retries} attempts")


# ─── MAIN ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Xiaomi Login + MiMo Referral")
    parser.add_argument("--email", default="nicosetiawan@jimixz.tech")
    parser.add_argument("--password", default="jimixz123!")
    parser.add_argument("--api-key", default=TWOCAPTCHA_API_KEY)
    parser.add_argument("--referral", default=MIMO_REFERRAL_CODE)
    args = parser.parse_args()

    if not args.api_key:
        print("ERROR: Set TWOCAPTCHA_API_KEY env var or pass --api-key")
        sys.exit(1)

    MIMO_REFERRAL_CODE = args.referral

    bot = XiaomiLogin(args.email, args.password, args.api_key)
    result = bot.run()

    print(f"\n{'='*60}")
    print("RESULT:")
    print(json.dumps(result, indent=2)[:2000])
