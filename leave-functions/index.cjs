'use strict';
const { onRequest }=require('firebase-functions/v2/https');
const { defineString }=require('firebase-functions/params');
const { initializeApp }=require('firebase-admin/app');
const { getAuth }=require('firebase-admin/auth');
const { getFirestore }=require('firebase-admin/firestore');
const {LoginDenied,sourceProject,tokenIdentity,verifyJournal,leaveClaims,ensure}=require('./identity.cjs');
const sourceKey=defineString('JOURNAL_WEB_API_KEY');
const targetProject='bhcs-leave';
const staffOrigin='https://bhcs-leave.web.app';
const staffApp=initializeApp({projectId:targetProject});
const sourceApp=initializeApp({projectId:sourceProject},'journal-verify-only');
const db=getFirestore(staffApp);
function parseDoc(d){
 const fields=d?.fields??{};
 return Object.fromEntries(Object.entries(fields).map(([k,v])=>[k,v.stringValue??v.booleanValue]));
}
async function sourceGet(path,token){
 const url='https://firestore.googleapis.com/v1/projects/'+sourceProject+'/databases/(default)/documents/'+path;
 const rsp=await fetch(url,{headers:{Authorization:'Bearer '+token},signal:AbortSignal.timeout(5000)});
 if(rsp.status===403||rsp.status===404)throw new LoginDenied();
 if(!rsp.ok)throw Error('Source data unavailable');
 return parseDoc(await rsp.json());
}
async function sourceAccount(token){
 const key=sourceKey.value();
 if(!/^[A-Za-z0-9_-]{20,100}$/.test(key))throw Error('Missing source web API configuration');
 const rsp=await fetch('https://identitytoolkit.googleapis.com/v1/accounts:lookup?key='+key,{
  method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({idToken:token}),signal:AbortSignal.timeout(5000)
 });
 if(rsp.status===400||rsp.status===401||rsp.status===403)throw new LoginDenied();
 if(!rsp.ok)throw Error('Source authentication unavailable');
 return (await rsp.json()).users?.[0];
}
exports.exchangeJournalLogin=onRequest({
 region:'asia-east1',serviceAccount:'leave-auth-runtime@bhcs-leave.iam.gserviceaccount.com',maxInstances:1,minInstances:0,cpu:'gcf_gen1',concurrency:1,memory:'256MiB',timeoutSeconds:25
},async(req,res)=>{
 res.set('Cache-Control','no-store');res.set('Vary','Origin');
 if((process.env.GCLOUD_PROJECT??process.env.GOOGLE_CLOUD_PROJECT)!==targetProject){res.status(503).end();return;}
 if(req.get('origin')!==staffOrigin){res.status(403).end();return;}
 res.set('Access-Control-Allow-Origin',staffOrigin);res.set('Access-Control-Allow-Methods','POST, OPTIONS');res.set('Access-Control-Allow-Headers','Authorization, Content-Type');
 if(req.method==='OPTIONS'){res.status(204).end();return;}
 if(req.method!=='POST'){res.status(405).end();return;}
 const token=(req.get('authorization')??'').match(/^Bearer ([A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)$/)?.[1];
 if(!token||token.length>4096){res.status(401).json({status:'denied'});return;}
 try{
  let verified;
  try{verified=await getAuth(sourceApp).verifyIdToken(token);}catch{throw new LoginDenied();}
  const decoded=tokenIdentity(verified,Date.now());
  const [account,teacher]=await Promise.all([sourceAccount(token),sourceGet('teachers/'+encodeURIComponent(decoded.uid),token)]);
  ensure(/^[a-z0-9_-]{3,64}$/.test(teacher.userId??''));
  const login=await sourceGet('logins/'+encodeURIComponent(teacher.userId),token);
  const userId=verifyJournal(decoded,account,teacher,login);
  const result=await db.runTransaction(async tx=>{
   const binding=(await tx.get(db.collection('journalBindings').doc(decoded.uid))).data();
   ensure(binding&&/^leave_[A-Za-z0-9_-]{16,80}$/.test(binding.leaveUid??''));
   const employee=(await tx.get(db.collection('leaveMembers').doc(binding.leaveUid))).data();
   return leaveClaims(decoded,userId,binding,employee,Date.now());
  },{readOnly:true});
  const customToken=await getAuth(staffApp).createCustomToken(result.uid,result.claims);
  res.status(200).json({token:customToken,until:result.claims.journalUntil});
 }catch(err){
  if(err instanceof LoginDenied){res.status(401).json({status:'denied'});return;}
  // A credential, employee record, or request content must never be logged.
  res.status(503).json({status:'unavailable'});
 }
});
