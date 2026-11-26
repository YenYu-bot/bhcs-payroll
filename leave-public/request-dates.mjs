export const occupiedMessage='已有人請假，請至櫃台登記冊確認';
export const maxRequestDays=14;
export function actualDate(s){
  return /^20\d\d-\d\d-\d\d$/.test(s)&&Number.isFinite(Date.parse(s))&&new Date(s).toISOString().slice(0,10)===s;
}
export function datesBetween(from,to){
  if(!actualDate(from)||!actualDate(to)||to<from)throw Error('請選擇有效的起訖日期。');
  const start=Date.parse(from), end=Date.parse(to), day=86400000;
  if((end-start)/day>=maxRequestDays)throw Error('每次最多選 14 個日曆日；較長假期請分次送出。');
  const out=[];
  for(let d=start;d<=end;d+=day)out.push(new Date(d).toISOString().slice(0,10));
  return out;
}
export function elapsedMinutes(start,end){
  const time=s=>/^([01]\d|2[0-3]):[0-5]\d$/.test(s)?Number(s.slice(0,2))*60+Number(s.slice(3)):NaN;
  const m=time(end)-time(start);
  if(!Number.isInteger(m)||m<1||m>480)throw Error('請確認部分時段的起訖時間；跨日時請分日填寫。');
  return m;
}
