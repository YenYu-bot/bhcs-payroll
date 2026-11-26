const test=require('node:test');
const assert=require('node:assert/strict');
const {validDays,staffLease,occupiedDays}=require('../leave-functions/occupancy.cjs');
test('inclusive leap-day range, explicit bounded dates; 4 actual working hours are 240 minutes',async()=>{
 const {datesBetween,elapsedMinutes,occupiedMessage}=await import('../leave-public/request-dates.mjs');
 assert.deepEqual(datesBetween('2028-02-28','2028-03-01'),['2028-02-28','2028-02-29','2028-03-01']);
 assert.equal(datesBetween('2026-12-25','2027-01-07').length,14);
 for(const [a,b] of [['2027-02-29','2027-03-01'],['2027-01-03','2027-01-02'],['2026-12-25','2027-01-08']]) assert.throws(()=>datesBetween(a,b));
 assert.equal(elapsedMinutes('15:00','19:00'),240);
 assert.equal(elapsedMinutes('17:30','19:00'),90); // Before schedule review, no assumed rest.
 assert.throws(()=>elapsedMinutes('19:00','18:00'));
 assert.equal(occupiedMessage,'已有人請假，請至櫃台登記冊確認');
});
test('advisory exposes only dates for other people who have active requests',async()=>{
 const days=['2026-12-01','2026-12-02','2026-12-03','2026-12-04'];
 const fixtures={ [days[0]]:[{owner:'staff-a',status:'approved'}],[days[1]]:[{owner:'staff-b',status:'withdrawn'},{owner:'staff-c',status:'rejected'}],
 [days[2]]:[{owner:'staff-b',status:'needsProof',type:'private'},{owner:'staff-b',status:'pending'}],[days[3]]:[{owner:'staff-d',status:'manual'}] };
 assert.deepEqual(await occupiedDays(days,'staff-a',d=>fixtures[d]),days.slice(2));
 assert.equal(validDays(days),true);
 for(const bad of [[],[days[0],days[0]],['2026-02-30'],['2026-12-01','2026-12-15']])assert.equal(validDays(bad),false);
});
test('advisory requires a current employee login and matching binding',()=>{
 const member={role:'staff',active:true,journalBindingVersion:1}, token={uid:'a',firebase:{sign_in_provider:'custom'},journalBinding:1,journalUntil:145};
 assert.ok(staffLease('a',token,member,100));
 for(const wrong of [{...token,journalUntil:100},{...token,journalBinding:2},{...token,firebase:{sign_in_provider:'google.com'}},{...token,uid:'b'}])assert.equal(staffLease('a',wrong,member,100),false);
 assert.equal(staffLease('a',token,{...member,active:false},100),false);
});
