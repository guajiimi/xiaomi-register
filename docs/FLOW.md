# Xiaomi Account — Browserless Registration

Resep register akun Xiaomi (global.account.xiaomi.com) **100% via HTTP** — tanpa browser.
Hasil akhir: akun jadi + cookie sesi (`passToken`, `serviceToken`).

> Semua nilai sensitif di file `*.sanitized.json` diganti `<REDACTED>`.
> Yang penting di situ: **nama field, endpoint, dan bentuk response** — bukan nilainya.

## Yang dibutuhkan
- API key solver captcha: **2Captcha** atau **CapSolver** (reCAPTCHA Enterprise).
- Email dengan **catch-all** ke 1 inbox + akses **IMAP** (mis. domain → Gmail). Kode verifikasi dibaca dari sini.
- Node 18+ (`fetch`, `crypto` global), lib: `node-forge` (RSA), `imapflow` (IMAP).

## Konstanta
```
CAPTCHA_DATA_KEY  = 8027422fb0eb42fbac1b521ec4a7961f
RECAPTCHA_SITEKEY = 6LeBM0ocAAAAAEwYcFUjtxpVbs-0rnbSVXBBXmh4
REGISTER_PAGE     = https://global.account.xiaomi.com/fe/service/register?_locale=en_US&_uRegion=ID
UA                = Mozilla/5.0 (Windows NT 10.0; Win64; x64) ... Chrome/148.0.0.0 Safari/537.36
```

## Alur (8 langkah)

**1. (opsional) GET register page** — warm-up; cookie awal tidak wajib.

**2. POST `verify.sec.xiaomi.com/captcha/v2/data?k=<KEY>&locale=en_US&_t=<ms>`**
Body (form): `s=<S>&d=<D>&a=register`.
`s`/`d` = fingerprint browser terenkripsi (lihat **Crypto s/d**). Kalau asal → `400 invalid data`.
Response: `{code:0, data:{ id, url }}`. Ambil `e_token` dari query `e` pada `data.url`.

**3. Solve reCAPTCHA** (2Captcha/CapSolver), task `RecaptchaV2EnterpriseTaskProxyless`
(CapSolver: `ReCaptchaV2EnterpriseTaskProxyLess`), `websiteURL=REGISTER_PAGE`, `websiteKey=SITEKEY`,
**WAJIB** `enterprisePayload:{ s: e_token }` — kalau tidak, token tak terikat ke challenge dan langkah 6 gagal `87001`.
Hasil: `gRecaptchaResponse` (token `g`).

**4. POST `verify.sec.xiaomi.com/captcha/v2/recaptcha/verify?k=<KEY>&locale=en_US&_t=<ms>`**
Body: `e=<e_token>&g=<g>&type=4`.
Sukses: `{code:0, data:{ result:true, token:<VTOKEN> }}`.
⚠️ Sering `result:false` (~30-50%, kualitas solve) → ulang dari langkah 2 dengan e_token baru. Bikin retry loop (4×).

**5. Encrypt email+password (EUI)** — lihat **Crypto EUI**. Nama field **harus `email,password`**.

**6. POST `global.account.xiaomi.com/pass/sendEmailRegTicket`**
Header: `eui:<EUI>`, `Content-Type: application/x-www-form-urlencoded; charset=UTF-8`, `X-Requested-With: XMLHttpRequest`.
**Cookie (KUNCI):** `vToken=<urlencode(VTOKEN)>; vAction=register; deviceId=wb_<uuid>`.
Body: `email=<enc>&password=<enc>&region=ID&sid=&icode=`  ← **`icode` SENGAJA KOSONG.**
> Gotcha utama: captcha pass dibawa lewat **cookie `vToken`** (= token langkah 4), BUKAN param `icode`.
> Browser asli pun kirim `icode=` kosong. Tanpa `vToken` → `87001 CAPTCHA_VERIFY_ERROR`.
Sukses: `{code:0, data:{address, vCodeLen:6}}` → email kode terkirim.

**7. Baca kode 6-digit via IMAP** dari `noreply@notice.xiaomi.com`.
> Gotcha: body MIME penuh angka 6-digit. Ambil yang benar dengan
> `/verification code is[:\s]*(\d{6})/i` (setelah hapus soft-break `=\r\n`). JANGAN pakai `\b\d{6}\b`.

