# Xiaomi Account Registration — Browserless

Fully automated Xiaomi account registration via **reverse-engineered API flow** — no browser, no Selenium, no Playwright. 100% HTTP.

## How It Works

The script performs an 8-step API flow that replicates exactly what the Xiaomi registration page does in the browser:

1. **Warm-up** — GET register page to collect cookies
2. **Captcha fingerprint** — POST encrypted browser fingerprint to `verify.sec.xiaomi.com/captcha/v2/data`
3. **Solve reCAPTCHA** — Enterprise reCAPTCHA v2 solved via 2Captcha API
4. **Captcha verify** — Exchange captcha solution for a `vToken`
5. **Encrypt credentials** — AES-128-CBC + RSA PKCS1v1.5 encryption of email/password (pure Python)
6. **Send registration ticket** — POST to `sendEmailRegTicket` with encrypted email + password, `vToken` as cookie
7. **Read verification code** — Parse 6-digit code from Gmail IMAP (`noreply@notice.xiaomi.com`)
8. **Verify & create account** — POST to `verifyEmailRegTicket` → account created, session cookies returned

## Prerequisites

- **Python 3.10+**
- **2Captcha API key** (reCAPTCHA Enterprise solver)
- **Gmail account** with app password (IMAP access)

## Quick Start

```bash
# Clone
git clone https://github.com/guajiimi/xiaomi-register.git
cd xiaomi-register

# Install Python deps
pip install -r requirements.txt

# Configure credentials
cp .env.example .env
# Edit .env with your actual credentials

# Register a single account
python register_v3.py
```

## Batch Registration

Register multiple accounts using Gmail + alias addressing:

```bash
# Register 100 accounts (default)
python batch_register.py

# Register 10 accounts with custom batch ID
python batch_register.py -n 10 --batch-id mybatch

# Custom sleep between registrations
python batch_register.py -n 50 --sleep 15
```

Email pattern: `{EMAIL_PREFIX}+mi{BATCH_ID}_{SEQ}@gmail.com`

- Accounts saved to `accounts.jsonl` (one JSON per line)
- Failures saved to `failed.jsonl`
- **Resume support**: re-run to skip already-registered emails
- Prints `[N/100]` status per account

## Environment Variables

| Variable | Description |
|----------|-------------|
| `TWOCAPTCHA_API_KEY` | Your 2Captcha API key |
| `IMAP_USER` | Gmail address for reading verification codes |
| `IMAP_PASS` | Gmail app password |
| `EMAIL_PREFIX` | Gmail local part (before `+alias@gmail.com`) |

## Crypto Overview

Two encryption layers (replicated from Xiaomi's `m.js`):

### Captcha fingerprint (`s`/`d`)
```
aesKey = random 16 chars
d = base64(AES-128-CBC-PKCS7(json(payload), key=aesKey, iv="0102030405060708"))
s = base64(RSA-PKCS1v1.5(base64(aesKey)))   // 2048-bit RSA key
```

### EUI (email/password encryption)
```
encField(v) = base64(AES-128-CBC-PKCS7(v, key=aesKey, iv="0102030405060708"))
EUI = base64(RSA-PKCS1v1.5(base64(aesKey))) + "." + base64("email,password")
```

## Important Notes

- The `vToken` captcha pass is carried via **cookie**, not the `icode` parameter
- Captcha solve quality varies (~30-50% pass rate) — retry loop handles this
- If `s`/`d` start returning 400, regenerate `payload_template.json` from a fresh browser capture
- Respect applicable Terms of Service; use for legitimate purposes only

## Files

| File | Description |
|------|-------------|
| `register_v3.py` | Main registration script (single account) |
| `batch_register.py` | Batch registration with resume support |
| `eui_encrypt.py` | Pure Python AES+RSA encryption (Xiaomi EUI format) |
| `capture/xiaomi/payload_template.json` | Browser fingerprint template |
| `capture/xiaomi/FLOW.md` | Detailed reverse-engineering notes |
