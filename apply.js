#!/usr/bin/env node
/**
 * MiMo UltraSpeed Beta — Auto Apply
 * Logs into Xiaomi account via SSO, applies for UltraSpeed beta.
 *
 * Usage:
 *   node apply.js                          # uses .env
 *   node apply.js --email X --password Y   # override
 *   node apply.js --batch accounts.jsonl   # apply for all accounts in file
 */

import 'dotenv/config';
import { readFileSync, existsSync, appendFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createInterface } from 'node:readline';
import crypto from 'node:crypto';
import { ImapFlow } from 'imapflow';

const __dirname = dirname(fileURLToPath(import.meta.url));

// ─── CONSTANTS ──────────────────────────────────────────────────────────────

const CAPTCHA_API_KEY = process.env.TWOCAPTCHA_API_KEY || '';
const CAPTCHA_SITE_KEY = '6LeBM0ocAAAAAEwYcFUjtxpVbs-0rnbSVXBBXmh4';
const CAPTCHA_PARAM_K = '8027422fb0eb42fbac1b521ec4a7961f';
const REGISTER_URL = 'https://global.account.xiaomi.com/fe/service/register?_locale=en_US&_uRegion=ID';
const MIMO_BASE = 'https://platform.xiaomimimo.com';
const MIMO_ULTRASPEED = `${MIMO_BASE}/ultraspeed`;
const IMAP_HOST = process.env.IMAP_HOST || 'imap.gmail.com';
const IMAP_USER = process.env.IMAP_USER || '';
const IMAP_PASS = process.env.IMAP_PASS || '';

const AES_IV = Buffer.from('0102030405060708');
const KEY_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*';

const CAPTCHA_RSA_PEM = `-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEArxfNLkuAQ/BYHzkzVwtu
g+0abmYRBVCEScSzGxJIOsfxVzcuqaKO87H2o2wBcacD3bRHhMjTkhSEqxPjQ/FE
XuJ1cdbmr3+b3EQR6wf/cYcMx2468/QyVoQ7BADLSPecQhtgGOllkC+cLYN6Md34
Uii6U+VJf0p0q/saxUTZvhR2ka9fqJ4+6C6cOghIecjMYQNHIaNW+eSKunfFsXVU
+QfMD0q2EM9wo20aLnos24yDzRjh9HJc6xfr37jRlv1/boG/EABMG9FnTm35xWrV
R0nw3cpYF7GZg13QicS/ZwEsSd4HyboAruMxJBPvK3Jdr4ZS23bpN0cavWOJsBqZ
VwIDAQAB
-----END PUBLIC KEY-----`;

const EUI_RSA_PEM = `-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCYEVrK/4Mahiv0pUJgTybx4J9P
5dUT/Y0PuwMbk+gMU+jrZnBiXGv6/hCH1avIhoBcE535F8nJQQN3UavZdFkYidso
XuEnat3+eVTp3FslyhRwIBDF09v4vDhRtxFOT+R7uH7h/mzmyA2/+lfIMWGIrffX
prYizbV76+YQKhoqFQIDAQAB
-----END PUBLIC KEY-----`;

// ─── FORM DATA OPTIONS ──────────────────────────────────────────────────────

const INDUSTRIES = [
  'Education and Research Institutions', 'Telecommunications and Operators',
  'Healthcare and Public Health', 'Cultural Industry',
  'Transportation and Logistics', 'Public Services', 'Public Technology',
  'Culture and Media', 'Finance and Tax Regulation', 'Energy and Power',
  'Natural Resources', 'Internet', 'Real Estate', 'Finance', 'Insurance',
  'Securities', 'Government', 'Retail', 'Public Security',
  'Manufacturing', 'Automotive', 'Others',
];

const USE_CASES = [
  'High-concurrency real-time chat', 'Real-time scene generation',
  'Live edits & preview on massive projects', 'Coding agent & code generation',
  'Latency-critical tasks (quant trading / risk control / bidding, etc.)',
  'Real-time IoT control', 'Parallel reasoning for higher quality', 'Other',
];

