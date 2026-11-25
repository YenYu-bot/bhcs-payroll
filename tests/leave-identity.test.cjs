'use strict';
const assert=require('node:assert/strict');
const {test}=require('node:test');
const {tokenIdentity,verifyJournal,leaveClaims,leaseMs,LoginDenied}=require('../leave-functions/identity.cjs');
const now=1795598000000;
const uid='journalUID1', next='journalUID2';
const email='bhcst0001@bhcs.local', renewed='bhcst0001-reset1@bhcs.local';
const leaveUid='leave_fixture0000000001';
const auth={aud:'bhcs-system',iss:'https://securetoken.google.com/bhcs-system',sub:uid,uid,email,auth_time:now/1000-90,firebase:{sign_in_provider:'password'}};
const account={localId:uid,email,validSince:String(auth.auth_time)};
const teacher={userId:'bhcst0001',authEmail:email,mustChangePassword:false};
const login={uid,authEmail:email};
const binding={leaveUid,active:true,version:1};
const staff={active:true,role:'staff',journalSourceUid:uid,journalUserId:teacher.userId,journalBindingVersion:1,employeeId:'fixture-employee'};
const validate=(a=auth,u=account,t=teacher,l=login,b=binding,s=staff)=>leaveClaims(tokenIdentity(a,now),verifyJournal(a,u,t,l),b,s,now);
test('active verified teacher obtains a short lease for a stable leave identity',()=>{
 assert.deepEqual(validate(),{uid:leaveUid,claims:{journalBinding:1,journalUntil:now+leaseMs}});
});
test('identity provider, audience, issuer, disabled and revoked status fail closed',()=>{
 for(const patch of [{aud:'bhcs-leave'},{iss:'https://securetoken.google.com/wrong'},{email:'admin@bhcs.local'}, {uid:'bad/path'},{firebase:{sign_in_provider:'google.com'}}])assert.throws(()=>validate({...auth,...patch}),LoginDenied);
 for(const patch of [{disabled:true},{validSince:auth.auth_time+1},{validSince:null},{localId:next},{email:'wrong@bhcs.local'}])assert.throws(()=>validate(auth,{...account,...patch}),LoginDenied);
});
test('deleted teacher, non-current login, must-change flag, unbound, suspended and wrong role are rejected',()=>{
 assert.throws(()=>validate(auth,account,null,login),LoginDenied);
 assert.throws(()=>validate(auth,account,teacher,{...login,uid:next}),LoginDenied);
 assert.throws(()=>validate(auth,account,{...teacher,mustChangePassword:true}),LoginDenied);
 assert.throws(()=>validate(auth,account,teacher,login,null),LoginDenied);
 for(const patch of [{active:false},{role:'manager'},{journalBindingVersion:2},{employeeId:''}])assert.throws(()=>validate(auth,account,teacher,login,binding,{...staff,...patch}),LoginDenied);
});
test('supervisor verified replacement preserves history; text identifier reuse does not auto-bind',()=>{
 const a={...auth,uid:next,sub:next,email:renewed},u={...account,localId:next,email:renewed};
 const t={...teacher,authEmail:renewed},l={uid:next,authEmail:renewed};
 assert.throws(()=>validate(a,u,t,l,binding,staff),LoginDenied);
 assert.equal(validate(a,u,t,l,{...binding,version:2},{...staff,journalSourceUid:next,journalBindingVersion:2}).uid,leaveUid);
});
