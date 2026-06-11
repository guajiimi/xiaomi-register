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

async function main() {
  const s = new Session();

  // SSO login
  console.log('SSO login...');
  const ssoUrl = 'https://account.xiaomi.com/pass/serviceLogin?callback=https%3A%2F%2Fplatform.xiaomimimo.com%2Fsts%3Fsign%3DcCRWVCC6g3tteb%252Fcnsfb4XS2Y1I%253D%26followup%3Dhttp%253A%252F%252Fplatform.xiaomimimo.com%252Fapi%252Fv1%252Fmimo-speed%252Fapply&sid=api-platform&_group=DEFAULT';
  let r = await s.get(ssoUrl);
  let url = r.headers.get('location');
  let steps = 10;
  while (url && steps-- > 0) {
    r = await s.get(url.startsWith('http') ? url : `https://account.xiaomi.com${url}`);
    url = r.headers.get('location');
    if (r.status >= 200 && r.status < 300) break;
  }

  const ph = (s.cookies['api-platform_ph'] || '').replace(/^"|"$/g, '');
  console.log(`✅ ph: ${ph}`);
  console.log(`Cookies: ${Object.keys(s.cookies).join(', ')}`);

  // Referral code
  console.log('\nReferral...');
  const refRes = await s.get(`${MIMO}/api/v1/invitation/code`, { headers: { 'Accept': 'application/json' } });
  const refData = await refRes.json();
  console.log(JSON.stringify(refData, null, 2));

  // Apply UltraSpeed - try with ph in cookie header AND as the only auth
  console.log('\nApply UltraSpeed...');
  
  // Build cookie string with ALL cookies
  const allCookies = s.cookieStr();
  console.log(`Cookie header length: ${allCookies.length}`);
  
  const applyRes = await s.post(
    `${MIMO}/api/v1/mimo-speed/apply`,
    JSON.stringify({
      name: 'Nico Setiawan',
      phone: '+62812345678',
      email: 'nicosetiawan@jimixz.tech',
      company: 'Jimixz Tech',
      industry: '互联网',
      appInfo: 'Coding Agent / 代码生成',
      additionalInfo: 'Building AI coding agents for production use. Need UltraSpeed 1000 tok/s.'
    }),
    { headers: {
      'Content-Type': 'application/json',
      'Origin': MIMO,
      'Referer': `${MIMO}/ultraspeed`,
      'Accept': 'application/json',
      'X-Requested-With': 'XMLHttpRequest'
    }}
  );
  
  const applyText = await applyRes.text();
  console.log(`Status: ${applyRes.status}`);
  console.log(`Response: ${applyText.substring(0, 500)}`);
  
  // Try to see if it's a sign issue - maybe we need a fresh STS call for the apply endpoint
  console.log('\n--- Debug: Try with followup=ultraspeed ---');
  const ssoUrl2 = 'https://account.xiaomi.com/pass/serviceLogin?callback=https%3A%2F%2Fplatform.xiaomimimo.com%2Fsts%3Fsign%3DcCRWVCC6g3tteb%252Fcnsfb4XS2Y1I%253D%26followup%3Dhttp%253A%252F%252Fplatform.xiaomimimo.com%252Fultraspeed&sid=api-platform&_group=DEFAULT';
  r = await s.get(ssoUrl2);
  url = r.headers.get('location');
  steps = 10;
  while (url && steps-- > 0) {
    r = await s.get(url.startsWith('http') ? url : `https://account.xiaomi.com${url}`);
    url = r.headers.get('location');
    if (r.status >= 200 && r.status < 300) break;
  }
  console.log(`After re-SSO, cookies: ${Object.keys(s.cookies).join(', ')}`);
  
  // Try apply again
  const applyRes2 = await s.post(
    `${MIMO}/api/v1/mimo-speed/apply`,
    JSON.stringify({
      name: 'Nico Setiawan',
      phone: '+62812345678',
      email: 'nicosetiawan@jimixz.tech',
      company: 'Jimixz Tech',
      industry: '互联网',
      appInfo: 'Coding Agent / 代码生成',
      additionalInfo: 'Building AI coding agents.'
    }),
    { headers: {
      'Content-Type': 'application/json',
      'Origin': MIMO,
      'Referer': `${MIMO}/ultraspeed`,
      'Accept': 'application/json'
    }}
  );
  const applyText2 = await applyRes2.text();
  console.log(`Status: ${applyRes2.status}`);
  console.log(`Response: ${applyText2.substring(0, 500)}`);
}

main().catch(e => console.error('Error:', e.message));