// Map English → Chinese (MiMo API uses Chinese values)
const INDUSTRY_ZH = {
  'Internet': '互联网', 'Finance': '金融', 'Insurance': '保险',
  'Securities': '证券', 'Government': '政府', 'Retail': '零售',
  'Manufacturing': '制造业', 'Automotive': '汽车', 'Others': '其他',
  'Education and Research Institutions': '教育科研',
  'Healthcare and Public Health': '医疗健康',
  'Real Estate': '房地产', 'Energy and Power': '能源电力',
  'Public Services': '公共服务', 'Public Security': '公共安全',
};

const USE_CASE_ZH = {
  'Coding agent & code generation': 'Coding Agent / 代码生成',
  'High-concurrency real-time chat': '高并发实时聊天',
  'Real-time scene generation': '实时场景生成',
  'Other': '其他',
};

// ─── HELPERS ────────────────────────────────────────────────────────────────

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const log = (step, emoji, msg) => console.log(`\n ${emoji} Step ${step}  ${msg}`);
const info = (msg) => console.log(`    ↳ ${msg}`);
const ok = (msg) => console.log(`    ↳ ${msg}`);
const err = (msg) => console.log(`    \x1b[31m↳ ${msg}\x1b[0m`);
const success = (msg) => console.log(`    \x1b[32m↳ ${msg}\x1b[0m`);

function randomAesKey(len = 16) {
  let k = '';
  for (let i = 0; i < len; i++) k += KEY_CHARS[crypto.randomBytes(1)[0] % KEY_CHARS.length];
  return k;
}

function aesEncrypt(plaintext, aesKey) {
  const cipher = crypto.createCipheriv('aes-128-cbc', Buffer.from(aesKey), AES_IV);
  cipher.setAutoPadding(true);
  let enc = cipher.update(plaintext, 'utf8');
  enc = Buffer.concat([enc, cipher.final()]);
  return enc.toString('base64');
}

function rsaEncrypt(dataB64, pem) {
  const buf = Buffer.from(dataB64, 'utf8');
  const encrypted = crypto.publicEncrypt({ key: pem, padding: crypto.constants.RSA_PKCS1_PADDING }, buf);
  return encrypted.toString('base64');
}

function encryptCaptchaPayload(payload) {
  const aesKey = randomAesKey();
  const json = JSON.stringify(payload);
  const d = aesEncrypt(json, aesKey);
  const keyB64 = Buffer.from(aesKey).toString('base64');
  const s = rsaEncrypt(keyB64, CAPTCHA_RSA_PEM);
  return { s, d };
}

function encryptFormFields(fields) {
  const aesKey = randomAesKey();
  const enc = {};
  for (const [name, val] of Object.entries(fields)) {
    enc[name] = aesEncrypt(val, aesKey);
  }
  const keyB64 = Buffer.from(aesKey).toString('base64');
  const rsaEnc = rsaEncrypt(keyB64, EUI_RSA_PEM);
  const fieldNames = Buffer.from(Object.keys(fields).join(',')).toString('base64');
  return { EUI: `${rsaEnc}.${fieldNames}`, encryptedParams: enc };
}

function maskEmail(email) {
  const [local, domain] = email.split('@');
  return local.length > 3 ? `${local.slice(0, 3)}***@${domain}` : `***@${domain}`;
}

// ─── HTTP ───────────────────────────────────────────────────────────────────

class Session {
  constructor() {
    this.cookies = {};
    this.ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36';
  }

  _parseCookies(headers) {
    const sc = headers['set-cookie'];
    if (!sc) return;
    for (const c of (Array.isArray(sc) ? sc : [sc])) {
      const [kv] = c.split(';');
      const [k, ...v] = kv.split('=');
      this.cookies[k.trim()] = v.join('=').trim();
    }
  }

  cookieStr() {
    return Object.entries(this.cookies).map(([k, v]) => `${k}=${v}`).join('; ');
  }

