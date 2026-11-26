'use strict';
const journalUidPattern=/^[A-Za-z0-9_-]{1,128}$/;
const staffUidPattern=/^leave_[A-Za-z0-9_-]{16,80}$/;
const journalLoginPattern=/^[a-z0-9_-]{3,64}$/;
const sourceProject='bhcs-system';
const leaseMs=10*60*1000;
class LoginDenied extends Error {}
function ensure(test){if(!test)throw new LoginDenied('登入未獲授權');}
function tokenIdentity(decoded, now){
  ensure(decoded && decoded.aud===sourceProject && decoded.iss==='https://securetoken.google.com/'+sourceProject &&
    journalUidPattern.test(decoded.uid??'') && decoded.sub===decoded.uid &&
    decoded.firebase?.sign_in_provider==='password' &&
    typeof decoded.email==='string' && decoded.email.endsWith('@bhcs.local') && decoded.email!=='admin@bhcs.local' &&
    Number.isInteger(decoded.auth_time) && decoded.auth_time>0 && decoded.auth_time<=Math.floor(now/1000)+10);
  return decoded;
}
function verifyJournal(decoded, user, teacher, login){
  ensure(user && user.localId===decoded.uid && user.email===decoded.email && !user.disabled &&
    /^(0|[1-9][0-9]{0,11})$/.test(String(user.validSince)) && Number(user.validSince)<=decoded.auth_time);
  ensure(teacher && journalLoginPattern.test(teacher.userId??'') &&
    teacher.authEmail===decoded.email && teacher.mustChangePassword!==true);
  ensure(login && login.uid===decoded.uid && login.authEmail===decoded.email);
  return teacher.userId;
}
function leaveClaims(decoded,userId,binding,employee,now){
  ensure(binding && staffUidPattern.test(binding.leaveUid??'') && binding.active===true &&
    employee && employee.active===true && employee.role==='staff' && employee.journalSourceUid===decoded.uid &&
    employee.journalUserId===userId && employee.journalBindingVersion===binding.version &&
    Number.isSafeInteger(binding.version) && binding.version>=1 && typeof employee.employeeId==='string' && employee.employeeId.length>0);
  return {uid:binding.leaveUid, claims:{journalBinding:binding.version,journalUntil:now+leaseMs}};
}
module.exports={LoginDenied,sourceProject,leaseMs,tokenIdentity,verifyJournal,leaveClaims,ensure};
