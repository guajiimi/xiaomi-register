#!/usr/bin/env node
const cookies = {
  passToken: 'V1:DXmurwq2/R1BHTELu6obCf5SEsEWzHG7hDkYw6Ue2BSwOcbNIEoKQlx5n70Y7/pyJIodm3U5ZhfJRJTZUu87C0uMd0f2IyIabIpm3J829R18J5LY+bnrySmg5ND9QWoTtccXyarHQ3faiuNyq6QxH5OD5ocISN0s1ESECcJHocMcTf7LnIVa46I1eka41CSk7uWIrFxPzuir80x7t+C/a5ql4U05iooGR3rDutspmyM1VqDCBNYVqlBOB6YWZkLTKFdj31O/LrCWN/Os66eMoSrK5BmFGvWXMsf9gJSkVDswUI5b0kgsrEljRJbX/ZqFSYnH+A6RPFooK3ToSwwICA==',
  cUserId: '_-y893NG8_Gnh-l99qkvQ35w4JM',
  userId: '6876448492'
};
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36';
const MIMO = 'https://platform.xiaomimimo.com';

class Session {
  constructor() { this.cookies = { ...cookies }; }
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

async function followRedirects(s, url) {
  let steps = 15;
  while (url && steps-- > 0) {
    const full = url.startsWith('http') ? url : `${MIMO}${url}`;
    const r = await s.get(full);
    const loc = r.headers.get('location');
    if (r.status >= 200 && r.status < 300) return r;
    if (r.status >= 300 && r.status < 400) { url = loc; continue; }
    // Check JS redirect
    const body = await r.text();
    const m = body.match(/window\.location(?:\.href)?\s*=\s*["']([^"']+)["']/);
    if (m) { url = m[1]; continue; }
    return r;
  }
}

async function main() {
  const s = new Session();

  // Step 1: Visit /api/v1/mimo-speed/apply directly — this gives us the CORRECT sign for this endpoint
  console.log('Step 1: Get correct SSO sign for apply endpoint...');
  const applyCheck = await s.get(`${MIMO}/api/v1/mimo-speed/apply`, {
    headers: { 'Accept': 'application/json' }
  });
  const applyCheckData = await applyCheck.json();
  console.log(`Apply check: ${applyCheck.status}`, JSON.stringify(applyCheckData).substring(0, 200));
  
  // The loginUrl from 401 contains the correct sign
  if (applyCheckData.code === 401 && applyCheckData.loginUrl) {
    console.log('\nStep 2: Follow the correct SSO loginUrl...');
    const loginUrl = applyCheckData.loginUrl;
    console.log(`  loginUrl: ${loginUrl.substring(0, 150)}...`);
    
    // Follow this loginUrl with Xiaomi cookies
    let r = await s.get(loginUrl);
    let url = r.headers.get('location');
    console.log(`  -> ${r.status} ${url?.substring(0, 120) || 'no redirect'}`);
    
    let steps = 15;
    while (url && steps-- > 0) {
      const full = url.startsWith('http') ? url : `https://account.xiaomi.com${url}`;
      r = await s.get(full);
      const loc = r.headers.get('location');
      console.log(`  -> ${r.status} ${loc?.substring(0, 120) || 'body'} | cookies: ${Object.keys(s.cookies).length}`);
      
      if (r.status >= 300 && r.status < 400) {
        url = loc;
      } else {
        const body = await r.text();
        const m = body.match(/window\.location(?:\.href)?\s*=\s*["']([^"']+)["']/);
        if (m) { url = m[1]; console.log(`  JS: ${url.substring(0, 100)}`); }
        else break;
      }
    }
    
    console.log(`\nFinal cookies: ${Object.keys(s.cookies).join(', ')}`);
    const ph = (s.cookies['api-platform_ph'] || '').replace(/^"|"$/g, '');
    console.log(`ph: ${ph}`);
    
    // Now try apply again
    console.log('\nStep 3: Apply UltraSpeed (with correct session)...');
    const applyRes = await s.post(
      `${MIMO}/api/v1/mimo-speed/apply`,
      JSON.stringify({
        name: 'Nico Setiawan',
        phone: '+628****5678',
        email: 'nicosetiawan@jimixz.tech',
        company: 'Jimixz Tech',
        industry: '互联网',
        appInfo: 'Coding Agent / 代码生成',
        additionalInfo: 'Building AI coding agents for production. Need UltraSpeed 1000 tok/s.'
      }),
      { headers: {
        'Content-Type': 'application/json',
        'Origin': MIMO,
        'Referer': `${MIMO}/ultraspeed`,
        'Accept': 'application/json'
      }}
    );
    const applyText = await applyRes.text();
    console.log(`Apply status: ${applyRes.status}`);
    console.log(`Apply response: ${applyText.substring(0, 500)}`);
    
    // Also fetch referral code
    console.log('\nReferral code...');
    const refRes = await s.get(`${MIMO}/api/v1/invitation/code`, { headers: { 'Accept': 'application/json' } });
    const refData = await refRes.json();
    console.log(JSON.stringify(refData, null, 2));
    
    // Final output
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
      appliedAt: new Date().toISOString()
    };
    
    console.log('\n' + '='.repeat(60));
    console.log('📄 FINAL JSON:');
    console.log(JSON.stringify(output, null, 2));
  }
}

main().catch(e => console.error('Error:', e.message));
