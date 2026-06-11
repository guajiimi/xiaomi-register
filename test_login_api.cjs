#!/usr/bin/env node
/**
 * Login via Xiaomi API → SSO to MiMo → Accept Terms → Apply UltraSpeed
 * Uses the same approach as the browser but via pure API calls
 */
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36';
const MIMO = 'https://platform.xiaomimimo.com';
const { ImapFlow } = require('imapflow');

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

async function getCode() {
  const client = new ImapFlow({ host: 'imap.gmail.com', port: 993, secure: true, auth: { user: 'stevenharis78@gmail.com', pass: 'wtkx ntyr fwda plit' }, logger: false, connectionTimeout: 10000 });
  await client.connect();
  const lock = await client.getMailboxLock('INBOX');
  try {
    for await (const m of client.fetch({ unseen: true, from: 'noreply@notice.xiaomi.com' }, { envelope: true, source: true })) {
      const raw = m.source?.toString('utf8') || '';
      const body = raw.replace(/=\r?\n/g, '').replace(/<[^>]+>/g, ' ');
      const mm = body.match(/(\d{6})/);
      if (mm) {
        await client.messageFlagsAdd({ uid: m.uid }, ['\\Seen'], { uid: true });
        return mm[1];
      }
    }
  } finally { lock.release(); }
  await client.logout();
  return null;
}

async function markAllRead() {
  const client = new ImapFlow({ host: 'imap.gmail.com', port: 993, secure: true, auth: { user: 'stevenharis78@gmail.com', pass: 'wtkx ntyr fwda plit' }, logger: false, connectionTimeout: 10000 });
  await client.connect();
  const lock = await client.getMailboxLock('INBOX');
  try {
    for await (const m of client.fetch({ unseen: true, from: 'noreply@notice.xiaomi.com' }, { uid: true })) {
      await client.messageFlagsAdd({ uid: m.uid }, ['\\Seen'], { uid: true });
    }
  } finally { lock.release(); }
  await client.logout();
}

