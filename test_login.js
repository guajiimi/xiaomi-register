#!/usr/bin/env node
/**
 * Test: Login with existing Xiaomi cookies → fetch referral code → apply UltraSpeed
 */

const cookies = {
  passToken: 'V1:DXmurwq2/R1BHTELu6obCf5SEsEWzHG7hDkYw6Ue2BSwOcbNIEoKQlx5n70Y7/pyJIodm3U5ZhfJRJTZUu87C0uMd0f2IyIabIpm3J829R18J5LY+bnrySmg5ND9QWoTtccXyarHQ3faiuNyq6QxH5OD5ocISN0s1ESECcJHocMcTf7LnIVa46I1eka41CSk7uWIrFxPzuir80x7t+C/a5ql4U05iooGR3rDutspmyM1VqDCBNYVqlBOB6YWZkLTKFdj31O/LrCWN/Os66eMoSrK5BmFGvWXMsf9gJSkVDswUI5b0kgsrEljRJbX/ZqFSYnH+A6RPFooK3ToSwwICA==',
  cUserId: '_-y893NG8_Gnh-l99qkvQ35w4JM',
  userId: '6876448492'
};

const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36';
const MIMO = 'https://platform.xiaomimimo.com';

async function test() {
  // Step 1: Visit MiMo ultraspeed to trigger SSO
  console.log('Step 1: Visiting MiMo ultraspeed...');
  const res1 = await fetch(`${MIMO}/ultraspeed`, {
    redirect: 'manual',
    headers: { 'User-Agent': UA }
  });
  console.log(`Status: ${res1.status}`);
  const location = res1.headers.get('location');
  console.log(`Redirect: ${(location || '').substring(0, 150)}`);

  // Step 2: Follow SSO redirect chain with Xiaomi cookies
  console.log('\nStep 2: Following SSO with Xiaomi cookies...');
  let url = location;
  let cookieJar = {};
  
  // Set Xiaomi cookies
  cookieJar['passToken'] = cookies.passToken;
  cookieJar['cUserId'] = cookies.cUserId;
  cookieJar['userId'] = cookies.userId;
  
  let maxRedirects = 15;
  while (url && maxRedirects-- > 0) {
    const fullUrl = url.startsWith('http') ? url : `${MIMO}${url}`;
    console.log(`  -> ${fullUrl.substring(0, 120)}...`);
    
    const cookieStr = Object.entries(cookieJar).map(([k,v]) => `${k}=${v}`).join('; ');
    const r = await fetch(fullUrl, {
      redirect: 'manual',
      headers: {
        'User-Agent': UA,
        'Cookie': cookieStr
      }
    });
    
    // Parse set-cookie
    const sc = r.headers.getSetCookie ? r.headers.getSetCookie() : [];
    for (const c of sc) {
      const [kv] = c.split(';');
      const [k, ...v] = kv.split('=');
      cookieJar[k.trim()] = v.join('=').trim();
    }
    
    console.log(`  Status: ${r.status} | Cookies: ${Object.keys(cookieJar).length}`);
    
    if (r.status >= 300 && r.status < 400) {
      url = r.headers.get('location');
    } else {
      // Check body for JS redirect
      const body = await r.text();
      const jsMatch = body.match(/window\.location\s*=\s*["']([^"']+)["']/);
      if (jsMatch) {
        url = jsMatch[1];
        console.log(`  JS redirect: ${url.substring(0, 100)}`);
      } else {
        break;
      }
    }
  }
  
  // Check if we got mimo cookies
  console.log('\nFinal cookies:', Object.keys(cookieJar).join(', '));
  const ph = cookieJar['api-platform_ph'];
  
  if (ph) {
    console.log(`✅ Got api-platform_ph: ${ph.substring(0, 30)}...`);
    const cookieStr = Object.entries(cookieJar).map(([k,v]) => `${k}=${v}`).join('; ');
    
    // Step 3: Fetch referral code
    console.log('\nStep 3: Fetching referral code...');
    const refRes = await fetch(`${MIMO}/api/v1/invitation/code`, {
      headers: {
        'User-Agent': UA,
        'Cookie': cookieStr,
        'Accept': 'application/json'
      }
    });
    const refData = await refRes.json();
    console.log('Referral response:', JSON.stringify(refData, null, 2));
    
    // Step 4: Check invitation eligible
    console.log('\nStep 3b: Checking invitation eligible...');
    const eligRes = await fetch(`${MIMO}/api/v1/invitation/eligible`, {
      headers: {
        'User-Agent': UA,
        'Cookie': cookieStr,
        'Accept': 'application/json'
      }
    });
    const eligData = await eligRes.json();
    console.log('Eligible response:', JSON.stringify(eligData, null, 2));
    
    // Step 5: Apply UltraSpeed
    console.log('\nStep 4: Applying UltraSpeed...');
    const applyBody = JSON.stringify({
      name: 'Nico Setiawan',
      phone: '+628123455678',
      email: 'nicosetiawan@jimixz.tech',
      company: 'Jimixz Tech',
      industry: '互联网',
      appInfo: 'Coding Agent / 代码生成',
      additionalInfo: 'Building AI coding agents for production. Need UltraSpeed 1000 tok/s for real-time code generation.'
    });
    
    const applyRes = await fetch(`${MIMO}/api/v1/mimo-speed/apply?api-platform_ph=${encodeURIComponent(ph)}`, {
      method: 'POST',
      headers: {
        'User-Agent': UA,
        'Cookie': cookieStr,
        'Content-Type': 'application/json',
        'Origin': MIMO,
        'Referer': `${MIMO}/ultraspeed`
      },
      body: applyBody
    });
    const applyData = await applyRes.json();
    console.log('Apply response:', JSON.stringify(applyData, null, 2));
    
    // Final JSON output
    const output = {
      email: 'nicosetiawan@jimixz.tech',
      userId: '6876448492',
      referralCode: refData.invitationCode || refData.data?.invitationCode || null,
      referralReward: refData.rewardAmount || refData.data?.rewardAmount || null,
      referralCurrency: refData.currency || refData.data?.currency || null,
      maxInvites: refData.maxInviteeCount || refData.data?.maxInviteeCount || null,
      referralUrl: null,
      ultraSpeedApplied: applyData.code === 0,
      ultraSpeedResponse: applyData,
      appliedAt: new Date().toISOString()
    };
    if (output.referralCode) {
      output.referralUrl = `${MIMO}?ref=${output.referralCode}`;
    }
    
    console.log('\n' + '='.repeat(60));
    console.log('📄 FINAL JSON OUTPUT:');
    console.log('='.repeat(60));
    console.log(JSON.stringify(output, null, 2));
    
  } else {
    console.log('❌ No api-platform_ph cookie — SSO failed');
    console.log('All cookies:', JSON.stringify(cookieJar, null, 2));
  }
}

test().catch(e => console.error('Error:', e.message));