**8. POST `global.account.xiaomi.com/pass/verifyEmailRegTicket`** — ini yang **MEMBUAT akun**.
Header `eui:<EUI baru>` (encrypt ulang email+password).
Body:
```
ticket=<code>&region=ID&email=<enc>&env=web&qs=%253Fsid%253Dpassport
&isAcceptLicense=true&sid=&password=<enc>&policyName=globalmiaccount
&callback=&deviceFingerprint=<32 hex acak>
```
Sukses `{code:0}` → akun JADI; server set cookie sesi **`passToken`, `serviceToken`, `cUserId`, `userId`, `passInfo=login-end`**.

Selesai — akun Xiaomi sudah terdaftar.

---

## Crypto `s`/`d` (fingerprint captcha)
Hasil bongkar `m.js` (miverify). Skema sama seperti EUI, beda RSA key:
```
aesKey = 16 char acak
d = base64( AES-128-CBC( pkcs7(utf8(JSON(payload))), key=aesKey, iv="0102030405060708" ) )
s = base64( RSA-PKCS1v1.5( base64(aesKey) ) )   // RSA public key captcha (2048-bit, di bawah)
body = s=<s>&d=<d>&a=register
```
RSA public key captcha (2048-bit):
```
-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEArxfNLkuAQ/BYHzkzVwtu
g+0abmYRBVCEScSzGxJIOsfxVzcuqaKO87H2o2wBcacD3bRHhMjTkhSEqxPjQ/FE
XuJ1cdbmr3+b3EQR6wf/cYcMx2468/QyVoQ7BADLSPecQhtgGOllkC+cLYN6Md34
Uii6U+VJf0p0q/saxUTZvhR2ka9fqJ4+6C6cOghIecjMYQNHIaNW+eSKunfFsXVU
+QfMD0q2EM9wo20aLnos24yDzRjh9HJc6xfr37jRlv1/boG/EABMG9FnTm35xWrV
R0nw3cpYF7GZg13QicS/ZwEsSd4HyboAruMxJBPvK3Jdr4ZS23bpN0cavWOJsBqZ
VwIDAQAB
-----END PUBLIC KEY-----
```
`payload` = fingerprint collector m.js:
`{type, startTs, endTs, env:{p1..p34}, action:{a1..a14}, force, talkBack, nonce:{t,r}, version:"2.0", scene:"register"}`.
Struktur lengkap → **`payload_template.json`**. Cara aman: capture template asli sekali pakai
**`dump_payload.mjs`** (hook `JSON.stringify` di browser, ambil objek ber-`env`+`nonce`+`scene`); di runtime
tinggal refresh `startTs/endTs/p11/nonce` tiap call. Server toleran (terima fingerprint headless Chrome).
Set `env.p33 = []` (kalau ada `"webdriver"` → tanda bot).

## Crypto EUI (email/password)
```
aesKey = 16 char acak
encField(v) = base64( AES-128-CBC( pkcs7(utf8(v)), key=aesKey, iv="0102030405060708" ) )
EUI = base64(RSA-PKCS1v1.5(base64(aesKey)))  +  "."  +  base64("email,password")
body: email=<encField(email)>&password=<encField(password)>
```
RSA key EUI **berbeda** dari key captcha (akun pakai key 1024-bit Xiaomi sendiri).
Nama field di `EUI` **harus sama** dengan key body (`email,password`); kalau `user,password` → ditolak.

---

## Isi bundel
- `FLOW.md` — dokumen ini.
- `payload_template.json` — contoh struktur fingerprint payload (`d`).
- `full_capture.sanitized.json` — capture register (data → sendEmailRegTicket → verifyEmailRegTicket), value diredaksi.
- `truth_capture.sanitized.json` — capture verify + sendEmailRegTicket (lihat mekanisme `vToken`/`eui`).
- `api_captures.sanitized.json` — capture API register awal.
- `dump_payload.mjs` — generate `payload_template.json` sendiri (Playwright).
- `capture_full.mjs` / `capture_truth.mjs` — generate capture sendiri; butuh config di
  `~/.hermes/credentials/mimo-config.json` (`twocaptcha_api_key`/`capsolver_api_key`,
  `gmail_register.{email,app_password}`, `domain`). Email/password di script tinggal contoh — ganti sendiri.

## Catatan
- Endpoint/format bisa berubah kalau Xiaomi update front-end (`m.js`, chunk). Kalau `s`/`d` mulai `400`,
  regenerate `payload_template.json` via `dump_payload.mjs`.
- Hormati ToS layanan terkait; pakai untuk keperluan yang sah saja.