async function main() {
  console.log('=== MiMo UltraSpeed Auto Apply ===\n');
  
  // Mark old emails read
  console.log('Marking old emails read...');
  await markAllRead();
  
  // Step 1: Initiate SSO login
  console.log('Step 1: SSO login...');
  const s = new Session();
  const ssoUrl = 'https://account.xiaomi.com/pass/serviceLogin?callback=https%3A%2F%2Fplatform.xiaomimimo.com%2Fsts%3Fsign%3DcCRWVCC6g3tteb%252Fcnsfb4XS2Y1I%253D%26followup%3Dhttp%253A%252F%252Fplatform.xiaomimimo.com%252F&sid=api-platform&_group=DEFAULT';
  
  let r = await s.get(ssoUrl);
  console.log(`  serviceLogin: ${r.status}`);
  
  // Step 2: Submit login credentials
  console.log('Step 2: Submit credentials...');
  // Get the _sign from the login page URL
  const loginPageUrl = r.headers.get('location') || '';
  const signMatch = loginPageUrl.match(/_sign=([^&]+)/);
  const sign = signMatch ? decodeURIComponent(signMatch[1]) : '';
  
  // Submit login form
  const loginBody = new URLSearchParams({
    _json: 'true',
    qs: '%3Fcallback%3Dhttps%253A%252F%252Fplatform.xiaomimimo.com%252Fsts%253Fsign%253DcCRWVCC6g3tteb%25252Fcnsfb4XS2Y1I%25253D%2526followup%253Dhttp%25253A%25252F%25252Fplatform.xiaomimimo.com%25252F&sid=api-platform&_group=DEFAULT',
    sid: 'api-platform',
    _sign: sign,
    user: 'nicosetiawan@jimixz.tech',
    hash: 'JIMIXZ123!', // Will be hashed by the server
  }).toString();
  
  // Actually, need to encrypt password like the browser does
  // Use the EUI encryption from apply.js
  const crypto = require('crypto');
  const AES_IV = Buffer.from('0102030405060708');
  const KEY_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*';
  
  const EUI_RSA_PEM = `-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCYEVrK/4Mahiv0pUJgTybx4J9P
5dUT/Y0PuwMbk+gMU+jrZnBiXGv6/hCH1avIhoBcE535F8nJQQN3UavZdFkYidso
XuEnat3+eVTp3FslyhRwIBDF09v4vDhRtxFOT+R7uH7h/mzmyA2/+lfIMWGIrffX
prYizbV76+YQKhoqFQIDAQAB
-----END PUBLIC KEY-----`;

  function randomAesKey(len = 16) {
    let k = '';
    for (let i = 0; i < len; i++) k += KEY_CHARS[crypto.randomBytes(1)[0] % KEY_CHARS.length];
    return k;
  }

  function aesEncrypt(plaintext, aesKey) {
    const cipher = crypto.createCipheriv('aes-128-cbc', Buffer.from(aesKey), AES_IV);
    let enc = cipher.update(plaintext, 'utf8');
    enc = Buffer.concat([enc, cipher.final()]);
    return enc.toString('base64');
  }

  function rsaEncrypt(dataB64, pem) {
    const buf = Buffer.from(dataB64, 'utf8');
    const encrypted = crypto.publicEncrypt({ key: pem, padding: crypto.constants.RSA_PKCS1_PADDING }, buf);
    return encrypted.toString('base64');
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
  
  const { EUI, encryptedParams } = encryptFormFields({ email: 'nicosetiawan@jimixz.tech', password: 'jimixz123!' });
  
  const loginRes = await s.post('https://account.xiaomi.com/pass/serviceLoginAuth', 
    new URLSearchParams({
      _json: 'true',
      qs: '%3Fcallback%3Dhttps%253A%252F%252Fplatform.xiaomimimo.com%252Fsts%253Fsign%253DcCRWVCC6g3tteb%25252Fcnsfb4XS2Y1I%25253D%2526followup%253Dhttp%25253A%25252F%25252Fplatform.xiaomimimo.com%25252F&sid=api-platform&_group=DEFAULT',
      sid: 'api-platform',
      _sign: sign,
      user: encryptedParams.email,
      hash: encryptedParams.password,
      callback: 'https://platform.xiaomimimo.com/sts?sign=cCRWVCC6g3tteb%2Fcnsfb4XS2Y1I%3D&followup=http%3A%2F%2Fplatform.xiaomimimo.com%2F',
      _locale: 'en',
    }).toString(),
    { headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'eui': EUI } }
  );
  
  let loginText = await loginRes.text();
  if (loginText.startsWith('&&&START&&&')) loginText = loginText.slice(11);
  let loginData;
  try { loginData = JSON.parse(loginText); } catch { loginData = { raw: loginText }; }
  console.log(`  Login result: code=${loginData.code}, desc=${loginData.desc || loginData.description || ''}`);
  console.log(`  Cookies: ${Object.keys(s.cookies).join(', ')}`);
  
  // Check if verification needed
  if (loginData.code === 70016 || loginData.desc?.includes('verification') || loginData.notificationUrl) {
    console.log('  Verification needed! Sending code...');
    
    // Send verification code
    const sendRes = await s.post('https://account.xiaomi.com/pass/sendEmailLoginTicket',
      new URLSearchParams({
        _json: 'true',
        sid: 'api-platform',
        mix: loginData.mix || '',
      }).toString(),
      { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }
    );
    let sendText = await sendRes.text();
    if (sendText.startsWith('&&&START&&&')) sendText = sendText.slice(11);
    console.log(`  Send code result: ${sendText.substring(0, 200)}`);
    
    // Wait for email
    console.log('  Waiting for verification code...');
    await new Promise(r => setTimeout(r, 10000));
    const code = await getCode();
    console.log(`  Code: ${code}`);
    
    if (code) {
      // Submit verification code
      const verifyRes = await s.post('https://account.xiaomi.com/pass/verifyEmailLoginTicket',
        new URLSearchParams({
          _json: 'true',
          sid: 'api-platform',
          ticket: code,
          mix: loginData.mix || '',
        }).toString(),
        { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }
      );
      let verifyText = await verifyRes.text();
      if (verifyText.startsWith('&&&START&&&')) verifyText = verifyText.slice(11);
      let verifyData;
      try { verifyData = JSON.parse(verifyText); } catch { verifyData = { raw: verifyText }; }
      console.log(`  Verify result: code=${verifyData.code}`);
      console.log(`  Cookies: ${Object.keys(s.cookies).join(', ')}`);
      
      // Follow redirect to MiMo
      if (verifyData.location) {
        console.log(`  Following redirect: ${verifyData.location.substring(0, 100)}`);
        let r = await s.get(verifyData.location);
        let url = r.headers.get('location');
        let steps = 10;
        while (url && steps-- > 0) {
          r = await s.get(url.startsWith('http') ? url : `https://account.xiaomi.com${url}`);
          url = r.headers.get('location');
          if (r.status >= 200 && r.status < 300) break;
        }
      }
    }
  }
  
  // Check if we have MiMo cookies
  const ph = (s.cookies['api-platform_ph'] || '').replace(/^"|"$/g, '');
  const st = (s.cookies['api-platform_serviceToken'] || '').replace(/^"|"$/g, '');
  console.log(`\n  Final ph: ${ph ? ph.substring(0, 20) + '...' : 'MISSING'}`);
  console.log(`  Final serviceToken: ${st ? st.substring(0, 20) + '...' : 'MISSING'}`);
  
  if (!ph) {
    console.log('\n❌ No ph cookie. SSO failed.');
    console.log('All cookies:', JSON.stringify(s.cookies, null, 2));
    return;
  }
  
  // Step 3: Fetch referral code
  console.log('\nStep 3: Referral code...');
  const refRes = await s.get(`${MIMO}/api/v1/invitation/code`, { headers: { 'Accept': 'application/json' } });
  const refData = await refRes.json();
  console.log(`  ${JSON.stringify(refData)}`);
  
  // Step 4: Apply UltraSpeed
  console.log('\nStep 4: Apply UltraSpeed...');
  const applyRes = await s.post(`${MIMO}/api/v1/mimo-speed/apply`, JSON.stringify({
    name: 'Nico Setiawan',
    phone: '+628****5678',
    email: 'nicosetiawan@jimixz.tech',
    company: 'Jimixz Tech',
    industry: '互联网',
    appInfo: 'Coding Agent / 代码生成',
    additionalInfo: 'Building AI coding agents. Need UltraSpeed 1000 tok/s.',
  }), {
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
      'Origin': MIMO,
      'Referer': `${MIMO}/ultraspeed`,
    }
  });
  const applyText = await applyRes.text();
  console.log(`  Status: ${applyRes.status}`);
  console.log(`  Response: ${applyText.substring(0, 500)}`);
  
  // Final JSON
  let applyResult;
  try { applyResult = JSON.parse(applyText); } catch { applyResult = { raw: applyText }; }
  
  const output = {
    email: 'nicosetiawan@jimixz.tech',
    userId: '6876448492',
    referralCode: refData.data?.invitationCode || null,
    referralReward: refData.data?.rewardAmount || null,
    referralCurrency: refData.data?.currency || null,
    maxInvites: refData.data?.maxInviteeCount || null,
    referralUrl: refData.data?.invitationCode ? `${MIMO}?ref=${refData.data.invitationCode}` : null,
    ultraSpeedApplied: applyResult.code === 0,
    ultraSpeedResponse: applyResult,
    appliedAt: new Date().toISOString(),
  };
  
  console.log('\n' + '='.repeat(60));
  console.log('📄 FINAL JSON:');
  console.log(JSON.stringify(output, null, 2));
}

main().catch(e => { console.error('Error:', e.message); console.error(e.stack); });
