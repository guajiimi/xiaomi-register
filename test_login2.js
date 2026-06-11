#!/usr/bin/env node
/**
 * Test v2: Login via Xiaomi SSO → MiMo → referral + apply
 */

const cookies = {
  passToken: 'V1:DXmurwq2/R1BHTELu6obCf5SEsEWzHG7hDkYw6Ue2BSwOcbNIEoKQlx5n70Y7/pyJIodm3U5ZhfJRJTZUu87C0uMd0f2IyIabIpm3J829R18J5LY+bnrySmg5ND9QWoTtccXyarHQ3faiuNyq6QxH5OD5ocISN0s1ESECcJHocMcTf7LnIVa46I1eka41CSk7uWIrFxPzuir80x7t+C/a5ql4U05iooGR3rDutspmyM1VqDCBNYVqlBOB6YWZkLTKFdj31O/LrCWN/Os66eMoSrK5BmFGvWXMsf9gJSkVDswUI5b0kgsrEljRJbX/ZqFSYnH+A6RPFooK3ToSwwICA==',
  cUserId: '_-y893NG8_Gnh-l99qkvQ35w4JM',
  userId: '6876448492'
};

const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36';
const MIMO = 'https://platform.xiaomimimo.com';

class Session {
  constructor() {
    this.cookies = { ...cookies };
    this.ua = UA;
  }

  _parseCookies(headers) {
    const sc = headers['set-cookie'] || headers.getSetCookie?.() || [];
    const arr = Array.isArray(sc) ? sc : [sc];
    for (const c of arr) {
      if (!c) continue;
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
    // Also try getSetCookie
    if (res.headers.getSetCookie) {
      for (const c of res.headers.getSetCookie()) {
        const [kv] = c.split(';');
        const [k, ...v] = kv.split('=');
        this.cookies[k.trim()] = v.join('=').trim();
      }
    }
    return res;
  }

  async post(url, body, opts = {}) {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'User-Agent': this.ua, Cookie: this.cookieStr(), ...opts.headers },
      body,
      redirect: 'manual',
    });
    this._parseCookies(Object.fromEntries(res.headers.entries()));
    if (res.headers.getSetCookie) {
      for (const c of res.headers.getSetCookie()) {
        const [kv] = c.split(';');
        const [k, ...v] = kv.split('=');
        this.cookies[k.trim()] = v.join('=').trim();
      }
    }
    return res;
  }
}

async function test() {
  const s = new Session();

  // Step 1: Hit the MiMo SSO login URL (from the docs page)
  // The SSO flow: MiMo → Xiaomi SSO login → back to MiMo with session
  console.log('Step 1: Initiating MiMo SSO...');
  
  // The STS endpoint is what exchanges Xiaomi auth for MiMo cookies
  // We need to go through the Xiaomi service login first
  const ssoUrl = 'https://account.xiaomi.com/pass/serviceLogin?callback=https%3A%2F%2Fplatform.xiaomimimo.com%2Fsts%3Fsign%3DcCRWVCC6g3tteb%252Fcnsfb4XS2Y1I%253D%26followup%3Dhttp%253A%252F%252Fplatform.xiaomimimo.com%252Fapi%252Fv1%252Fmimo-speed%252Fapply&sid=api-platform&_group=DEFAULT';
  
  console.log(`  -> Xiaomi SSO: ${ssoUrl.substring(0, 100)}...`);
  const r1 = await s.get(ssoUrl);
  console.log(`  Status: ${r1.status} | Location: ${(r1.headers.get('location') || '').substring(0, 120)}`);
  console.log(`  Cookies: ${Object.keys(s.cookies).join(', ')}`);

  // Step 2: Follow redirect (should go to STS → MiMo)
  let url = r1.headers.get('location');
  let maxSteps = 15;
  while (url && maxSteps-- > 0) {
    const fullUrl = url.startsWith('http') ? url : `https://account.xiaomi.com${url}`;
    console.log(`  -> ${fullUrl.substring(0, 130)}...`);
    const r = await s.get(fullUrl);
    console.log(`  Status: ${r.status} | Cookies: ${Object.keys(s.cookies).length}`);
    
    if (r.status >= 300 && r.status < 400) {
      url = r.headers.get('location');
    } else {
      // Check for JS redirect
      const body = await r.text();
      const jsMatch = body.match(/window\.location(?:\.href)?\s*=\s*["']([^"']+)["']/);
      if (jsMatch) {
        url = jsMatch[1];
        console.log(`  JS redirect: ${url.substring(0, 100)}`);
      } else {
        // Check meta refresh
        const metaMatch = body.match(/<meta[^>]*url=([^"'\s>]+)/i);
        if (metaMatch) {
          url = metaMatch[1];
          console.log(`  Meta refresh: ${url.substring(0, 100)}`);
        } else {
          break;
        }
      }
    }
  }

  console.log('\nFinal cookies:', Object.keys(s.cookies).join(', '));
  const ph = s.cookies['api-platform_ph'];
  
  if (ph) {
    console.log(`✅ Got api-platform_ph: ${ph.substring(0, 30)}...`);
    
    // Fetch referral code
    console.log('\nFetching referral code...');
    const refRes = await s.get(`${MIMO}/api/v1/invitation/code`, {
      headers: { 'Accept': 'application/json' }
    });
    const refData = await refRes.json();
    console.log('Referral:', JSON.stringify(refData, null, 2));
    
    // Apply UltraSpeed
    console.log('\nApplying UltraSpeed...');
    const applyRes = await s.post(
      `${MIMO}/api/v1/mimo-speed/apply?api-platform_ph=${encodeURIComponent(ph)}`,
      JSON.stringify({
        name: 'Nico Setiawan',
        phone: '+62812345678',
        email: 'nicosetiawan@jimixz.tech',
        company: 'Jimixz Tech',
        industry: '互联网',
        appInfo: 'Coding Agent / 代码生成',
        additionalInfo: 'Building AI coding agents. Need UltraSpeed 1000 tok/s.'
      }),
      { headers: { 'Content-Type': 'application/json', 'Origin': MIMO, 'Referer': `${MIMO}/ultraspeed` } }
    );
    const applyData = await applyRes.json();
    console.log('Apply:', JSON.stringify(applyData, null, 2));
    
    // Final output
    const output = {
      email: 'nicosetiawan@jimixz.tech',
      userId: '6876448492',
      referralCode: refData.invitationCode || null,
      referralReward: refData.rewardAmount || null,
      referralCurrency: refData.currency || null,
      maxInvites: refData.maxInviteeCount || null,
      referralUrl: null,
      ultraSpeedApplied: applyData.code === 0,
      ultraSpeedResponse: applyData,
      appliedAt: new Date().toISOString()
    };
    if (output.referralCode) output.referralUrl = `${MIMO}?ref=${output.referralCode}`;
    
    console.log('\n' + '='.repeat(60));
    console.log('📄 FINAL JSON:');
    console.log('='.repeat(60));
    console.log(JSON.stringify(output, null, 2));
    
  } else {
    console.log('❌ No api-platform_ph — SSO failed');
    // Debug: try hitting MiMo API directly with just the xiaomi cookies
    console.log('\nDebug: Trying direct API call with xiaomi cookies...');
    const debugRes = await s.get(`${MIMO}/api/v1/invitation/code`, {
      headers: { 'Accept': 'application/json' }
    });
    console.log(`Status: ${debugRes.status}`);
    const debugBody = await debugRes.text();
    console.log(`Body: ${debugBody.substring(0, 300)}`);
  }
}

test().catch(e => { console.error('Error:', e.message); console.error(e.stack); });
