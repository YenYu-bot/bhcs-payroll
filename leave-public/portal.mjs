import {datesBetween,elapsedMinutes,occupiedMessage} from './request-dates.mjs';
const sdk='https://www.gstatic.com/firebasejs/10.12.2/';
const types={annual:'特休',personal:'一般事假',sick:'普通傷病假',family:'家庭照顧假',carePersonal:'照顧家人事假',paidLeave:'婚／喪／公假',menstrual:'生理假',protectedSick:'其他不扣全勤病假（由主管核對）'};
const labels={pending:'待審核',needsProof:'待補證明',approved:'已核准，待登記考勤',applied:'已核准，已帶入考勤',manual:'已核准，主管已人工處理',rejected:'未核准',withdrawn:'已撤回'};
const limit=650000;
const value=(x)=>String(x??'');
const make=(tag,content)=>{const e=document.createElement(tag);if(content!=null)e.textContent=content;return e;};
const button=(title,action,alt=false)=>{const b=make('button',title);b.type='button';if(alt)b.className='alt';b.addEventListener('click',action);return b;};
function field(form,title,input){const l=make('label',title);l.append(input);form.append(l);return input;}
const selectedPhoto=(camera=false)=>{const p=make('input');p.type='file';p.accept='image/*';if(camera)p.setAttribute('capture','environment');return p;};
function photoFields(form){
  const camera=field(form,'用手機拍照',selectedPhoto(true)),library=field(form,'或選擇相簿照片',selectedPhoto());
  camera.onchange=()=>{if(camera.files.length)library.value='';};
  library.onchange=()=>{if(library.files.length)camera.value='';};
  return {file:()=>camera.files[0]||library.files[0],clear:()=>{camera.value=library.value='';}};
}
async function jpeg(file){
  if(!file||!/^image\/(jpeg|png|heic|heif|webp|avif|bmp)$/i.test(file.type)||file.size>20*1024*1024)throw Error('請用手機拍一張照片，或選擇 20 MB 以下的 JPEG／PNG 等相片。');
  let im;
  try{im=await createImageBitmap(file);}catch{throw Error('這張照片無法讀取，請重新拍攝，或另存成 JPEG／PNG。');}
  try{
    const c=make('canvas');
    let edge=1800;
    while(edge>=850){
      const scale=Math.min(1,edge/Math.max(im.width,im.height));
      c.width=Math.max(1,Math.round(im.width*scale));c.height=Math.max(1,Math.round(im.height*scale));
      const ctx=c.getContext('2d');
      ctx.fillStyle='#fff';ctx.fillRect(0,0,c.width,c.height);ctx.drawImage(im,0,0,c.width,c.height);
      for(const q of [.88,.76,.64]){
        const b=await new Promise(done=>c.toBlob(done,'image/jpeg',q));
        if(b?.size<=limit&&b.type==='image/jpeg')return new Uint8Array(await b.arrayBuffer());
      }
      edge-=280;
    }
    throw Error('照片過大，請裁切到證明範圍後再試。');
  }finally{im.close();}
}
export async function mountLeave(root,mode,integrate){
  const cfg=await import('./config.mjs');
  const { staffOrigin, managerOrigin, config }=cfg;
  if(!config?.apiKey||config.projectId!=='bhcs-leave'||!/^https:\/\//.test(staffOrigin)||!/^https:\/\//.test(managerOrigin)||staffOrigin===managerOrigin||
      location.origin!==(mode==='staff'?staffOrigin:managerOrigin))throw Error('入口或專案設定不正確。');
  const [fa,au,fs]=await Promise.all(['app','auth','firestore'].map(n=>import(sdk+'firebase-'+n+'.js')));
  const name='bhcs-leave-'+mode;
  const app=fa.getApps().find(x=>x.name===name)||fa.initializeApp(config,name);
  const auth=au.getAuth(app),db=fs.getFirestore(app);
  await au.setPersistence(auth,au.inMemoryPersistence);
  let journalAuth=null,journalDb=null,leaseTimer=null,renewing=false,loginRev=0;
  if(mode==='staff'){
    if(cfg.journalConfig?.projectId!=='bhcs-system'||!/^https:\/\/asia-east1-bhcs-leave\.cloudfunctions\.net\/exchangeJournalLogin$/.test(cfg.journalExchangeUrl??''))throw Error('教室日誌登入尚未開通。');
    const j=fa.getApps().find(x=>x.name==='bhcs-journal-signin-for-leave')||fa.initializeApp(cfg.journalConfig,'bhcs-journal-signin-for-leave');
    journalAuth=au.getAuth(j);journalDb=fs.getFirestore(j);
    await au.setPersistence(journalAuth,au.inMemoryPersistence);
  }
  async function signOutAll(){
    loginRev++;clearTimeout(leaseTimer);leaseTimer=null;
    await Promise.all([au.signOut(auth),journalAuth?au.signOut(journalAuth):Promise.resolve()]);
  }
  let closed=false,epoch=0,rev=0,member=null,urls=new Set(),busy=false;
  const objectsClear=()=>{for(const url of urls)URL.revokeObjectURL(url);urls.clear();};
  const alive=(token)=>!closed&&root.isConnected&&token===epoch;
  const uiError=(e)=>e?.code==='permission-denied'?'權限或假單狀態已變更，請重新整理。':e?.code?.startsWith('auth/')?'登入未完成，請用已開通的 Google 帳號再試一次。':!e?.code&&e?.message?e.message:'連線或儲存未完成，請再試一次。';
  let note;
  const say=(s)=>{if(note&&note.isConnected)note.textContent=s;};
  const action=async(fn)=>{
    if(busy||closed)return;
    const token=epoch;busy=true;say('處理中…');
    for(const b of root.querySelectorAll('button'))b.disabled=true;
    try{const msg=await fn(token);if(alive(token))say(msg||'已完成。');}
    catch(e){if(alive(token))say(uiError(e));}
    finally{busy=false;if(!closed)for(const b of root.querySelectorAll('button'))b.disabled=false;}
  };
  const requests=fs.collection(db,'leaveRequests');
  const person=(id)=>fs.doc(db,'leaveMembers',id);
  const ref=(id)=>fs.doc(requests,id);
  const proof=(id)=>fs.doc(db,'leaveProof',id);
  const sent=()=>fs.serverTimestamp();
  const get=fs.getDocFromServer;
  function base(){
    objectsClear();root.replaceChildren();
    note=make('p');note.setAttribute('role','status');root.append(note);
  }
  function list(head,container){root.append(make('h3',head),container);}
  function scheduleRefresh(until){
    clearTimeout(leaseTimer);
    leaseTimer=setTimeout(async()=>{
      if(closed||renewing||!auth.currentUser||!journalAuth?.currentUser)return;
      renewing=true;
      try{await exchange();}catch{if(!closed){await signOutAll();showLogin('登入已逾時或帳號已停用，請重新登入。');}}
      finally{renewing=false;}
    },Math.max(500,until-Date.now()-90_000));
  }
  async function exchange(){
    if(closed||!journalAuth?.currentUser)throw Error('請重新登入教室日誌帳號。');
    const current=journalAuth.currentUser,started=loginRev;
    const idToken=await current.getIdToken(true);
    const response=await fetch(cfg.journalExchangeUrl,{method:'POST',headers:{Authorization:'Bearer '+idToken},
      credentials:'omit',cache:'no-store',redirect:'error',signal:AbortSignal.timeout(12000)});
    if(!response.ok)throw Error(response.status===401?'帳號未開通請假或需要更新教室日誌密碼，請洽主管。':'驗證服務暫時無法連線，請稍後再試。');
    const data=await response.json();
    if(closed||started!==loginRev||journalAuth.currentUser!==current||!Number.isSafeInteger(data.until)||data.until<=Date.now()||data.until>Date.now()+660_000||typeof data.token!=='string')throw Error('請重新登入。');
    await au.signInWithCustomToken(auth,data.token);
    if(closed||started!==loginRev){await signOutAll();return;}
    scheduleRefresh(data.until);
  }
  function showLogin(message=''){
    base();say(message);
    if(mode==='manager'){
      root.append(button('使用主管 Google 帳號登入',()=>action(()=>au.signInWithPopup(auth,new au.GoogleAuthProvider()).then(()=>''))));
      return;
    }
    const f=make('form'),id=field(f,'教室日誌帳號',make('input')),password=field(f,'教室日誌密碼',make('input'));
    id.autocomplete='username';id.required=true;id.maxLength=64;
    password.type='password';password.autocomplete='current-password';password.required=true;
    const submit=make('button','使用教室日誌帳號登入');submit.type='submit';f.append(submit);
    f.addEventListener('submit',e=>{e.preventDefault();action(async()=>{
      const userId=id.value.trim().toLowerCase(),pw=password.value;
      password.value='';
      if(!/^[a-z0-9_-]{3,64}$/.test(userId)||!pw)throw Error('請輸入有效的教室日誌帳號和密碼。');
      try{
        const login=await get(fs.doc(journalDb,'logins',userId)),email=login.data()?.authEmail;
        if(typeof email!=='string'||!email.endsWith('@bhcs.local')||email==='admin@bhcs.local')throw Error('帳號或密碼不正確。');
        await au.signInWithEmailAndPassword(journalAuth,email,pw);
        await exchange();
      }catch(err){
        await signOutAll();
        if(err?.code?.startsWith('auth/'))throw Error('帳號或密碼不正確，或登入暫時受限。');
        throw err;
      }
      return '';
    });});
    root.append(f);
  }
  async function showProof(id,box,token){
    const d=await get(proof(id));if(!alive(token)||!box.isConnected)return;
    if(!d.exists()){box.textContent='尚未附照片。';return;}
    const b=d.data().jpeg.toUint8Array();
    if(b.length<4||b.length>limit||b[0]!==255||b[1]!==216||b[2]!==255)throw Error('此附件不是可預覽的 JPEG。');
    const url=URL.createObjectURL(new Blob([b],{type:'image/jpeg'}));urls.add(url);
    const photo=make('img');photo.src=url;photo.alt='請假證明照片';
    const hide=button('關閉照片',()=>{URL.revokeObjectURL(url);urls.delete(url);box.replaceChildren();},true);
    box.replaceChildren(photo,hide);
  }
  async function syncPayroll(id,user,token){
    if(!integrate||!alive(token))throw Error('請從薪資後台的主管入口操作。');
    const d=await get(ref(id));if(!d.exists()||d.data().scope!=='production'||d.data().status!=='approved')throw Error('假單已變更，請刷新清單。');
    if(!alive(token))return;
    const request=d.data();
    let result=await integrate(request,id);
    if(result.confirmation){
      if(!alive(token))return;
      const {name,empNo,token:match}=result.confirmation;
      if(!confirm('首次核對請假帳號\n教室日誌姓名：'+request.employeeLabel+'\n薪資員工：'+name+'（工號 '+empNo+'）\n\n確認是同一人，才會綁定並帶入本張假單。'))return '假單已核准，尚未綁定或帶入考勤。';
      const latest=await get(ref(id));
      if(!alive(token))return;
      if(!latest.exists()||latest.data().scope!=='production'||latest.data().status!=='approved')throw Error('假單已變更，請刷新清單。');
      result=await integrate(latest.data(),id,match);
    }
    if(!result.ok)throw Error('假單已核准，尚未帶入考勤：'+result.error);
    await fs.updateDoc(ref(id),{status:'applied',settledBy:user.uid,settledAt:sent()});
    return '已核准並帶入考勤。';
  }
  function card(row,user,refresh){
    const {id}=row,d=row.data(),box=make('article');box.className='lv-record';
    box.append(make('h4',(mode==='manager'?value(d.employeeLabel)+' ｜ ':'')+d.date+' ｜ '+(types[d.type]||'假單')));
    box.dataset.status=d.status;
    const state=make('span',labels[d.status]||'待核對');state.className='lv-status';
    const detail=make('p');detail.append(value(d.minutes?d.start+'–'+d.end+'（時段 '+d.minutes+' 分鐘，依班表核對）':'整班'), ' ｜ ',state);box.append(detail);
    const bar=make('div');bar.className='lv-actions';const photo=make('div');box.append(bar,photo);
    bar.append(button('查看證明',()=>action(async token=>{await showProof(id,photo,token);return '證明查閱完成。';}),true));
    const proofOnline=d.scope!=='production'||d.proofOnline===true;
    if(mode==='staff'&&proofOnline&&['pending','needsProof'].includes(d.status)){
      box.append(make('p','補上證明照片（一張）'));const upload=photoFields(box);
      bar.append(button('補上證明',()=>action(async token=>{
        const bytes=await jpeg(upload.file());if(!alive(token))return;
        await fs.setDoc(proof(id),{jpeg:fs.Bytes.fromUint8Array(bytes),createdAt:sent()});upload.clear();return '照片已上傳。';
      })));
    }
    if(mode==='staff'&&['pending','needsProof'].includes(d.status)){
      bar.append(button('撤回',()=>{if(confirm('要撤回這張假單嗎？'))action(async token=>{
        await fs.updateDoc(ref(id),{status:'withdrawn',withdrawnAt:sent()});if(alive(token))await refresh(token);return '假單已撤回。';
      });},true));
    }
    if(mode==='manager'&&['pending','needsProof'].includes(d.status)){
      const review=async(status,token)=>{
        const p={status,proofRequired:status==='needsProof'||d.proofRequired,reviewAt:sent(),reviewBy:user.uid};
        await fs.updateDoc(ref(id),p);
        let msg=status==='needsProof'?'已標記待補證明。':'已標記未核准。';
        try{if(status==='approved'&&alive(token))msg=await syncPayroll(id,user,token);}
        finally{if(alive(token))await refresh(token);}
        return msg;
      };
      bar.append(button(d.payrollMatch==='journalName'?'核准並核對考勤':'核准並帶入考勤',()=>action(token=>review('approved',token))));
      if(proofOnline)bar.append(button('要求補證明',()=>action(token=>review('needsProof',token)),true));
      else box.append(make('p','證明請在櫃台核對，不收線上照片。'));
      bar.append(button('不核准',()=>{if(confirm('確定不核准這張假單？'))action(token=>review('rejected',token));},true));
      if(d.proofRequired)box.append(make('p','此單已要求證明，須先上傳。'));
    }
    if(mode==='manager'&&d.status==='approved'&&integrate){
      bar.append(button('重試帶入考勤',()=>action(async token=>{try{return await syncPayroll(id,user,token);}finally{if(alive(token))await refresh(token);}})),
        button('已人工處理',()=>{if(confirm('請先確認這筆假單已在考勤完成核對或有更正紀錄。確定標成已人工處理？'))action(async token=>{
          await fs.updateDoc(ref(id),{status:'manual',settledBy:user.uid,settledAt:sent()});if(alive(token))await refresh(token);return '已標記人工處理；本操作不另寫入薪資。';
        });},true));
    }
    return box;
  }
  async function checkDates(user,dates){
    const response=await fetch('https://asia-east1-bhcs-leave.cloudfunctions.net/checkLeaveDates',{
      method:'POST',headers:{Authorization:'Bearer '+await user.getIdToken(),'Content-Type':'application/json'},
      body:JSON.stringify({dates}),credentials:'omit',cache:'no-store',redirect:'error',signal:AbortSignal.timeout(12000)
    });
    if(!response.ok)throw Error('未能核對同日請假狀態，請稍後重試，或至櫃台登記冊確認。');
    const result=(await response.json()).dates;
    if(!Array.isArray(result)||result.some(d=>!dates.includes(d)))throw Error('未能核對同日請假狀態。');
    return result;
  }
  function submitForm(user){
    const section=make('section');section.id='leave-apply';section.className='lv-section';root.append(section);
    const f=make('form');section.append(make('h3','新增請假'),f);
    if(member.formalPayroll!==true)section.append(make('p','此帳號僅供試用。請勿填真實資料或證明，不會帶入正式薪資。'));
    const step=(title)=>{const block=make('fieldset');block.className='lv-step';block.append(make('legend',title));f.append(block);return block;};
    const datesStep=step('1. 選日期');
    const layout=make('div');layout.className='lv-two';datesStep.append(layout);
    const from=field(layout,'開始日期',make('input')),to=field(layout,'結束日期（單日可留空）',make('input'));
    from.type=to.type='date';from.required=true;
    const details=step('2. 選假別與時段');
    const type=field(details,'假別',make('select'));
    for(const [k,v] of Object.entries(types)){const o=make('option',v);o.value=k;type.append(o);}
    const mode=field(details,'請假時段',make('select'));for(const [k,v] of [['full','整班'],['part','部分時段']]){const o=make('option',v);o.value=k;mode.append(o);}
    const part=make('div');part.hidden=true;details.append(part);
    const start=field(part,'開始時間（每天相同）',make('input')),end=field(part,'結束時間（每天相同）',make('input'));
    start.type=end.type='time';
    const period=make('p');period.setAttribute('aria-live','polite');part.append(period);
    function showMinutes(){
      period.textContent='';
      if(start.value&&end.value)try{period.textContent='時段長度 '+elapsedMinutes(start.value,end.value)+' 分鐘。不固定扣休息時間，實際請假分鐘由主管按當日班表核對。';}catch(e){period.textContent=e.message;}
    }
    start.oninput=end.oninput=showMinutes;
    mode.onchange=()=>{part.hidden=mode.value!=='part';for(const el of [start,end])el.required=!part.hidden;showMinutes();};
    const days=make('fieldset'),dayFields=make('div');days.hidden=true;dayFields.className='lv-date-options';
    days.append(make('legend','選擇實際有排班、要請假的日期'),dayFields);datesStep.append(days);
    const warns=make('p');warns.setAttribute('role','status');f.append(warns);
    let checks=[],datesKey='',ackKey='';
    function showDates(){
      ackKey='';warns.textContent='';let selected=[];
      try{selected=datesBetween(from.value,to.value||from.value);}catch{}
      const next=selected.join(',');
      if(next===datesKey)return;
      datesKey=next;checks=[];dayFields.replaceChildren();days.hidden=selected.length<=1;
      for(const date of selected){
        const input=make('input');input.type='checkbox';input.value=date;input.checked=selected.length===1;
        input.onchange=()=>{ackKey='';warns.textContent='';};
        field(dayFields,date,input);checks.push(input);
      }
    }
    const summary=make('p','先選開始日期。');summary.className='lv-summary';summary.setAttribute('aria-live','polite');datesStep.append(summary);
    const updateSummary=()=>{
      const n=checks.filter(x=>x.checked).length;
      summary.textContent=n?'已選 '+n+' 天要請假。':checks.length?'請勾選要請假的日期。':'請選擇有效的起訖日期。';
    };
    const dateChanged=()=>{if(from.value)to.min=from.value;else to.removeAttribute('min');showDates();updateSummary();};
    dayFields.addEventListener('change',updateSummary);
    from.onchange=to.onchange=dateChanged;
    f.append(make('p','選多天可一次送出，主管逐日核對。各天時段不同時，請分次送出。'));
    if(cfg.checkDateOccupancy!==true)f.append(make('p','同日請假名額請先至櫃台登記冊確認。'));
    const online=member.formalPayroll!==true||member.formalProofOnline===true;
    const attach=make('details');attach.className='lv-attach';attach.hidden=!online;attach.append(make('summary','3. 附證明（如果需要）'));f.append(attach);
    attach.append(make('p','可現在拍照或稍後補件。同一張照片會附在這次勾選的每一天；若證明不同，請分次送出。'));
    const file=online?photoFields(attach):{file:()=>null,clear:()=>{}};
    if(!online)f.append(make('p','如需請假證明，請至櫃台核對；此入口暫不收照片。'));
    attach.append(make('p',member.formalPayroll===true?'只提供核對假別所需的證明，請先遮住無關的身分證號、病歷內容及他人資料。':'請用空白紙試拍，不要上傳真實證明。'));
    const send=make('button','送出假單');send.type='submit';f.append(send);
    let docIds=[], submittedJson='';
    f.addEventListener('submit',event=>{event.preventDefault();action(async token=>{
      const all=datesBetween(from.value,to.value||from.value);
      const chosen=all.length===1?all:checks.filter(x=>x.checked).map(x=>x.value);
      if(!chosen.length||chosen.some(x=>!all.includes(x)))throw Error('請勾選至少一個實際有排班的日期。');
      const partial=mode.value==='part',m=partial?elapsedMinutes(start.value,end.value):0;
      const entries=chosen.map(date=>({...(member.formalPayroll===true?{scope:'production',proofOnline:online,...(['empNo','journalName'].includes(member.payrollMatch)?{payrollMatch:member.payrollMatch}:{})}:{}),owner:user.uid,employeeId:member.employeeId,employeeLabel:member.label,date,type:type.value,minutes:m,start:partial?start.value:'',end:partial?end.value:'',status:'pending',proofRequired:false}));
      const payload=JSON.stringify(entries);
      const current=async docs=>Promise.all(docs.map(doc=>get(doc).catch(e=>{if(e.code==='permission-denied')return null;throw e;})));
      let existing=await current(docIds);
      if(docIds.length&&submittedJson!==payload){
        if(existing.some(d=>d?.exists()))throw Error('前一次假單可能已送出，請先重新整理確認。');
        docIds=[];existing=[];
      }
      if(existing.some(d=>d?.exists())&&!existing.every(d=>d?.exists()))throw Error('請先重新整理確認已送出的假單。');
      if(!existing.length||!existing.every(d=>d?.exists())){
        let occupied;
        try{occupied=cfg.checkDateOccupancy===true?await checkDates(user,chosen):[];}catch(e){
          if(!alive(token))return;
          // An outage in a staffing advisory must never block filing leave.
          const missing='無法核對同日請假狀態，請至櫃台登記冊確認。';
          if(ackKey!==payload+'unavailable'){warns.textContent=missing;ackKey=payload+'unavailable';return '確認後，可再按一次送出假單。';}
        }
        if(!alive(token))return;
        if(occupied?.length){
          const key=payload+occupied.join(',');
          warns.textContent=occupied.join('、')+'：'+occupiedMessage;
          if(ackKey!==key){ackKey=key;return '確認後，可再按一次送出，交由主管協調。';}
        }else if(occupied){warns.textContent='';}
        const bytes=file.file()?await jpeg(file.file()):null;
        if(!alive(token))return;
        if(!docIds.length){docIds=entries.map(()=>fs.doc(requests));submittedJson=payload;}
        const batch=fs.writeBatch(db);
        for(const [i,doc] of docIds.entries()){
          batch.set(doc,{...entries[i],createdAt:sent()});
          if(bytes)batch.set(proof(doc.id),{jpeg:fs.Bytes.fromUint8Array(bytes),createdAt:sent()});
        }
        await batch.commit();
      }
      docIds=[];submittedJson='';
      f.reset();mode.onchange();attach.open=false;dateChanged();summary.textContent='先選開始日期。';
      if(alive(token)){try{await refreshList(token);}catch{return '已送出 '+chosen.length+' 天的假單。清單暫未更新，請重新整理，不必重送。';}}
      return '已送出 '+chosen.length+' 天的假單，等待主管核對。';
    });});
  }
  let refreshList=async()=>{};
  const unsubscribe=au.onAuthStateChanged(auth,async user=>{
    const token=++epoch;rev++;
    if(closed)return;
    if(!user){member=null;showLogin();return;}
    base();say('核對帳號權限…');
    try{
      const p=await get(person(user.uid));if(!alive(token))return;
      member=p.data();
      if(!p.exists()||member.active!==true||member.role!==mode||mode==='staff'&&(!member.employeeId||!member.label)){
        base();say('這個帳號沒有此入口的權限。');
        root.append(button('登出並切換帳號',()=>signOutAll()));return;
      }
      const controls=make('div');controls.className='lv-actions';root.append(controls);
      const results=make('div');results.id='leave-records';results.className='lv-section';
      if(mode==='staff'){
        const nav=make('nav');nav.className='lv-quick';nav.setAttribute('aria-label','請假頁面捷徑');
        for(const [href,name] of [['#leave-apply','我要請假'],['#leave-records','我的申請進度']]){
          const a=make('a',name);a.href=href;nav.append(a);
        }root.insertBefore(nav,controls);
      }
      const groups=mode==='manager'?{
        open:make('div'),closed:make('div')
      }:null;
      const month=mode==='manager'?make('input'):null;
      if(month){month.type='month';month.value=new Intl.DateTimeFormat('en-CA',{year:'numeric',month:'2-digit',timeZone:'Asia/Taipei'}).format(new Date());field(controls,'請假月份',month);}
      let cursor=null;
      refreshList=async function(t,more=false){
        const current=++rev;
        const parts=mode==='staff'?[fs.where('owner','==',user.uid)]:[fs.where('scope','==','production')];
        if(mode==='staff'&&member.formalPayroll===true)parts.push(fs.where('scope','==','production'));
        if(month&&/^20\d{2}-(0[1-9]|1[0-2])$/.test(month.value))parts.push(fs.where('date','>=',month.value+'-01'),fs.where('date','<=',month.value+'-31'));
        parts.push(fs.orderBy('date','desc'));
        if(more&&cursor)parts.push(fs.startAfter(cursor));
        parts.push(fs.limit(50));
        const response=await fs.getDocsFromServer(fs.query(requests,...parts));
        if(!alive(t)||current!==rev)return;
        if(!more){
          objectsClear();results.replaceChildren();
          if(groups){
            groups.open.replaceChildren();groups.closed.replaceChildren();
            results.append(make('h4','待處理'),groups.open,make('h4','已處理'),groups.closed);
          }
        }
        results.querySelector('.lv-more')?.remove();
        cursor=response.docs.at(-1)||null;
        if(response.empty&&!more&&!groups)results.append(make('p','你還沒有送出假單。'));
        for(const row of response.docs){
          const status=row.data().status;
          const target=!groups?results:['pending','needsProof','approved'].includes(status)?groups.open:groups.closed;
          target.querySelector('.lv-empty')?.remove();
          target.append(card(row,user,refreshList));
        }
        if(groups)for(const group of [groups.open,groups.closed])if(!group.children.length){
          const empty=make('p',response.size===50?'已載入的正式假單中沒有此類紀錄。':'目前沒有此類假單。');empty.className='lv-empty';group.append(empty);
        }
        if(response.size===50){const moreBtn=button('顯示更多',()=>action(t=>refreshList(t,true)),true);moreBtn.classList.add('lv-more');results.append(moreBtn);}
      };
      if(month)month.onchange=()=>action(t=>refreshList(t));
      controls.append(button('重新整理假單',()=>action(async t=>{await refreshList(t);return '已重新整理。';}),true),button('登出',()=>signOutAll(),true));
      if(mode==='staff')submitForm(user);
      list(mode==='staff'?'我的申請進度':'正式員工假單',results);
      await refreshList(token);if(alive(token))say('');
    }catch(e){if(alive(token)){base();say(uiError(e));root.append(button('登出',()=>signOutAll(),true));}}
  });
  return ()=>{closed=true;epoch++;unsubscribe();objectsClear();root.replaceChildren();signOutAll().catch(()=>{});};
}