  async get(url, opts = {}) {
    const res = await fetch(url, {
      method: 'GET',
      headers: { 'User-Agent': this.ua, Cookie: this.cookieStr(), ...opts.headers },
      redirect: 'manual',
    });
    this._parseCookies(Object.fromEntries(res.headers.entries()));
    return res;
  }

  async post(url, body, opts = {}) {
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        'User-Agent': this.ua,
        Cookie: this.cookieStr(),
        ...opts.headers,
      },
      body,
      redirect: 'manual',
    });
    this._parseCookies(Object.fromEntries(res.headers.entries()));
    return res;
  }
}

// ─── STEPS ──────────────────────────────────────────────────────────────────

async function step1Warmup(session) {
  log(1, '⛔', 'Warming up register page...');
  const res = await session.get(REGISTER_URL);
  ok(`${res.status} ${res.status === 200 ? 'OK' : 'WARN'}`);
}

async function step2CaptchaData(session) {
  log(2, '🔑', 'Generating captcha fingerprint...');
  const payloadTemplate = JSON.parse(readFileSync(resolve(__dirname, 'capture/xiaomi/payload_template.json'), 'utf8'));
  const now = Date.now();
  payloadTemplate.startTs = now;
  payloadTemplate.endTs = now + Math.floor(Math.random() * 1000) + 500;
  payloadTemplate.env.p11 = now;
  payloadTemplate.nonce.t = Math.floor(now / 1000);
  payloadTemplate.nonce.r = Math.floor(Math.random() * 9000000000) + 1000000000;
  payloadTemplate.env.p33 = [];

  const { s, d } = encryptCaptchaPayload(payloadTemplate);
  const ts = Date.now();
  const url = `https://verify.sec.xiaomi.com/captcha/v2/data?k=${CAPTCHA_PARAM_K}&locale=en_US&_t=${ts}`;
  const body = `s=${encodeURIComponent(s)}&d=${encodeURIComponent(d)}&a=register`;
  const res = await session.post(url, body, { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } });
  const data = await res.json();
  if (data.code !== 0) throw new Error(`captcha/v2/data failed: ${JSON.stringify(data)}`);
  const eToken = new URL(data.data.url).searchParams.get('e');
  ok(`e_token: ${eToken.slice(0, 40)}...`);
  return eToken;
}

async function step3SolveCaptcha(session, eToken) {
  log(3, '🧩', 'Solving reCAPTCHA Enterprise...');
  const create = await session.post('https://api.2captcha.com/createTask', JSON.stringify({
    clientKey: CAPTCHA_API_KEY,
    task: {
      type: 'RecaptchaV2EnterpriseTaskProxyless',
      websiteURL: REGISTER_URL,
      websiteKey: CAPTCHA_SITE_KEY,
      enterprisePayload: { s: eToken },
    },
  }), { headers: { 'Content-Type': 'application/json' } });
  const createData = await create.json();
  if (createData.errorId) throw new Error(`2Captcha: ${createData.errorDescription}`);
  ok(`Task #${createData.taskId} submitted`);

  for (let i = 0; i < 60; i++) {
    await sleep(5000);
    const poll = await session.post('https://api.2captcha.com/getTaskResult', JSON.stringify({
      clientKey: CAPTCHA_API_KEY, taskId: createData.taskId,
    }), { headers: { 'Content-Type': 'application/json' } });
    const pollData = await poll.json();
    if (pollData.status === 'ready') {
      success('Solved ✓');
      return pollData.solution.gRecaptchaResponse;
    }
    if (pollData.errorId) throw new Error(`2Captcha: ${pollData.errorDescription}`);
    process.stdout.write(`    ↳ Polling... (attempt ${i + 1}/60)\r`);
  }
  throw new Error('2Captcha timeout');
}

