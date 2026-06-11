#!/usr/bin/env node
const crypto = require('crypto');
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36';
const MIMO = 'https://platform.xiaomimimo.com';
const AES_IV = Buffer.from('0102030405060708');
const KEY_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*';
const EUI_RSA_PEM = `-----BEGIN PUBLIC KEY-----\nMIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCYEVrK/4Mahiv0pUJgTybx4J9P\n5dUT/Y0PuwMbk+gMU+jrZnBiXGv6/hCH1avIhoBcE535F8nJQQN3UavZdFkYidso\nXuEnat3+eVTp3FslyhRwIBDF09v4vDhRtxFOT+R7uH7h/mzmyA2/+lfIMWGIrffX\nprYizbV76+YQKhoqFQIDAQAB\n-----END PUBLIC KEY-----`;

const cookies = {};
function cs() { return Object.entries(cookies).map(([k,v]) => `${k}=${v}`).join('; '); }
function pc(r) { if (r.headers.getSetCookie) for (const c of r.headers.getSetCookie()) { const [kv]=c.split(';'); const [k,...v]=kv.split('='); cookies[k.trim()]=v.join('=').trim(); } }
function randomAesKey(l=16){let k='';for(let i=0;i<l;i++)k+=KEY_CHARS[crypto.randomBytes(1)[0]%KEY_CHARS.length];return k}
function aesEncrypt(p,k){const c=crypto.createCipheriv('aes-128-cbc',Buffer.from(k),AES_IV);let e=c.update(p,'utf8');e=Buffer.concat([e,c.final()]);return e.toString('base64')}
function rsaEncrypt(d,p){return crypto.publicEncrypt({key:p,padding:crypto.constants.RSA_PKCS1_PADDING},Buffer.from(d,'utf8')).toString('base64')}
function enc(fields){const k=randomAesKey(),e={};for(const[n,v]of Object.entries(fields))e[n]=aesEncrypt(v,k);const kb=Buffer.from(k).toString('base64'),r=rsaEncrypt(kb,EUI_RSA_PEM),fn=Buffer.from(Object.keys(fields).join(',')).toString('base64');return{EUI:r+'.'+fn,enc:e}}

async function main() {
  // Step 1: SSO
  console.log('1. SSO...');
  let r = await fetch('https://account.xiaomi.com/pass/serviceLogin?callback=https%3A%2F%2Fplatform.xiaomimimo.com%2Fsts%3Fsign%3DcCRWVCC6g3tteb%252Fcnsfb4XS2Y1I%253D%26followup%3Dhttp%253A%252F%252Fplatform.xiaomimimo.com%252F&sid=api-platform&_group=DEFAULT', { headers: { 'User-Agent': UA }, redirect: 'manual' });
  pc(r);
  const ssoLoc = r.headers.get('location');
  
  // Step 2: Follow to login page
  r = await fetch(ssoLoc, { headers: { 'User-Agent': UA, 'Cookie': cs() }, redirect: 'manual' });
  pc(r);
  const loginPageLoc = r.headers.get('location');
  
  // Get sign
  const allUrls = ssoLoc + (loginPageLoc || '');
  const signMatch = allUrls.match(/_sign=([^&]+)/);
  const sign = signMatch ? decodeURIComponent(signMatch[1]) : '';
  
  // Step 3: Login with SHA1 hashed password
  console.log('2. Login...');
  const sha1Pass = crypto.createHash('sha1').update('jimixz123!').digest('hex').toUpperCase();
  console.log('  SHA1 pass:', sha1Pass.substring(0, 10) + '...');
  
  const { EUI, enc: ep } = enc({ email: 'nicosetiawan@jimixz.tech', password: sha1Pass });
  
  const body = new URLSearchParams({
    _json: 'true',
    qs: '%3Fcallback%3Dhttps%253A%252F%252Fplatform.xiaomimimo.com%252Fsts%253Fsign%253DcCRWVCC6g3tteb%25252Fcnsfb4XS2Y1I%25253D%2526followup%253Dhttp%25253A%25252F%25252Fplatform.xiaomimimo.com%25252F&sid=api-platform&_group=DEFAULT',
    sid: 'api-platform',
    _sign: sign,
    user: ep.email,
    hash: ep.password,
    callback: 'https://platform.xiaomimimo.com/sts?sign=cCRWVCC6g3tteb%2Fcnsfb4XS2Y1I%3D&followup=http%3A%2F%2Fplatform.xiaomimimo.com%2F',
    _locale: 'en',
  }).toString();
  
  const lr = await fetch('https://account.xiaomi.com/pass/serviceLoginAuth', {
    method: 'POST',
    headers: { 'User-Agent': UA, 'Cookie': cs(), 'Content-Type': 'application/x-www-form-urlencoded', 'eui': EUI },
    body, redirect: 'manual'
  });
  pc(lr);
  let lt = await lr.text();
  if (lt.startsWith('&&&START&&&')) lt = lt.slice(11);
  console.log('  Response:', lt.substring(0, 300));
  
  let ld;
  try { ld = JSON.parse(lt); } catch { ld = { raw: lt }; }
  console.log('  code:', ld.code, 'desc:', ld.desc);
  console.log('  Cookies:', Object.keys(cookies).join(', '));
  
  // If login succeeded (no code means success, location present)
  if (ld.location) {
    console.log('\n3. Following SSO redirect...');
    let url = ld.location;
    let steps = 15;
    while (url && steps-- > 0) {
      r = await fetch(url, { headers: { 'User-Agent': UA, 'Cookie': cs() }, redirect: 'manual' });
      pc(r);
      const loc = r.headers.get('location');
      console.log(`  ${r.status} ${url.substring(0, 80)}...`);
      if (r.status >= 300 && r.status < 400) url = loc;
      else {
        const b = await r.text();
        const m = b.match(/window\.location(?:\.href)?\s*=\s*["']([^"']+)["']/);
        if (m) url = m[1]; else break;
      }
    }
  }
  
  const ph = (cookies['api-platform_ph'] || '').replace(/^"|"$/g, '');
  console.log(`\n  ph: ${ph ? 'OK' : 'MISSING'}`);
  console.log('  All cookies:', Object.keys(cookies).join(', '));
  
  if (ph) {
    // Referral
    console.log('\n4. Referral...');
    const refRes = await fetch(`${MIMO}/api/v1/invitation/code`, { headers: { 'User-Agent': UA, 'Cookie': cs(), 'Accept': 'application/json' } });
    const refData = await refRes.json();
    console.log(`  ${JSON.stringify(refData)}`);
    
    // Apply
    console.log('\n5. Apply...');
    const applyRes = await fetch(`${MIMO}/api/v1/mimo-speed/apply`, {
      method: 'POST',
      headers: { 'User-Agent': UA, 'Cookie': cs(), 'Content-Type': 'application/json', 'Origin': MIMO, 'Referer': `${MIMO}/ultraspeed` },
      body: JSON.stringify({ name: 'Nico Setiawan', phone: '+628****5678', email: 'nicosetiawan@jimixz.tech', company: 'Jimixz Tech', industry: '互联网', appInfo: 'Coding Agent / 代码生成', additionalInfo: 'Building AI coding agents.' })
    });
    console.log(`  Status: ${applyRes.status}`);
    console.log(`  Response: ${(await applyRes.text()).substring(0, 500)}`);
  }
}
main().catch(e => console.error('Error:', e.message));
