#!/usr/bin/env node
const crypto = require('crypto');
const { ImapFlow } = require('imapflow');

const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36';
const MIMO = 'https://platform.xiaomimimo.com';
const EMAIL = 'nicosetiawan@jimixz.tech';
const PASS = 'jimixz123!';
const IMAP_USER = 'stevenharis78@gmail.com';
const IMAP_PASS = 'wtkx ntyr fwda plit';
const AES_IV = Buffer.from('0102030405060708');
const KEY_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*';
const EUI_RSA_PEM = `-----BEGIN PUBLIC KEY-----\nMIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCYEVrK/4Mahiv0pUJgTybx4J9P\n5dUT/Y0PuwMbk+gMU+jrZnBiXGv6/hCH1avIhoBcE535F8nJQQN3UavZdFkYidso\nXuEnat3+eVTp3FslyhRwIBDF09v4vDhRtxFOT+R7uH7h/mzmyA2/+lfIMWGIrffX\nprYizbV76+YQKhoqFQIDAQAB\n-----END PUBLIC KEY-----`;

class Session {
  constructor() { this.cookies = {}; }
  cookieStr() { return Object.entries(this.cookies).map(([k, v]) => `${k}=${v}`).join('; '); }
  async get(url, opts = {}) {
    const res = await fetch(url, { method: 'GET', headers: { 'User-Agent': UA, Cookie: this.cookieStr(), ...opts.headers }, redirect: 'manual' });
    this._parse(res); return res;
  }
  async post(url, body, opts = {}) {
    const res = await fetch(url, { method: 'POST', headers: { 'User-Agent': UA, Cookie: this.cookieStr(), ...opts.headers }, body, redirect: 'manual' });
    this._parse(res); return res;
  }
  _parse(res) {
    if (res.headers.getSetCookie) {
      for (const c of res.headers.getSetCookie()) {
        const [kv] = c.split(';'); const [k, ...v] = kv.split('=');
        this.cookies[k.trim()] = v.join('=').trim();
      }
    }
  }
}

function enc(fields) {
  const aesKey = randomAesKey();
  const enc = {};
  for (const [n, v] of Object.entries(fields)) enc[n] = aesEncrypt(v, aesKey);
  const keyB64 = Buffer.from(aesKey).toString('base64');
  const rsaEnc = rsaEncrypt(keyB64, EUI_RSA_PEM);
  const fn = Buffer.from(Object.keys(fields).join(',')).toString('base64');
  return { EUI: `${rsaEnc}.${fn}`, enc };
}
function randomAesKey(l=16){let k='';for(let i=0;i<l;i++)k+=KEY_CHARS[crypto.randomBytes(1)[0]%KEY_CHARS.length];return k}
function aesEncrypt(p,k){const c=crypto.createCipheriv('aes-128-cbc',Buffer.from(k),AES_IV);let e=c.update(p,'utf8');e=Buffer.concat([e,c.final()]);return e.toString('base64')}
function rsaEncrypt(d,p){return crypto.publicEncrypt({key:p,padding:crypto.constants.RSA_PKCS1_PADDING},Buffer.from(d,'utf8')).toString('base64')}

async function getCode() {
  return new Promise(async (resolve) => {
    const timeout = setTimeout(() => resolve(null), 25000);
    try {
      const client = new ImapFlow({ host: 'imap.gmail.com', port: 993, secure: true, auth: { user: IMAP_USER, pass: IMAP_PASS }, logger: false, connectionTimeout: 5000 });
      await client.connect();
      const lock = await client.getMailboxLock('INBOX');
      try {
        for await (const m of client.fetch({ unseen: true, since: new Date(Date.now() - 120000), from: 'noreply@notice.xiaomi.com' }, { source: true, uid: true })) {
          const raw = m.source?.toString('utf8') || '';
          const parts = raw.split('------=_Part_');
          for (const part of parts) {
            if (part.includes('text/html')) {
              const decoded = part.replace(/=\r?\n/g, '').replace(/=([0-9A-Fa-f]{2})/g, (_, h) => String.fromCharCode(parseInt(h, 16)));
              const text = decoded.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');
              const match = text.match(/verification code is[:\s]+(\d{6})/i) || text.match(/your verification code[:\s]+(\d{6})/i);
              if (match) {
                await client.messageFlagsAdd({ uid: m.uid }, ['\\Seen'], { uid: true });
                clearTimeout(timeout);
                await client.logout();
                return resolve(match[1]);
              }
            }
          }
        }
      } finally { lock.release(); }
      await client.logout();
    } catch (e) { console.log('IMAP error:', e.message); }
    clearTimeout(timeout);
    resolve(null);
  });
}