async function step4Verify(session, eToken, g) {
  log(4, '✅', 'Verifying captcha...');
  const ts = Date.now();
  const url = `https://verify.sec.xiaomi.com/captcha/v2/recaptcha/verify?k=${CAPTCHA_PARAM_K}&locale=en_US&_t=${ts}`;
  const body = `e=${encodeURIComponent(eToken)}&g=${encodeURIComponent(g)}&type=4`;
  const res = await session.post(url, body, { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } });
  const data = await res.json();
  if (data.code !== 0 || !data.data?.result) throw new Error(`verify failed: ${JSON.stringify(data)}`);
  ok('vToken obtained');
  return data.data.token;
}

async function step5Encrypt(email, password) {
  log(5, '🔒', 'Encrypting credentials (EUI)...');
  const { EUI, encryptedParams } = encryptFormFields({ email, password });
  ok(`EUI: ${EUI.slice(0, 50)}...`);
  return { EUI, encEmail: encryptedParams.email, encPass: encryptedParams.password };
}

async function step6SendTicket(session, vtoken, eui, encEmail, encPass, email) {
  log(6, '📧', 'Sending registration ticket...');
  const deviceId = `wb_${crypto.randomUUID()}`;
  session.cookies.vToken = vtoken;
  session.cookies.vAction = 'register';
  session.cookies.deviceId = deviceId;

  const body = `email=${encodeURIComponent(encEmail)}&password=${encodeURIComponent(encPass)}&region=ID&sid=&icode=`;
  const res = await session.post('https://global.account.xiaomi.com/pass/sendEmailRegTicket', body, {
    headers: {
      'eui': eui,
      'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
      'X-Requested-With': 'XMLHttpRequest',
      'Referer': REGISTER_URL,
      'Origin': 'https://global.account.xiaomi.com',
    },
  });
  let text = await res.text();
  if (text.startsWith('&&&START&&&')) text = text.slice(11);
  const data = JSON.parse(text);
  if (data.code !== 0) throw new Error(`sendEmailRegTicket: ${JSON.stringify(data)}`);
  ok(`Code sent to ${maskEmail(email)}`);
  return data;
}

async function step7ReadCode(email, timeoutSec = 120) {
  log(7, '📬', `Reading verification code from IMAP...`);
  info(`Waiting for email... (${timeoutSec}s timeout)`);
  const deadline = Date.now() + timeoutSec * 1000;

  while (Date.now() < deadline) {
    let client;
    try {
      client = new ImapFlow({ host: IMAP_HOST, port: 993, secure: true, auth: { user: IMAP_USER, pass: IMAP_PASS }, logger: false });
      await client.connect();
      const lock = await client.getMailboxLock('INBOX');
      try {
        const msgs = [];
        for await (const m of client.fetch({ unseen: true, from: 'noreply@notice.xiaomi.com' }, { envelope: true, source: true })) msgs.push(m);
        for (const m of msgs.reverse()) {
          const to = (m.envelope?.to || []).map((a) => a.address?.toLowerCase()).join(',');
          if (!to.includes(email.toLowerCase())) continue;
          const raw = m.source?.toString('utf8') || '';
          const body = raw.replace(/=\r?\n/g, '').replace(/<[^>]+>/g, ' ');
          const mm = body.match(/verification code is[:\s]*(\d{6})/i) || body.match(/verification code[^0-9]{0,20}(\d{6})/i);
          if (mm) {
            await client.messageFlagsAdd({ uid: m.uid }, ['\\Seen'], { uid: true });
            success(`Code: ${mm[1]}`);
            await client.logout();
            return mm[1];
          }
        }
      } finally { lock.release(); }
      await client.logout();
    } catch { try { await client?.logout(); } catch {} }
    await sleep(5000);
    process.stdout.write('    ↳ Waiting...\r');
  }
  throw new Error('Code timeout');
}

