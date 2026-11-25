const sdk='https://www.gstatic.com/firebasejs/10.12.2/';
const types={annual:'特休',personal:'一般事假',sick:'普通傷病假',family:'家庭照顧假',carePersonal:'照顧家人事假',paidLeave:'婚／喪／公假',menstrual:'生理假',protectedSick:'其他不扣全勤病假（由主管核對）'};
const labels={pending:'待審核',needsProof:'待補證明',approved:'已核准，待登記考勤',applied:'已核准，已帶入考勤',manual:'已核准，主管已人工處理',rejected:'未核准',withdrawn:'已撤回'};
const limit=650000;
const value=(x)=>String(x??'');
const make=(tag,content)=>{const e=document.createElement(tag);if(content!=null)e.textContent=content;return e;};
const button=(title,action,alt=false)=>{const b=make('button',title);b.type='button';if(alt)b.className='alt';b.addEventListener('click',action);return b;};
function field(form,title,input){const l=make('label',title);l.append(input);form.append(l);return input;}
const tm=(s)=>{const [h,m]=s.split(':').map(Number);return h*60+m;};
function actualDate(s){return /^20\d\d-\d\d-\d\d$/.test(s)&&Number.isFinite(Date.parse(s))&&new Date(s).toISOString().slice(0,10)===s;}
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
  if(!config?.apiKey||config.projectId==='bhcs-payroll'||!/^https:\/\//.test(staffOrigin)||!/^https:\/\//.test(managerOrigin)||staffOrigin===managerOrigin||
      location.origin!==(mode==='staff'?staffOrigin:managerOrigin))throw Error('入口或專案設定不正確。');
  const [fa,au,fs]=await Promise.all(['app','auth','firestore'].map(n=>import(sdk+'firebase-'+n+'.js')));
  const name='bhcs-leave-'+mode;
  const app=fa.getApps().find(x=>x.name===name)||fa.initializeApp(config,name);
  const auth=au.getAuth(app),db=fs.getFirestore(app);
  await au.setPersistence(auth,au.inMemoryPersistence);
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
  function showLogin(message=''){
    base();say(message);
    root.append(button('使用 Google 帳號登入',()=>action(()=>au.signInWithPopup(auth,new au.GoogleAuthProvider()).then(()=>''))));
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
    const d=await get(ref(id));if(!d.exists()||d.data().status!=='approved')throw Error('假單已變更，請刷新清單。');
    if(!alive(token))return;
    const result=await integrate(d.data(),id);
    if(!result.ok)throw Error('假單已核准，尚未帶入考勤：'+result.error);
    await fs.updateDoc(ref(id),{status:'applied',settledBy:user.uid,settledAt:sent()});
    return '已核准並帶入考勤。';
  }
  function card(row,user,refresh){
    const {id}=row,d=row.data(),box=make('article');box.className='lv-record';
    box.append(make('h4',(mode==='manager'?value(d.employeeLabel)+' ｜ ':'')+d.date+' ｜ '+(types[d.type]||'假單')));
    const state=make('span',labels[d.status]||'待核對');state.className='lv-status';
    const detail=make('p');detail.append(value(d.minutes?d.start+'–'+d.end+'，請假 '+d.minutes+' 分鐘':'整班'), ' ｜ ',state);box.append(detail);
    const bar=make('div');bar.className='lv-actions';const photo=make('div');box.append(bar,photo);
    bar.append(button('查看證明',()=>action(async token=>{await showProof(id,photo,token);return '證明查閱完成。';}),true));
    if(mode==='staff'&&['pending','needsProof'].includes(d.status)){
      box.append(make('p','補上證明照片（一張）'));const upload=photoFields(box);
      bar.append(button('上傳證明',()=>action(async token=>{
        const bytes=await jpeg(upload.file());if(!alive(token))return;
        await fs.setDoc(proof(id),{jpeg:fs.Bytes.fromUint8Array(bytes),createdAt:sent()});upload.clear();return '照片已上傳。';
      })),button('撤回',()=>{if(confirm('要撤回這張假單嗎？'))action(async token=>{
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
      bar.append(button('核准並帶入考勤',()=>action(token=>review('approved',token))),button('要求補證明',()=>action(token=>review('needsProof',token)),true),button('不核准',()=>{if(confirm('確定不核准這張假單？'))action(token=>review('rejected',token));},true));
      if(d.proofRequired)box.append(make('p','此單已要求證明，須先上傳。'));
    }
    if(mode==='manager'&&d.status==='approved'){
      bar.append(button('重試帶入考勤',()=>action(async token=>{try{return await syncPayroll(id,user,token);}finally{if(alive(token))await refresh(token);}})),
        button('已人工處理',()=>{if(confirm('請先確認這筆假單已在考勤完成核對或有更正紀錄。確定標成已人工處理？'))action(async token=>{
          await fs.updateDoc(ref(id),{status:'manual',settledBy:user.uid,settledAt:sent()});if(alive(token))await refresh(token);return '已標記人工處理；本操作不另寫入薪資。';
        });},true));
    }
    return box;
  }
  function submitForm(user){
    const f=make('form');root.append(make('h3','新增假單（每張一日）'),f);
    const date=field(f,'請假日期',make('input'));date.type='date';date.required=true;
    const type=field(f,'假別',make('select'));
    for(const [k,v] of Object.entries(types)){const o=make('option',v);o.value=k;type.append(o);}
    const mode=field(f,'請假時段',make('select'));for(const [k,v] of [['full','整班'],['part','部分時段']]){const o=make('option',v);o.value=k;mode.append(o);}
    const part=make('div');part.hidden=true;f.append(part);
    const start=field(part,'開始時間',make('input')),end=field(part,'結束時間',make('input')),min=field(part,'扣除休息後的請假分鐘',make('input'));
    start.type=end.type='time';min.type='number';min.min='1';min.max='480';min.step='1';min.inputMode='numeric';
    mode.onchange=()=>{part.hidden=mode.value!=='part';for(const el of [start,end,min])el.required=!part.hidden;};
    f.append(make('p','證明照片可現在上傳，也可稍後補。'));const file=photoFields(f);
    f.append(make('p','只拍必要的證明；請遮住無關的身分證號、病歷內容與他人資料。核准前不會帶入薪資考勤。'));
    const send=make('button','送出假單');send.type='submit';f.append(send);
    let docId=null, submittedJson='';
    f.addEventListener('submit',event=>{event.preventDefault();action(async token=>{
      if(!actualDate(date.value))throw Error('請選擇有效日期。');
      const partial=mode.value==='part',m=partial?Number(min.value):0;
      if(partial&&(!start.value||!end.value||!Number.isInteger(m)||m<1||m>480||m>tm(end.value)-tm(start.value)))throw Error('請填有效的起迄與扣除休息後的分鐘數。');
      const entry={owner:user.uid,employeeId:member.employeeId,employeeLabel:member.label,date:date.value,type:type.value,minutes:m,start:partial?start.value:'',end:partial?end.value:'',status:'pending',proofRequired:false};
      const payload=JSON.stringify(entry);
      if(docId&&submittedJson!==payload){
        const old=await get(docId).catch(e=>{if(e.code==='permission-denied')return null;throw e;});if(old?.exists())throw Error('前一張假單已送出，請先重新整理確認。');
        docId=null;
      }
      const bytes=file.file()?await jpeg(file.file()):null;
      if(!alive(token))return;
      if(!docId){docId=fs.doc(requests);submittedJson=payload;}
      const prior=await get(docId).catch(e=>{if(e.code==='permission-denied')return null;throw e;});
      if(!prior?.exists()){
        const batch=fs.writeBatch(db);batch.set(docId,{...entry,createdAt:sent()});
        if(bytes)batch.set(proof(docId.id),{jpeg:fs.Bytes.fromUint8Array(bytes),createdAt:sent()});
        await batch.commit();
      }
      docId=null;submittedJson='';
      f.reset();mode.onchange();
      if(alive(token))await refreshList(token);
      return '假單已送出，等待主管審核。';
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
        root.append(button('登出並切換帳號',()=>au.signOut(auth)));return;
      }
      const controls=make('div');controls.className='lv-actions';root.append(controls);
      const results=make('div');
      const month=mode==='manager'?make('input'):null;
      if(month){month.type='month';month.value=new Intl.DateTimeFormat('en-CA',{year:'numeric',month:'2-digit',timeZone:'Asia/Taipei'}).format(new Date());field(controls,'請假月份',month);}
      let cursor=null;
      refreshList=async function(t,more=false){
        const current=++rev;
        const parts=mode==='staff'?[fs.where('owner','==',user.uid)]:[];
        if(month&&/^20\d{2}-(0[1-9]|1[0-2])$/.test(month.value))parts.push(fs.where('date','>=',month.value+'-01'),fs.where('date','<=',month.value+'-31'));
        parts.push(fs.orderBy('date','desc'));
        if(more&&cursor)parts.push(fs.startAfter(cursor));
        parts.push(fs.limit(50));
        const response=await fs.getDocsFromServer(fs.query(requests,...parts));
        if(!alive(t)||current!==rev)return;
        if(!more){objectsClear();results.replaceChildren();}
        results.querySelector('.lv-more')?.remove();
        cursor=response.docs.at(-1)||null;
        if(response.empty&&!more)results.append(make('p','目前沒有假單。'));
        for(const row of response.docs)results.append(card(row,user,refreshList));
        if(response.size===50){const moreBtn=button('顯示更多',()=>action(t=>refreshList(t,true)),true);moreBtn.classList.add('lv-more');results.append(moreBtn);}
      };
      if(month)month.onchange=()=>action(t=>refreshList(t));
      controls.append(button('重新整理假單',()=>action(async t=>{await refreshList(t);return '已重新整理。';}),true),button('登出',()=>au.signOut(auth),true));
      if(mode==='staff')submitForm(user);
      list(mode==='staff'?'我的假單':'員工假單',results);
      await refreshList(token);if(alive(token))say('');
    }catch(e){if(alive(token)){base();say(uiError(e));root.append(button('登出',()=>au.signOut(auth),true));}}
  });
  return ()=>{closed=true;epoch++;unsubscribe();objectsClear();root.replaceChildren();au.signOut(auth).catch(()=>{});};
}
