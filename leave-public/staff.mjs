import { mountLeave } from './portal.mjs';
const root=document.querySelector('#leave-root');
mountLeave(root,'staff').catch(()=>{root.textContent='員工入口尚未啟用或連線失敗，請洽主管。';});
