#!/usr/bin/env node
const cookies = {
  passToken: 'V1:DXmurwq2/R1BHTELu6obCf5SEsEWzHG7hDkYw6Ue2BSwOcbNIEoKQlx5n70Y7/pyJIodm3U5ZhfJRJTZUu87C0uMd0f2IyIabIpm3J829R18J5LY+bnrySmg5ND9QWoTtccXyarHQ3faiuNyq6QxH5OD5ocISN0s1ESECcJHocMcTf7LnIVa46I1eka41CSk7uWIrFxPzuir80x7t+C/a5ql4U05iooGR3rDutspmyM1VqDCBNYVqlBOB6YWZkLTKFdj31O/LrCWN/Os66eMoSrK5BmFGvWXMsf9gJSkVDswUI5b0kgsrEljRJbX/ZqFSYnH+A6RPFooK3ToSwwICA==',
  cUserId: '_-y893NG8_Gnh-l99qkvQ35w4JM',
  userId: '6876448492'
};
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36';
const MIMO = 'https://platform.xiaomimimo.com';

async function main() {
  // Step 1: Get the STS endpoint by visiting MiMo
  console.log('Step 1: Get genLoginUrl...');
  const genRes = await fetch(`${MIMO}/api/v1/genLoginUrl?currentPath=%2Fultraspeed`, {
    headers: { 'User-Agent': UA },
    redirect: 'manual'
  });
  const genData = await genRes.json().catch(() => null);
  console.log('genLoginUrl:', JSON.stringify(genData)?.substring(0, 300));
  
  // Step 2: Visit the SSO URL directly with ONLY Xiaomi cookies
  // The SSO flow: visit serviceLogin → passToken auto-auth → redirect to callback (STS)
  const ssoUrl = genData?.data?.loginUrl || genData?.loginUrl || 
    'https://account.xiaomi.com/pass/serviceLogin?callback=https%3A%2F%2Fplatform.xiaomimimo.com%2Fsts%3Fsign%3DcCRWVCC6g3tteb%252Fcnsfb4XS2Y1I%253D%26followup%3Dhttp%253A%252F%252Fplatform.xiaomimimo.com%252Fapi%252Fv1%252Fmimo-speed%252Fapply&sid=api-platform&_group=DEFAULT';
  
  console.log(`\nStep 2: SSO with Xiaomi cookies...`);
  console.log(`URL: ${ssoUrl.substring(0, 150)}`);
  
  // ONLY send Xiaomi cookies to Xiaomi domain
  const xiaomiCookies = `passToken=${cookies.passToken}; cUserId=${cookies.cUserId}; userId=${cookies.userId}`;
  
  const ssoRes = await fetch(ssoUrl, {
    headers: { 'User-Agent': UA, 'Cookie': xiaomiCookies },
    redirect: 'manual'
  });
  console.log(`SSO status: ${ssoRes.status}`);
  const ssoLoc = ssoRes.headers.get('location');
  console.log(`Location: ${ssoLoc?.substring(0, 200)}`);
  
  // Collect all set-cookie from Xiaomi
  const xiaomiNewCookies = {};
  if (ssoRes.headers.getSetCookie) {
    for (const c of ssoRes.headers.getSetCookie()) {
      const [kv] = c.split(';'); const [k, ...v] = kv.split('=');
      xiaomiNewCookies[k.trim()] = v.join('=').trim();
    }
  }
  console.log(`Xiaomi new cookies: ${Object.keys(xiaomiNewCookies).join(', ')}`);
  
  if (!ssoLoc) {
    console.log('❌ No redirect from SSO — passToken might be expired');
    // Check response body
    const body = await ssoRes.text();
    console.log(`Body (first 300): ${body.substring(0, 300)}`);
    return;
  }
  
  // Step 3: Follow redirect to STS → MiMo
  console.log('\nStep 3: Follow to STS...');
  let url = ssoLoc;
  let mimoCookies = {};
  let steps = 10;
  
  while (url && steps-- > 0) {
    // Determine which cookies to send based on domain
    const isXiaomi = url.includes('account.xiaomi.com');
    const isMimo = url.includes('platform.xiaomimimo.com');
    
    let cookieStr = '';
    if (isXiaomi) {
      cookieStr = Object.entries({...cookies, ...xiaomiNewCookies}).map(([k,v]) => `${k}=${v}`).join('; ');
    } else if (isMimo) {
      cookieStr = Object.entries(mimoCookies).map(([k,v]) => `${k}=${v}`).join('; ');
    }
    
    const r = await fetch(url, {
      headers: { 'User-Agent': UA, 'Cookie': cookieStr },
      redirect: 'manual'
    });
    
    // Collect cookies
    if (r.headers.getSetCookie) {
      for (const c of r.headers.getSetCookie()) {
        const [kv] = c.split(';'); const [k, ...v] = kv.split('=');
        if (isMimo) mimoCookies[k.trim()] = v.join('=').trim();
        else xiaomiNewCookies[k.trim()] = v.join('=').trim();
      }
    }
    
    const loc = r.headers.get('location');
    console.log(`  ${r.status} ${url.substring(0, 100)}... | mimo cookies: ${Object.keys(mimoCookies).length}`);
    
    if (r.status >= 300 && r.status < 400) {
      url = loc;
    } else {
      const body = await r.text();
      const m = body.match(/window\.location(?:\.href)?\s*=\s*["']([^"']+)["']/);
      if (m) { url = m[1]; console.log(`  JS redirect: ${url.substring(0, 100)}`); }
      else break;
    }
  }
  
  console.log(`\nMiMo cookies: ${Object.keys(mimoCookies).join(', ')}`);
  const ph = (mimoCookies['api-platform_ph'] || '').replace(/^"|"$/g, '');
  console.log(`ph: ${ph}`);
  
  if (!ph) {
    console.log('❌ No ph cookie');
    return;
  }
  
  // Step 4: Fetch referral code
  console.log('\nStep 4: Referral code...');
  const mimoCookieStr = Object.entries(mimoCookies).map(([k,v]) => `${k}=${v}`).join('; ');
  
  const refRes = await fetch(`${MIMO}/api/v1/invitation/code`, {
    headers: { 'User-Agent': UA, 'Cookie': mimoCookieStr, 'Accept': 'application/json' }
  });
  const refData = await refRes.json();
  console.log(JSON.stringify(refData, null, 2));
  
  // Step 5: Apply UltraSpeed
  console.log('\nStep 5: Apply UltraSpeed...');
  const applyRes = await fetch(`${MIMO}/api/v1/mimo-speed/apply`, {
    method: 'POST',
    headers: {
      'User-Agent': UA,
      'Cookie': mimoCookieStr,
      'Content-Type': 'application/json',
      'Origin': MIMO,
      'Referer': `${MIMO}/ultraspeed`,
      'Accept': 'application/json'
    },
    body: JSON.stringify({
      name: 'Nico Setiawan',
      phone: '+628****5678',
      email: 'nicosetiawan@jimixz.tech',
      company: 'Jimixz Tech',
      industry: '互联网',
      appInfo: 'Coding Agent / 代码生成',
      additionalInfo: 'Building AI coding agents for production. Need UltraSpeed 1000 tok/s.'
    })
  });
  const applyText = await applyRes.text();
  console.log(`Status: ${applyRes.status}`);
  console.log(`Response: ${applyText.substring(0, 500)}`);
  
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
    appliedAt: new Date().toISOString()
  };
  
  console.log('\n' + '='.repeat(60));
  console.log('📄 FINAL JSON:');
  console.log(JSON.stringify(output, null, 2));
}

main().catch(e => console.error('Error:', e.message));
