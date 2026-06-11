#!/usr/bin/env node
const cookies = {
  passToken: 'V1:DXmurwq2/R1BHTELu6obCf5SEsEWzHG7hDkYw6Ue2BSwOcbNIEoKQlx5n70Y7/pyJIodm3U5ZhfJRJTZUu87C0uMd0f2IyIabIpm3J829R18J5LY+bnrySmg5ND9QWoTtccXyarHQ3faiuNyq6QxH5OD5ocISN0s1ESECcJHocMcTf7LnIVa46I1eka41CSk7uWIrFxPzuir80x7t+C/a5ql4U05iooGR3rDutspmyM1VqDCBNYVqlBOB6YWZkLTKFdj31O/LrCWN/Os66eMoSrK5BmFGvWXMsf9gJSkVDswUI5b0kgsrEljRJbX/ZqFSYnH+A6RPFooK3ToSwwICA==',
  cUserId: '_-y893NG8_Gnh-l99qkvQ35w4JM',
  userId: '6876448492'
};
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36';
const MIMO = 'https://platform.xiaomimimo.com';

async function main() {
  // SSO login
  const ssoUrl = 'https://account.xiaomi.com/pass/serviceLogin?callback=https%3A%2F%2Fplatform.xiaomimimo.com%2Fsts%3Fsign%3DcCRWVCC6g3tteb%252Fcnsfb4XS2Y1I%253D%26followup%3Dhttp%253A%252F%252Fplatform.xiaomimimo.com%252Fapi%252Fv1%252Fmimo-speed%252Fapply&sid=api-platform&_group=DEFAULT';
  const xiaomiCookies = `passToken=${cookies.passToken}; cUserId=${cookies.cUserId}; userId=${cookies.userId}`;
  
  let r = await fetch(ssoUrl, { headers: { 'User-Agent': UA, 'Cookie': xiaomiCookies }, redirect: 'manual' });
  let url = r.headers.get('location');
  
  // Collect xiaomi cookies
  const xc = {};
  if (r.headers.getSetCookie) {
    for (const c of r.headers.getSetCookie()) {
      const [kv] = c.split(';'); const [k, ...v] = kv.split('=');
      xc[k.trim()] = v.join('=').trim();
    }
  }
  
  // Follow to MiMo
  const mc = {};
  let steps = 10;
  while (url && steps-- > 0) {
    const isMimo = url.includes('xiaomimimo.com');
    const ck = isMimo ? Object.entries(mc).map(([k,v]) => `${k}=${v}`).join('; ') : 
               Object.entries({...cookies, ...xc}).map(([k,v]) => `${k}=${v}`).join('; ');
    
    r = await fetch(url, { headers: { 'User-Agent': UA, 'Cookie': ck }, redirect: 'manual' });
    
    if (r.headers.getSetCookie) {
      for (const c of r.headers.getSetCookie()) {
        const [kv] = c.split(';'); const [k, ...v] = kv.split('=');
        if (isMimo) mc[k.trim()] = v.join('=').trim();
        else xc[k.trim()] = v.join('=').trim();
      }
    }
    
    const loc = r.headers.get('location');
    if (r.status >= 300 && r.status < 400) { url = loc; }
    else break;
  }
  
  console.log('MiMo cookies:');
  for (const [k, v] of Object.entries(mc)) {
    console.log(`  ${k} = ${v.substring(0, 50)}${v.length > 50 ? '...' : ''}`);
  }
  
  const ph = mc['api-platform_ph'] || '';
  console.log(`\nRaw ph: "${ph}"`);
  console.log(`Has quotes: ${ph.startsWith('"') && ph.endsWith('"')}`);
  
  // Try apply with raw cookie string (bypass any encoding issues)
  const rawCookie = `api-platform_ph=${ph}; api-platform_serviceToken=${mc['api-platform_serviceToken'] || ''}; userId=${mc['userId'] || ''}; api-platform_slh=${mc['api-platform_slh'] || ''}`;
  console.log(`\nRaw cookie header: ${rawCookie.substring(0, 100)}...`);
  
  // Apply
  const applyRes = await fetch(`${MIMO}/api/v1/mimo-speed/apply`, {
    method: 'POST',
    headers: {
      'User-Agent': UA,
      'Cookie': rawCookie,
      'Content-Type': 'application/json',
      'Origin': MIMO,
      'Referer': `${MIMO}/ultraspeed`
    },
    body: JSON.stringify({
      name: 'Nico Setiawan', phone: '+628****5678', email: 'nicosetiawan@jimixz.tech',
      company: 'Jimixz Tech', industry: '互联网', appInfo: 'Coding Agent / 代码生成',
      additionalInfo: 'Building AI coding agents.'
    })
  });
  console.log(`\nApply status: ${applyRes.status}`);
  console.log(`Apply response: ${(await applyRes.text()).substring(0, 500)}`);
  
  // Also try without quotes in ph
  if (ph.startsWith('"')) {
    const cleanPh = ph.replace(/^"|"$/g, '');
    const cleanCookie = `api-platform_ph=${cleanPh}; api-platform_serviceToken=${mc['api-platform_serviceToken'] || ''}; userId=${mc['userId'] || ''}; api-platform_slh=${mc['api-platform_slh'] || ''}`;
    console.log(`\nTrying with clean ph (no quotes): ${cleanPh}`);
    
    const applyRes2 = await fetch(`${MIMO}/api/v1/mimo-speed/apply`, {
      method: 'POST',
      headers: {
        'User-Agent': UA,
        'Cookie': cleanCookie,
        'Content-Type': 'application/json',
        'Origin': MIMO,
        'Referer': `${MIMO}/ultraspeed`
      },
      body: JSON.stringify({
        name: 'Nico Setiawan', phone: '+628****5678', email: 'nicosetiawan@jimixz.tech',
        company: 'Jimixz Tech', industry: '互联网', appInfo: 'Coding Agent / 代码生成',
        additionalInfo: 'Building AI coding agents.'
      })
    });
    console.log(`Apply status: ${applyRes2.status}`);
    console.log(`Apply response: ${(await applyRes2.text()).substring(0, 500)}`);
  }
}

main().catch(e => console.error('Error:', e.message));
