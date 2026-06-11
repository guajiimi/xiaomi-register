#!/usr/bin/env node
const cookies = {
  passToken: 'V1:DXmurwq2/R1BHTELu6obCf5SEsEWzHG7hDkYw6Ue2BSwOcbNIEoKQlx5n70Y7/pyJIodm3U5ZhfJRJTZUu87C0uMd0f2IyIabIpm3J829R18J5LY+bnrySmg5ND9QWoTtccXyarHQ3faiuNyq6QxH5OD5ocISN0s1ESECcJHocMcTf7LnIVa46I1eka41CSk7uWIrFxPzuir80x7t+C/a5ql4U05iooGR3rDutspmyM1VqDCBNYVqlBOB6YWZkLTKFdj31O/LrCWN/Os66eMoSrK5BmFGvWXMsf9gJSkVDswUI5b0kgsrEljRJbX/ZqFSYnH+A6RPFooK3ToSwwICA==',
  cUserId: '_-y893NG8_Gnh-l99qkvQ35w4JM',
  userId: '6876448492'
};
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36';
const MIMO = 'https://platform.xiaomimimo.com';

async function main() {
  // SSO login — use followup to get a session that covers ALL endpoints
  // Use / (root) as followup instead of specific endpoint
  const ssoUrl = 'https://account.xiaomi.com/pass/serviceLogin?callback=https%3A%2F%2Fplatform.xiaomimimo.com%2Fsts%3Fsign%3DcCRWVCC6g3tteb%252Fcnsfb4XS2Y1I%253D%26followup%3Dhttp%253A%252F%252Fplatform.xiaomimimo.com%252F&sid=api-platform&_group=DEFAULT';
  const xiaomiCookies = `passToken=${cookies.passToken}; cUserId=${cookies.cUserId}; userId=${cookies.userId}`;
  
  let r = await fetch(ssoUrl, { headers: { 'User-Agent': UA, 'Cookie': xiaomiCookies }, redirect: 'manual' });
  let url = r.headers.get('location');
  const xc = {};
  if (r.headers.getSetCookie) for (const c of r.headers.getSetCookie()) { const [kv]=c.split(';'); const [k,...v]=kv.split('='); xc[k.trim()]=v.join('=').trim(); }
  
  const mc = {};
  let steps = 10;
  while (url && steps-- > 0) {
    const isMimo = url.includes('xiaomimimo.com');
    const ck = isMimo ? Object.entries(mc).map(([k,v]) => `${k}=${v}`).join('; ') : 
               Object.entries({...cookies, ...xc}).map(([k,v]) => `${k}=${v}`).join('; ');
    r = await fetch(url, { headers: { 'User-Agent': UA, 'Cookie': ck }, redirect: 'manual' });
    if (r.headers.getSetCookie) for (const c of r.headers.getSetCookie()) { const [kv]=c.split(';'); const [k,...v]=kv.split('='); if(isMimo) mc[k.trim()]=v.join('=').trim(); else xc[k.trim()]=v.join('=').trim(); }
    const loc = r.headers.get('location');
    if (r.status >= 300 && r.status < 400) url = loc;
    else break;
  }
  
  console.log('Cookies:', Object.keys(mc).join(', '));
  const ph = (mc['api-platform_ph'] || '').replace(/^"|"$/g, '');
  const st = (mc['api-platform_serviceToken'] || '').replace(/^"|"$/g, '');
  const slh = (mc['api-platform_slh'] || '').replace(/^"|"$/g, '');
  console.log(`ph: ${ph}`);
  console.log(`st: ${st.substring(0, 30)}...`);
  console.log(`slh: ${slh}`);
  
  // Test various endpoints
  const cookieStr = `api-platform_ph=${ph}; api-platform_serviceToken=${st}; userId=${mc['userId']}; api-platform_slh=${slh}`;
  const headers = { 'User-Agent': UA, 'Cookie': cookieStr, 'Accept': 'application/json' };
  
  console.log('\n--- Test endpoints ---');
  
  // Test 1: GET /api/v1/invitation/code
  const t1 = await fetch(`${MIMO}/api/v1/invitation/code`, { headers });
  console.log(`GET /invitation/code: ${t1.status} ${(await t1.text()).substring(0, 100)}`);
  
  // Test 2: GET /api/v1/mimo-speed/apply
  const t2 = await fetch(`${MIMO}/api/v1/mimo-speed/apply`, { headers });
  console.log(`GET /mimo-speed/apply: ${t2.status} ${(await t2.text()).substring(0, 100)}`);
  
  // Test 3: POST /api/v1/mimo-speed/apply (with ph in query)
  const t3 = await fetch(`${MIMO}/api/v1/mimo-speed/apply?api-platform_ph=${encodeURIComponent(ph)}`, {
    method: 'POST',
    headers: { ...headers, 'Content-Type': 'application/json', 'Origin': MIMO, 'Referer': `${MIMO}/ultraspeed` },
    body: JSON.stringify({ name: 'Test', phone: '+628123', email: 'test@test.com', company: 'Test', industry: '互联网', appInfo: 'Coding Agent / 代码生成', additionalInfo: 'test' })
  });
  console.log(`POST /mimo-speed/apply?ph=xxx: ${t3.status} ${(await t3.text()).substring(0, 100)}`);
  
  // Test 4: Try with BOTH cookies from SSO (combine xiaomi + mimo)
  const combinedCookie = Object.entries({...xc}).map(([k,v]) => `${k}=${v}`).join('; ') + '; ' + cookieStr;
  console.log(`\nCombined cookie length: ${combinedCookie.length}`);
  
  const t4 = await fetch(`${MIMO}/api/v1/mimo-speed/apply`, {
    method: 'POST',
    headers: { 'User-Agent': UA, 'Cookie': combinedCookie, 'Content-Type': 'application/json', 'Origin': MIMO, 'Referer': `${MIMO}/ultraspeed` },
    body: JSON.stringify({ name: 'Nico Setiawan', phone: '+628****5678', email: 'nicosetiawan@jimixz.tech', company: 'Jimixz Tech', industry: '互联网', appInfo: 'Coding Agent / 代码生成', additionalInfo: 'Building AI coding agents.' })
  });
  console.log(`POST with combined cookies: ${t4.status} ${(await t4.text()).substring(0, 200)}`);
  
  // Test 5: Try with serviceToken as header
  const t5 = await fetch(`${MIMO}/api/v1/mimo-speed/apply`, {
    method: 'POST',
    headers: { 'User-Agent': UA, 'Cookie': cookieStr, 'Content-Type': 'application/json', 'Origin': MIMO, 'Referer': `${MIMO}/ultraspeed`, 'Authorization': `Bearer ${st}` },
    body: JSON.stringify({ name: 'Nico Setiawan', phone: '+628****5678', email: 'nicosetiawan@jimixz.tech', company: 'Jimixz Tech', industry: '互联网', appInfo: 'Coding Agent / 代码生成', additionalInfo: 'Building AI coding agents.' })
  });
  console.log(`POST with Bearer token: ${t5.status} ${(await t5.text()).substring(0, 200)}`);
}

main().catch(e => console.error('Error:', e.message));
