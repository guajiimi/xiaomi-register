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
  
  cookieStr() {
    return Object.entries(this.cookies).map(([k, v]) => `${k}=${v}`).join('; ');
  }

  async get(url, opts = {}) {
    const res = await fetch(url, {
      method: 'GET',
      headers: { 'User-Agent': UA, Cookie: this.cookieStr(), ...opts.headers },
      redirect: 'manual',
    });
    this._parseCookies(res);
    return res;
  }

  async post(url, body, opts = {}) {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'User-Agent': UA, Cookie: this.cookieStr(), ...opts.headers },
      body, redirect: 'manual',
    });
    this._parseCookies(res);
    return res;
  }

  _parseCookies(res) {
    if (res.headers.getSetCookie) {
      for (const c of res.headers.getSetCookie()) {
        const [kv] = c.split(';');
        const [k, ...v] = kv.split('=');
        this.cookies[k.trim()] = v.join('=').trim();
      }
    }
  }
}

async function main() {
  const s = new Session();

  // Step 1: SSO login
  console.log('Step 1: SSO login...');
  const ssoUrl = 'https://account.xiaomi.com/pass/serviceLogin?callback=https%3A%2F%2Fplatform.xiaomimimo.com%2Fsts%3Fsign%3DcCRWVCC6g3tteb%252Fcnsfb4XS2Y1I%253D%26followup%3Dhttp%253A%252F%252Fplatform.xiaomimimo.com%252Fapi%252Fv1%252Fmimo-speed%252Fapply&sid=api-platform&_group=DEFAULT';
  
  let r = await s.get(ssoUrl);
  let url = r.headers.get('location');
  let steps = 10;
  while (url && steps-- > 0) {
    const full = url.startsWith('http') ? url : `https://account.xiaomi.com${url}`;
    r = await s.get(full);
    url = r.headers.get('location');
    if (r.status >= 200 && r.status < 300) break;
  }

  const ph = s.cookies['api-platform_ph'];
  // Remove quotes if present
  const cleanPh = ph ? ph.replace(/^"|"$/g, '') : null;
  console.log(`✅ SSO OK | ph: ${cleanPh?.substring(0, 30)}...`);
  console.log(`All cookies: ${Object.keys(s.cookies).join(', ')}`);

  // Step 2: Fetch referral code
  console.log('\nStep 2: Referral code...');
  const refRes = await s.get(`${MIMO}/api/v1/invitation/code`, { headers: { 'Accept': 'application/json' } });
  const refData = await refRes.json();
  console.log(JSON.stringify(refData, null, 2));

  // Step 3: Apply UltraSpeed (use clean ph without quotes)
  console.log('\nStep 3: Apply UltraSpeed...');
  const applyRes = await s.post(
    `${MIMO}/api/v1/mimo-speed/apply`,
    JSON.stringify({
      name: 'Nico Setiawan',
      phone: '+62812345678',
      email: 'nicosetiawan@jimixz.tech',
      company: 'Jimixz Tech',
      industry: '互联网',
      appInfo: 'Coding Agent / 代码生成',
      additionalInfo: 'Building AI coding agents. Need UltraSpeed 1000 tok/s for real-time code generation and inference.'
    }),
    { headers: {
      'Content-Type': 'application/json',
      'Origin': MIMO,
      'Referer': `${MIMO}/ultraspeed`
    }}
  );
  const applyData = await applyRes.json();
  console.log('Apply status:', applyRes.status);
  console.log(JSON.stringify(applyData, null, 2));

  // Final JSON
  const output = {
    email: 'nicosetiawan@jimixz.tech',
    userId: '6876448492',
    referralCode: refData.data?.invitationCode || null,
    referralReward: refData.data?.rewardAmount || null,
    referralCurrency: refData.data?.currency || null,
    maxInvites: refData.data?.maxInviteeCount || null,
    referralUrl: refData.data?.invitationCode ? `${MIMO}?ref=${refData.data.invitationCode}` : null,
    ultraSpeedApplied: applyData.code === 0,
    ultraSpeedResponse: applyData,
    appliedAt: new Date().toISOString()
  };

  console.log('\n' + '='.repeat(60));
  console.log('📄 FINAL JSON:');
  console.log(JSON.stringify(output, null, 2));
}

main().catch(e => console.error('Error:', e.message));