async function main() {
  console.log('=== MiMo UltraSpeed Apply ===\n');
  const s = new Session();

  // Step 1: SSO
  console.log('1. SSO...');
  const ssoUrl = 'https://account.xiaomi.com/pass/serviceLogin?callback=https%3A%2F%2Fplatform.xiaomimimo.com%2Fsts%3Fsign%3DcCRWVCC6g3tteb%252Fcnsfb4XS2Y1I%253D%26followup%3Dhttp%253A%252F%252Fplatform.xiaomimimo.com%252F&sid=api-platform&_group=DEFAULT';
  let r = await s.get(ssoUrl);
  const loc = r.headers.get('location') || '';
  console.log(`  ${r.status}`);

  // Step 2: Login
  console.log('2. Login...');
  const { EUI, enc: encParams } = enc({ email: EMAIL, password: PASS });
  r = await s.get(loc.startsWith('http') ? loc : `https://account.xiaomi.com${loc}`);
  const signMatch = (loc + (r.headers.get('location') || '')).match(/_sign=([^&]+)/);
  const sign = signMatch ? decodeURIComponent(signMatch[1]) : '';
  
  const loginRes = await s.post('https://account.xiaomi.com/pass/serviceLoginAuth',
    new URLSearchParams({ _json: 'true', qs: '%3Fcallback%3Dhttps%253A%252F%252Fplatform.xiaomimimo.com%252Fsts%253Fsign%253DcCRWVCC6g3tteb%25252Fcnsfb4XS2Y1I%25253D%2526followup%253Dhttp%25253A%25252F%25252Fplatform.xiaomimimo.com%25252F&sid=api-platform&_group=DEFAULT', sid: 'api-platform', _sign: sign, user: encParams.email, hash: encParams.password, callback: 'https://platform.xiaomimimo.com/sts?sign=cCRWVCC6g3tteb%2Fcnsfb4XS2Y1I%3D&followup=http%3A%2F%2Fplatform.xiaomimimo.com%2F', _locale: 'en' }).toString(),
    { headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'eui': EUI } }
  );
  let lt = await loginRes.text();
  if (lt.startsWith('&&&START&&&')) lt = lt.slice(11);
  let ld; try { ld = JSON.parse(lt); } catch { ld = { raw: lt }; }
  console.log(`  code=${ld.code} desc=${ld.desc || ''}`);

  // Step 3: Verification
  if (ld.code === 70016 || ld.notificationUrl) {
    console.log('3. Verification...');
    await s.post('https://account.xiaomi.com/pass/sendEmailLoginTicket',
      new URLSearchParams({ _json: 'true', sid: 'api-platform', mix: ld.mix || '' }).toString(),
      { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }
    );
    console.log('  Waiting 15s...');
    await new Promise(r => setTimeout(r, 15000));
    const code = await getCode();
    console.log(`  Code: ${code}`);
    if (!code) { console.log('  ❌ No code'); return; }
    
    const vr = await s.post('https://account.xiaomi.com/pass/verifyEmailLoginTicket',
      new URLSearchParams({ _json: 'true', sid: 'api-platform', ticket: code, mix: ld.mix || '' }).toString(),
      { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }
    );
    let vt = await vr.text();
    if (vt.startsWith('&&&START&&&')) vt = vt.slice(11);
    let vd; try { vd = JSON.parse(vt); } catch { vd = { raw: vt }; }
    console.log(`  Verify: code=${vd.code}`);
    
    if (vd.location) {
      let url = vd.location;
      let steps = 15;
      while (url && steps-- > 0) {
        r = await s.get(url.startsWith('http') ? url : `https://account.xiaomi.com${url}`);
        const l = r.headers.get('location');
        if (r.status >= 300 && r.status < 400) url = l;
        else {
          const b = await r.text();
          const m = b.match(/window\.location(?:\.href)?\s*=\s*["']([^"']+)["']/);
          if (m) url = m[1]; else break;
        }
      }
    }
  }

  const ph = (s.cookies['api-platform_ph'] || '').replace(/^"|"$/g, '');
  console.log(`\n  ph: ${ph ? 'OK' : 'MISSING'}`);
  if (!ph) { console.log('Cookies:', Object.keys(s.cookies).join(', ')); return; }

  // Step 4: Referral
  console.log('\n4. Referral...');
  const refRes = await s.get(`${MIMO}/api/v1/invitation/code`, { headers: { 'Accept': 'application/json' } });
  const refData = await refRes.json();
  console.log(`  ${JSON.stringify(refData)}`);

  // Step 5: Apply
  console.log('\n5. Apply UltraSpeed...');
  const applyRes = await s.post(`${MIMO}/api/v1/mimo-speed/apply`, JSON.stringify({
    name: 'Nico Setiawan', phone: '+628****5678', email: EMAIL,
    company: 'Jimixz Tech', industry: '互联网',
    appInfo: 'Coding Agent / 代码生成',
    additionalInfo: 'Building AI coding agents. Need UltraSpeed 1000 tok/s.',
  }), { headers: { 'Content-Type': 'application/json', 'Accept': 'application/json', 'Origin': MIMO, 'Referer': `${MIMO}/ultraspeed` } });
  const applyText = await applyRes.text();
  console.log(`  Status: ${applyRes.status}`);
  console.log(`  Response: ${applyText.substring(0, 500)}`);

  let ar; try { ar = JSON.parse(applyText); } catch { ar = { raw: applyText }; }
  const output = {
    email: EMAIL, userId: '6876448492',
    referralCode: refData.data?.invitationCode || null,
    referralReward: refData.data?.rewardAmount || null,
    referralCurrency: refData.data?.currency || null,
    maxInvites: refData.data?.maxInviteeCount || null,
    referralUrl: refData.data?.invitationCode ? `${MIMO}?ref=${refData.data.invitationCode}` : null,
    ultraSpeedApplied: ar.code === 0, ultraSpeedResponse: ar,
    appliedAt: new Date().toISOString(),
  };
  console.log('\n' + '='.repeat(60));
  console.log('📄 FINAL JSON:');
  console.log(JSON.stringify(output, null, 2));
}

main().catch(e => console.error('Error:', e.message));
