#!/usr/bin/env node
/**
 * Full flow: Login → Accept Terms → Apply UltraSpeed
 */
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36';
const MIMO = 'https://platform.xiaomimimo.com';

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

async function main() {
  const s = new Session();

  // Step 1: Login via Xiaomi SSO
  console.log('Step 1: SSO login...');
  const ssoUrl = 'https://account.xiaomi.com/pass/serviceLogin?callback=https%3A%2F%2Fplatform.xiaomimimo.com%2Fsts%3Fsign%3DcCRWVCC6g3tteb%252Fcnsfb4XS2Y1I%253D%26followup%3Dhttp%253A%252F%252Fplatform.xiaomimimo.com%252Fconsole&sid=api-platform&_group=DEFAULT';
  
  // Set Xiaomi cookies
  s.cookies['passToken'] = 'V1:DXmurwq2/R1BHTELu6obCf5SEsEWzHG7hDkYw6Ue2BSwOcbNIEoKQlx5n70Y7/pyJIodm3U5ZhfJRJTZUu87C0uMd0f2IyIabIpm3J829R18J5LY+bnrySmg5ND9QWoTtccXyarHQ3faiuNyq6QxH5OD5ocISN0s1ESECcJHocMcTf7LnIVa46I1eka41CSk7uWIrFxPzuir80x7t+C/a5ql4U05iooGR3rDutspmyM1VqDCBNYVqlBOB6YWZkLTKFdj31O/LrCWN/Os66eMoSrK5BmFGvWXMsf9gJSkVDswUI5b0kgsrEljRJbX/ZqFSYnH+A6RPFooK3ToSwwICA==';
  s.cookies['cUserId'] = '_-y893NG8_Gnh-l99qkvQ35w4JM';
  s.cookies['userId'] = '6876448492';
  
  let r = await s.get(ssoUrl);
  let url = r.headers.get('location');
  console.log(`  SSO: ${r.status} → ${url?.substring(0, 100) || 'no redirect'}`);
  
  // Follow SSO chain
  let steps = 15;
  while (url && steps-- > 0) {
    const full = url.startsWith('http') ? url : `https://account.xiaomi.com${url}`;
    r = await s.get(full);
    const loc = r.headers.get('location');
    console.log(`  ${r.status} ${full.substring(0, 100)}...`);
    if (r.status >= 300 && r.status < 400) { url = loc; }
    else {
      const body = await r.text();
      const m = body.match(/window\.location(?:\.href)?\s*=\s*["']([^"']+)["']/);
      if (m) { url = m[1]; console.log(`  JS redirect: ${url.substring(0, 100)}`); }
      else break;
    }
  }
  
  const ph = (s.cookies['api-platform_ph'] || '').replace(/^"|"$/g, '');
  const st = (s.cookies['api-platform_serviceToken'] || '').replace(/^"|"$/g, '');
  console.log(`  ph: ${ph ? ph.substring(0, 20) + '...' : 'MISSING'}`);
  console.log(`  serviceToken: ${st ? st.substring(0, 20) + '...' : 'MISSING'}`);
  
  if (!ph) {
    console.log('❌ SSO failed — no ph cookie');
    return;
  }
  
  // Step 2: Check current user info & agreement status
  console.log('\nStep 2: Check user info...');
  const infoRes = await s.get(`${MIMO}/api/v1/user/info`, { headers: { 'Accept': 'application/json' } });
  const infoData = await infoRes.json().catch(() => ({}));
  console.log(`User info: ${JSON.stringify(infoData).substring(0, 300)}`);
  
  // Step 3: Accept Terms & Agreements
  console.log('\nStep 3: Accept Terms...');
  // Try different endpoints for accepting terms
  for (const endpoint of [
    '/api/v1/user/agreement',
    '/api/v1/agreement/accept',
    '/api/v1/user/agreement/accept',
    '/api/v1/agreement',
  ]) {
    const termRes = await s.post(`${MIMO}${endpoint}`, JSON.stringify({ accepted: true }), {
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' }
    });
    const termText = await termRes.text();
    console.log(`  POST ${endpoint}: ${termRes.status} ${termText.substring(0, 100)}`);
    if (termRes.status !== 404) break;
  }
  
  // Step 4: Fetch referral code
  console.log('\nStep 4: Referral code...');
  const refRes = await s.get(`${MIMO}/api/v1/invitation/code`, { headers: { 'Accept': 'application/json' } });
  const refData = await refRes.json();
  console.log(`  ${JSON.stringify(refData)}`);
  
  // Step 5: Apply UltraSpeed
  console.log('\nStep 5: Apply UltraSpeed...');
  const applyBody = JSON.stringify({
    name: 'Nico Setiawan',
    phone: '+62812345678',
    email: 'nicosetiawan@jimixz.tech',
    company: 'Jimixz Tech',
    industry: '互联网',
    appInfo: 'Coding Agent / 代码生成',
    additionalInfo: 'Building AI coding agents for production. Need UltraSpeed 1000 tok/s for real-time code generation.',
    agreement: true,
    isAcceptAgreement: true,
    agreeService: true,
  });
  
  const applyRes = await s.post(`${MIMO}/api/v1/mimo-speed/apply`, applyBody, {
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
  
  // Step 6: Try with serviceToken in Authorization header
  console.log('\nStep 6: Try with Bearer token...');
  const applyRes2 = await s.post(`${MIMO}/api/v1/mimo-speed/apply`, applyBody, {
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
      'Origin': MIMO,
      'Referer': `${MIMO}/ultraspeed`,
      'Authorization': `Bearer ${st}`,
    }
  });
  const applyText2 = await applyRes2.text();
  console.log(`  Status: ${applyRes2.status}`);
  console.log(`  Response: ${applyText2.substring(0, 500)}`);
  
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
    appliedAt: new Date().toISOString(),
  };
  
  console.log('\n' + '='.repeat(60));
  console.log('📄 FINAL JSON:');
  console.log(JSON.stringify(output, null, 2));
}

main().catch(e => console.error('Error:', e.message));