async function step8Verify(session, vtoken, code, email, password) {
  log(8, '🎯', 'Verifying & creating account...');
  const { EUI, encryptedParams } = encryptFormFields({ email, password });
  const deviceFp = crypto.randomBytes(16).toString('hex');
  const body = [
    `ticket=${code}`, `region=ID`, `email=${encodeURIComponent(encryptedParams.email)}`,
    `env=web`, `qs=%253Fsid%253Dpassport`, `isAcceptLicense=true`, `sid=`,
    `password=${encodeURIComponent(encryptedParams.password)}`, `policyName=globalmiaccount`,
    `callback=`, `deviceFingerprint=${deviceFp}`,
  ].join('&');

  const res = await session.post('https://global.account.xiaomi.com/pass/verifyEmailRegTicket', body, {
    headers: {
      'eui': EUI,
      'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
      'X-Requested-With': 'XMLHttpRequest',
    },
  });
  let text = await res.text();
  if (text.startsWith('&&&START&&&')) text = text.slice(11);
  const data = JSON.parse(text);
  if (data.code !== 0) throw new Error(`verifyEmailRegTicket: ${JSON.stringify(data)}`);
  success(`Account created! userId: ${data.userId}`);
  return data;
}

// ─── MIMO SSO + APPLY ───────────────────────────────────────────────────────

async function mimoLogin(session) {
  // Visit MiMo platform → triggers SSO redirect to Xiaomi → back with platform cookies
  log('SSO', '🔗', 'Logging into MiMo platform via Xiaomi SSO...');
  const res = await session.get(`${MIMO_BASE}/ultraspeed`);
  // Follow redirects manually
  let location = res.headers.get('location');
  let maxRedirects = 10;
  while (location && maxRedirects-- > 0) {
    const r = await session.get(location.startsWith('http') ? location : `${MIMO_BASE}${location}`);
    location = r.headers.get('location');
    if (r.status === 200) break;
  }
  const ph = session.cookies['api-platform_ph'];
  if (ph) {
    success(`api-platform_ph: ${ph.slice(0, 20)}...`);
    return ph;
  }
  throw new Error('SSO login failed — no api-platform_ph cookie');
}

async function applyUltraSpeed(ph, account) {
  log('APPLY', '🚀', 'Applying for UltraSpeed Beta...');
  const session = new Session();
  session.cookies['api-platform_ph'] = ph;
  session.cookies['userId'] = account.userId || '';

  const body = JSON.stringify({
    name: account.name || 'Steven Harris',
    phone: account.phone || '+628123456789',
    email: account.email,
    company: account.company || 'GraceTech Solutions',
    industry: account.industry || '互联网',
    appInfo: account.useCase || 'Coding Agent / 代码生成',
    additionalInfo: account.additionalInfo || 'Building AI-powered coding agents. UltraSpeed 1000 tok/s for real-time code generation.',
  });

  const res = await session.post(
    `${MIMO_BASE}/api/v1/mimo-speed/apply?api-platform_ph=${encodeURIComponent(ph)}`,
    body,
    { headers: { 'Content-Type': 'application/json', 'Origin': MIMO_BASE, 'Referer': MIMO_ULTRASPEED } },
  );

  let text = await res.text();
  try { text = JSON.parse(text); } catch {}
  if (typeof text === 'object' && text.code === 0) {
    success('UltraSpeed application submitted!');
    return text;
  }
  throw new Error(`Apply failed: ${JSON.stringify(text)}`);
}

// ─── FULL FLOW ──────────────────────────────────────────────────────────────

