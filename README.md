# Xiaomi Account Registration — Browserless

Reverse-engineered Xiaomi account registration & MiMo UltraSpeed beta application. **100% HTTP API — no browser automation.**

## Structure

```
├── register.py           # Register Xiaomi account (8-step API flow)
├── mimo_bot/
│   ├── mimo_bot.py       # Login → SSO → Referral → Apply UltraSpeed
│   └── requirements.txt
├── scripts/
│   └── encrypt.cjs       # Node.js AES+RSA crypto helper (EUI encryption)
├── docs/
│   ├── FLOW.md           # Reverse-engineering notes
│   └── payload_template.json
├── .env.example
└── .gitignore
```

## Prerequisites

- Python 3.10+
- Node.js 18+ (for `scripts/encrypt.cjs`)
- [WARP](https://1.1.1.1/) SOCKS5 proxy on `127.0.0.1:40000` (Xiaomi blocks VPS IPs)
- 2Captcha API key (reCAPTCHA Enterprise, ~$0.003/solve)
- Gmail with App Password (IMAP for verification codes)

## Setup

```bash
pip install curl_cffi pycryptodome python-dotenv
cp .env.example .env
# Edit .env with your credentials
```

## 1. Register Xiaomi Account

```bash
python3 register.py
```

**Flow:** Warm-up → Captcha fingerprint → 2Captcha solve → Verify → Encrypt email+password → Send verification → IMAP read code → Create account

**Env vars needed:** `TWOCAPTCHA_API_KEY`, `EMAIL`, `XIAOMI_PASSWORD`, `IMAP_USER`, `IMAP_PASS`

## 2. Apply MiMo UltraSpeed Beta

```bash
cd mimo_bot
python3 mimo_bot.py
# or with args:
python3 mimo_bot.py --email user@example.com --password xxx --referral MX5V9X
```

**Flow:** Login → Captcha (if needed) → SSO redirect → Bind referral → Apply UltraSpeed

**Env vars needed:** `TWOCAPTCHA_API_KEY`, `EMAIL`, `XIAOMI_PASSWORD`, `REFERRAL_CODE`

## Architecture

- **curl_cffi** with `impersonate="chrome124"` for TLS fingerprint
- **WARP SOCKS5 proxy** to bypass VPS IP blocking (503)
- **pycryptodome** for AES-128-CBC + RSA-PKCS1v15 (identical to CryptoJS output)
- **2Captcha v2 API** for reCAPTCHA Enterprise solving
- **IMAP** for reading verification codes from forwarded emails

## Key Pitfalls

- VPS IPs get **503** from `account.xiaomi.com` — must use WARP proxy
- `icode` param is **EMPTY** — captcha pass is via `vToken` cookie
- `eui` is a **HEADER**, not body param
- All Xiaomi responses prefixed with `&&&START&&&` — strip before JSON parse
- `qs=%253Fsid%253Dpassport` — raw string, don't double-encode
- RSA double-base64: `s = base64(RSA(base64(aesKey)))`
- IMAP: mark old emails as read before each registration
- 30-50% captcha failure rate — retry up to 4 times

## License

Private use only.
