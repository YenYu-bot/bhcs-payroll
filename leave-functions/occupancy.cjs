'use strict';
const active=new Set(['pending','needsProof','approved','applied','manual']);
function validDays(input){
 if(!Array.isArray(input)||input.length<1||input.length>14||new Set(input).size!==input.length)return false;
 return input.every(s=>typeof s==='string'&&/^20\d{2}-\d{2}-\d{2}$/.test(s)&&Number.isFinite(Date.parse(s))&&new Date(s).toISOString().slice(0,10)===s)
  && (Math.max(...input.map(Date.parse))-Math.min(...input.map(Date.parse)))/86400000<14;
}
function staffLease(uid,decoded,member,now){
 return decoded?.uid===uid&&member?.active===true&&member.role==='staff'
  && decoded.firebase?.sign_in_provider==='custom'
  && Number.isSafeInteger(decoded.journalBinding)&&decoded.journalBinding===member.journalBindingVersion
  && Number.isSafeInteger(decoded.journalUntil)&&decoded.journalUntil>now;
}
async function occupiedDays(dates,uid,readDate){
 const out=await Promise.all(dates.map(async date=>[date,(await readDate(date)).some(r=>r.owner!==uid&&active.has(r.status))]));
 return out.filter(([,occupied])=>occupied).map(([date])=>date);
}
module.exports={validDays,staffLease,occupiedDays};