export async function applyUltraSpeedFull(account) {
  const { email, password } = account;
  const session = new Session();

  console.log('\n' + '━'.repeat(60));
  console.log(' 🚀 MiMo UltraSpeed — Auto Apply');
  console.log('━'.repeat(60));

  // Register account
  await step1Warmup(session);

  // Cleanup old emails
  try {
    const client = new ImapFlow({ host: IMAP_HOST, port: 993, secure: true, auth: { user: IMAP_USER, pass: IMAP_PASS }, logger: false });
    await client.connect();
    const lock = await client.getMailboxLock('INBOX');
    try {
      let count = 0;
      for await (const m of client.fetch({ unseen: true, from: 'noreply@notice.xiaomi.com' }, { uid: true })) {
        await client.messageFlagsAdd({ uid: m.uid }, ['\\Seen'], { uid: true });
        count++;
      }
      if (count) info(`${count} stale emails marked read`);
    } finally { lock.release(); }
    await client.logout();
  } catch {}

  // Captcha solve + verify (retry 4x)
  let vtoken;
  for (let attempt = 0; attempt < 4; attempt++) {
    try {
      const eToken = await step2CaptchaData(session);
      const g = await step3SolveCaptcha(session, eToken);
      vtoken = await step4Verify(session, eToken, g);
      break;
    } catch (e) {
      err(`${e.message} — retrying (${attempt + 1}/4)`);
      if (attempt === 3) throw e;
      await sleep(2000);
    }
  }

  const { EUI, encEmail, encPass } = await step5Encrypt(email, password);
  await step6SendTicket(session, vtoken, EUI, encEmail, encPass, email);
  const code = await step7ReadCode(email);
  const regResult = await step8Verify(session, vtoken, code, email, password);

  // SSO into MiMo
  const ph = await mimoLogin(session);

  // Apply for UltraSpeed
  const applyResult = await applyUltraSpeed(ph, { ...account, userId: regResult.userId });

  console.log('\n' + '━'.repeat(60));
  console.log(' ✨ Done');
  console.log('━'.repeat(60));
  console.log(`    Email:     ${email}`);
  console.log(`    UserId:    ${regResult.userId}`);
  console.log('━'.repeat(60));

  return { email, password, userId: regResult.userId, applied: true };
}

// ─── CLI ────────────────────────────────────────────────────────────────────

async function main() {
  const args = process.argv.slice(2);
  const getArg = (flag) => { const i = args.indexOf(flag); return i >= 0 ? args[i + 1] : null; };

  if (getArg('--batch')) {
    // Batch mode
    const file = getArg('--batch');
    const lines = readFileSync(resolve(__dirname, file), 'utf8').split('\n').filter(Boolean);
    const accounts = lines.map((l) => JSON.parse(l));
    const existing = new Set();
    const appliedFile = resolve(__dirname, 'applied.jsonl');
    if (existsSync(appliedFile)) {
      readFileSync(appliedFile, 'utf8').split('\n').filter(Boolean).forEach((l) => {
        try { existing.add(JSON.parse(l).email?.toLowerCase()); } catch {}
      });
    }
    const pending = accounts.filter((a) => !existing.has(a.email?.toLowerCase()));
    console.log(`\n📋 ${accounts.length} total, ${existing.size} already applied, ${pending.length} pending\n`);
    for (let i = 0; i < pending.length; i++) {
      const a = pending[i];
      console.log(`\n[${i + 1}/${pending.length}] 🔵 ${a.email}`);
      try {
        const result = await applyUltraSpeedFull(a);
        appendFileSync(appliedFile, JSON.stringify(result) + '\n');
        console.log(`[${i + 1}/${pending.length}] ✅ ${a.email}`);
      } catch (e) {
        console.log(`[${i + 1}/${pending.length}] ❌ ${a.email}: ${e.message}`);
      }
      if (i < pending.length - 1) { console.log(`\n⏳ Sleeping 10s...`); await sleep(10000); }
    }
    return;
  }

  // Single mode
  const email = getArg('--email') || process.env.EMAIL || '';
  const password = getArg('--password') || process.env.DEFAULT_PASSWORD || '';

  if (!email || !password) {
    console.error('Usage: node apply.js --email X --password Y');
    console.error('   or: node apply.js --batch accounts.jsonl');
    console.error('   or: set EMAIL + DEFAULT_PASSWORD in .env');
    process.exit(1);
  }

  try {
    await applyUltraSpeedFull({ email, password });
  } catch (e) {
    err(`Failed: ${e.message}`);
    process.exit(1);
  }
}

main();
