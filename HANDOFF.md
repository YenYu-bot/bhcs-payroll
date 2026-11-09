# 百宏薪資試算系統（bhcs-payroll）交接文件

> 交接日期：2026-11-07｜前任開發：Claude｜接手：ChatGPT
> 使用者：百宏文教機構負責人（台中北屯補習班），系統的唯一管理者與審核者。

## 1. 專案概要

| 項目 | 內容 |
|---|---|
| 用途 | 百宏文教機構員工薪資試算：出勤匯入、加班費、請假、特休、勞健保、薪資單、薪資紀錄 |
| 型態 | **零依賴單一 HTML 檔**（`index.html`，約 1,860 行，CSS + HTML + JS 全在同一檔） |
| Repo | https://github.com/YenYu-bot/bhcs-payroll （public，branch `main`） |
| 網址 | https://yenyu-bot.github.io/bhcs-payroll/ （GitHub Pages，由 `main` 根目錄部署） |
| 雲端 | Firebase 專案 `bhcs-payroll`（Spark 免費方案，Firestore 位置 asia-east1），只用 Auth（Google 登入）＋ Firestore |
| 唯一外部依賴 | 雲端同步啟用時才動態載入 Firebase JS SDK `10.12.2`（gstatic CDN）；其餘全部原生 JS |
| 語言 | 介面與文件皆為繁體中文（台灣用語） |

## 2. 目前狀態與待辦（交接時）

**使用者正在進行中：**
1. Firebase 後台 → Authentication → 设置 → 已获授权的网域：加入 `yenyu-bot.github.io`。第一次登入時已出現「網域未授權」，這是唯一卡住的地方。
2. 在新網址第一次登入前，先在舊版系統匯出備份，再到新版匯入，然後設定薪資密碼並上傳雲端。
3. Firestore 規則中的允許 email 由使用者自行填寫。我沒有看到實際 email，若出現「此帳號沒有權限」，就是規則 email 與登入帳號不符。

**尚未經真實環境驗證：**
- 雲端同步只在**模擬 Firebase**（自寫 mock 模組＋測試伺服器）測過完整雙機流程，全部通過；尚未連真 Firebase 跑過。第一次真實登入後請協助確認。
- 真實打卡檔（2026-10，7 位員工）已實測匯入與計算。

**已知限制／可能的下一步：**
- 2026 勞健保級距表、國定假日清單、基本工資（29,500／196）都是 2026 年資料，**每年需更新**（`LABOR`、`HEALTH`、`HOLIDAYS_2026`、`MIN_MONTH`、`MIN_HOUR`）。
- 未實作：二代健保補充保費、薪資所得扣繳、勞保職災費率（雇主負擔）、多人帳號權限分級。
- 密碼為單一薪資密碼，異動紀錄沒有操作者身分（雲端 meta 只記 `updatedBy` email）。
- Firestore 單一文件上限 1 MiB：`core`（員工＋設定＋異動紀錄）的紀錄上限為 3,000 筆，月份資料各自一份文件。
- 曆年制離職結算的算法（以當年已給天數＋補足少於週年制的差額）有解讀空間，已提醒使用者向律師確認。

## 3. 檔案結構

Repo 只有三個檔案：`index.html`（系統本體）、`README.md`、`HANDOFF.md`。**直接編輯 `index.html` 即可**。前任開發時是拆成多段再拼接，但 repo 只保留拼好的成品，沒有建置流程。

`index.html` 內 `<script>` 依序分區（以 `/* ===== … ===== */` 標示）：

| 區段 | 主要內容 |
|---|---|
| 官方級距 | `LABOR`（勞保含就保，勞工自付）、`HEALTH`（健保本人自付）陣列 |
| 常數／設定 | `HOLIDAYS_2026`、`MIN_MONTH`、`MIN_HOUR`、`DEF_SETTINGS`、`state` |
| 日期工具 | 一律用 **UTC 毫秒**處理 `YYYY-MM-DD`：`pd`、`fd`、`addM`、`ymRange`、`curYM` |
| 儲存 | `blankRec`、`mrec(id,ym)`（取／建月份紀錄）、`peekRec`、`migrateV2`、`load`、`normalizeState` |
| 工資基礎 | `isHourly`、`wageBase`、`hourly`、`daily`、`holidaySet` |
| 出勤日曆 | `DST`（日狀態）、`DKIND`（類型）、`schedDay`／`schedFor`（每週七天排班＋寒暑假時間）、`workedH`、`dayAgg`、`monthLeave` |
| 加班費 | `otPayDay(type,h,hr,hourlyMode)`、`otSummary`（**逐日**分段） |
| 破月 | `employment(e,ym)`：在職日數、比例、勞保投保日數、健保月底在保 |
| 特休 | `annivSegs`、`calGrant`、`periodsFor`、`usageItems`、`leaveStatus`（含遞延、年度終結、遲到抵扣） |
| 遲到早退 | `lateRaw`、`processLate` |
| **計算核心** | `compute(e,ym)`（已確認則回傳 snapshot）、`computeLive(e,ym,r)`：產出 `earnings`、`deducts`、`reviews`、各種明細 |
| 畫面 1–6 | 員工設定、出勤上傳、本月核算、薪資單、特休總覽、薪資紀錄 |
| 打卡解析 | 零依賴 XLSX 讀取（`DecompressionStream`）、`parsePunch`、`derivePunch`、`ingestPunch`、`ingestSimple`（CSV） |
| 明細 modal | `openDet(id,kind)`，kind＝`day`／`ot`／`annual`／`late`／`items` |
| 匯出 | 零依賴 XLSX 產生器、`exportExcel`、`exportWord`（HTML-as-.doc）、`exportYear` |
| 密碼保護 | PBKDF2（250,000 次）＋AES-GCM；`save()` 在此定義（加密寫入＋觸發雲端上傳） |
| 異動紀錄／審核 | `addLog`、`empDiff`、`setReview`、`approveAll`、`reviewBlock` |
| 自訂薪資項目 | 員工固定加減項、本月加減項 |
| 雲端同步 | `FB_CONFIG`、`cloudInit`、`cloudSignIn`、`cloudConnect`、`cloudPull`、`cloudPush`、`cloudWatch` |
| boot | `bootUI()`；`load()` 回傳 `'locked'` 時顯示解鎖畫面；最後呼叫 `cloudInit()` |

## 4. 資料模型（`state`）

```js
state = {
  version: 3,
  settings: { hourlyHolidayOff:true,  // 依勞動契約：計時人員國定假日不排班、不給薪
              typhoonDates:'YYYY-MM-DD 說明\n…', typhoonPay:'unpaid'|'paid'（預設不給薪）, typhoonExtra:'0'|'0.5'|'1', absUnit:0|30|60, leaveDefault:'cal', prorateBase:'cal'|'30', calRound, holidays:'YYYY-MM-DD 名稱\n…',
              seasons:{summerStart,summerEnd,winterStart,winterEnd} },
  employees: [{ id, name, role, empNo, payType:'monthly'|'hourly', base, rate, ptRatio,
    hourBasis:'punch'|'sched', hourRound, brkMin, brkAfter, summer, perfect, otFixed,
    wagePerfect, wageSummer, fixedItems:[{name,type:'add'|'ded',amount,wage}],
    laborGrade, labor, healthGrade, healthDeps, health, meal, pensionWage, pensionSelf, insAuto,
    hire, leave, leaveSystem:'anniv'|'cal', yearEnd:'pay'|'defer', priorUsed, priorAsOf,
    sickPolicy:'prorate'|'none', voidPersonal, lateePolicy:'annualOffset'|'both'|'voidPerfect'|'deduct',  // 預設 annualOffset＋lateFallback 'both'
    lateGrace, lateUnit, lateFallback:'both'|'deduct'|'void',
    sched:{ tpl:{type,start,end,sStart,sEnd,wStart,wEnd},   // 快速排班範本
            d0..d6:{ type:'work'|'none'|'rest'|'off', start,end, sStart,sEnd, wStart,wEnd, useTpl } } }],  // useTpl＝套用範本（值已複製進該日）
  months: { 'YYYY-MM': { [empId]: {
    att:{sick,menstrual,personal,family,paidLeave,extraHours},   // 單位：小時（手動額外輸入）
    days:[{date,wk,in,out,wh(分),punches,abnormal,kind,status,hours,manual}],  // 應出勤日曆
    otEvents:[{date,type,hours}], annualEvents:[{date,hours}], lateEvents:[{date,late,early}],
    absChoice:{[date]:{type,hours,min}},   // 單日缺勤逾 60 分的處理（事假/病假/特休…/late＝維持遲到早退）
    items:[{name,type,amount,note}], otherBonus, otherDeduct, overrides:{[項目名]:金額},
    reviews:{[key]:{d:'ok'|'no', v:簽章, t}}, confirmed, confirmedAt, snapshot } } },
  log: [{t, action, detail, ym, emp}]
}
```

- 舊格式相容：舊版 `sched.weekday/sat/sun`（`rest` 布林）會由 `schedDay()` 自動轉換；v2 資料（`bhcs_payroll_v2`）由 `migrateV2()` 轉換。
- localStorage key：`bhcs_payroll_v3`（明文）／`bhcs_payroll_v3_enc`（加密）／`bhcs_payroll_cloud`、`bhcs_payroll_cloudmeta`（雲端旗標與同步版本）。
- 注意：GitHub Pages 的所有專案共用 `yenyu-bot.github.io` 同一個 origin，localStorage 互相讀得到，所以才需要密碼加密。

## 5. 已實作的計算規則（含法源）

- **特休 §38**：週年制／曆年制（按年資期間落在該年的天數比例）、遞延（遞延日數優先扣除）、年度終結與離職未休工資（施行細則 §24-1，日薪＝工資基礎÷30）、部分工時按比例。
- **工資基礎**：底薪＋勾選的全勤、暑期津貼、固定加項（「計入工資」）；時薪＝÷240、日薪＝÷30。計時人員以時薪為基礎。
- **加班 §24／§32／§36／§39／§40**：逐日計算；平日延長 4/3、5/3；休息日 4/3、5/3、8/3；國定假日 8 小時內加發一日工資（計時人員為加發時薪×時數）；例假日出勤加倍並警示；延長工時超過 46 小時警示；定額加班費＝max(定額, 法定)。
- **請假（勞工請假規則 §4、§9；性平法 §14、§21）**：病假年度 30 日內半薪、超過不給薪；生理假每年 3 日不併入病假；全勤不得因婚喪公假、家庭照顧假、生理假而扣；病假只能按比例扣全勤（全勤×病假日數÷30）。
- **特休 12 月結算**：使用者的做法是每年 12 月薪資結算特休，所以新員工預設**曆年制**（施行細則 §24 II ②）；曆年制未休工資在 12 月薪資自動產生（審核 `annualPay`）。週年制年度終結在到職週年日，須 30 日內發給（§24-1），特休總覽會提示並提供「全部改為曆年制」。
- **休息日調移**（使用者已於勞動契約約定）：假日清單中名稱含「休息日調移」的日期（`swapSet()`），對**排班中有休息日的員工**改為休息日（`schedFor` 回傳 `swapped:'toRest'`），同週原休息日改為工作日（`'toWork'`），該日若為國定假日即當天放假照給、不另補假；此日期自 `holidaySet()` 排除。2026 預設 `2026-10-09 休息日調移`（取代原「國慶日補假」，舊設定由 `normalizeState`／`swapV1` 轉換）。沒有休息日的兼職人員不調移：國定假日落在其工作日即當天放假。
- **颱風假**（勞動部「天然災害發生事業單位勞工出勤管理及工資給付要點」，114-09-19 修正）：`settings.typhoonDates` 的日子，沒打卡＝日狀態 `typhoon`、有打卡＝類型 `typhoonWork`，當天遲到早退不計（`lateRaw` 排除）；不算缺勤、不影響全勤。未出勤工資依 `typhoonPay`（使用者確認：勞動部為「宜不扣發」之建議，預設不給薪，月薪扣日薪並審核 `typhoon`；可改照給）；計時人員照給排班時數（審核 `typhoon`）；出勤加給依 `typhoonExtra`（審核 `typhoonExtra`）。缺勤處理與 CSV 假別也可選颱風假。
- **單日缺勤逾 1 小時**（`core7` 區段：`absenceItems`、`openAbs`、`setAbs`）：單日遲到加早退超過 60 分、或整天未打卡（且該日是工作日），匯入後自動跳出「缺勤處理」，逐筆選擇假別；時數依 `settings.absUnit` 進位。選定後該日的遲到早退由 `lateRaw` 排除，改由 `dayAgg` 計入假別時數。未處理的筆數納入 `attend` 審核簽章。
- **遲到早退**：每月寬限；超過寬限的處理**順序**（使用者指定）：① 單日逾 1 小時者先在「缺勤處理」選假別 → ② 其餘分鐘以特休優先抵扣（`annualOffset`，依抵扣單位進位，需審核 `lateOffset`） → ③ 特休不足或沒有特休的部分取消全勤＋按實際分鐘比例扣薪（`lateFallback:'both'`）。舊資料由 `normalizeState`（`latePolicyV3`）一次性轉換並記錄；扣薪依實際分鐘數；計時人員依打卡實際工時計薪時不另扣；以特休抵扣依 §38 須員工申請，列入審核。
- **破月**：底薪、津貼、固定加項依在職日數比例；勞保、勞退依投保日數（每月以 30 日計）；健保看月底在保。
- **打卡機檔案格式**（真實檔已驗證）：欄位為「系統編號、員工編號、中文姓名、英文姓名、上班天數、異常天數、上班時數、序號、日期、星期、打卡時間、備註」。每位員工第一列有姓名；每天有一列只有日期，下一列起才是打卡時間；備註 `WH=08H05` 是當日工時，`*WH=` 表示異常。**列出的日期＝排班日**（含未打卡日），未打卡＝列出天數－上班天數。

## 6. 人工審核機制（使用者明確要求）

使用者要求：**所有系統自動更正或補足的內容都必須人工審核**。`computeLive` 內用 `decide(key,…)` 產生審核項目，薪資單上逐項按「通過」或「不採用」；有待審核項目時無法確認薪資單；金額變動（簽章不同）後自動回到待審核。

審核 key：`ot`（依打卡算的加班費）、`otTopUp`（定額補足差額）、`holPay`（計時人員國定假日照給）、`annualPay`（特休未休工資）、`insProrate`、`partial`（破月）、`perfect`（全勤扣發）、`absent`（曠職）、`late`、`lateOffset`（特休抵扣，須員工同意）、`sickUnpaid`、`attend`（出勤資料確認，只能「確認無誤」）。

**新增任何自動調整金額的邏輯時，務必也加上 `decide()` 審核項目。**

## 7. 安全與雲端

- **密碼**：PBKDF2-SHA256 250k ＋ AES-GCM 256。本機與備份檔都加密；閒置 15 分鐘自動鎖定；忘記密碼無法復原。
- **雲端（Firestore 只存密文）**：
  - collection `payroll`：`meta` 存 `{rev, salt, parts[], updatedBy, updatedAt}`；`core` 與各 `m_YYYY-MM` 存 `{ct, iv}`。
  - 上傳用 `runTransaction`：比對 `meta.rev` 與本機 `cloud.rev`，不同就判定為衝突，停止上傳並顯示橘色提示，由使用者選擇「載入雲端版本」或「以本機覆蓋雲端」。
  - `onSnapshot(meta)` 偵測其他電腦更新；修改後 2 秒 debounce 自動上傳；變更密碼時以新 salt 重傳全部資料。
- **Firestore 規則**（使用者已發布，email 由使用者填）：

```
match /payroll/{document=**} { allow read, write: if request.auth != null
  && request.auth.token.email_verified == true && request.auth.token.email in ['…']; }
match /{document=**} { allow read, write: if false; }
```

- `FB_CONFIG` 寫在 `index.html` 裡，這是正常做法（Firebase web config 非機密），安全由規則把關。**不要**加入服務帳戶金鑰。

## 8. 開發與測試慣例

- 每次修改用 headless Chrome（Playwright）實際跑：匯入真實打卡檔、計算金額並手算比對、截圖檢查版面，確認沒有 JS 錯誤後才推送。
- 雲端功能測試時，以 `window.FB_BASE` 指向本機 mock 的 Firebase 模組（同名 API：initializeApp、getAuth、onAuthStateChanged、signInWithPopup、GoogleAuthProvider、signOut、getFirestore、doc、getDoc、runTransaction、onSnapshot、serverTimestamp）。
- commit 訊息用中文，條列改了什麼；直接 push `main`（GitHub Pages 自動部署）。

## 9. 使用者偏好（請遵守）

- 溝通直接、精簡，不要冗長；希望你直接動手做，不要每一步都問。
- **結論必須用真實資料驗證**，不要編造答案或解釋；查不到就說查不到。
- 法律判斷尊重專業（使用者有委任律師處理一件勞動訴訟）：系統提供計算與法條依據，有解讀空間的地方標示出來，交由律師判斷，不要自行下定論。
- 系統自動調整的金額一律交由使用者審核（見第 6 節）。

## 10. 版本歷程（main）

1. 初始版本 v3.1：分月儲存、逐日加班、特休週年／曆年、病假全勤合規、離職與年度終結特休工資、破月勞健保、v2 資料遷移
2. 寒暑假班表與例假日判定
3. 人工審核、薪資紀錄、異動紀錄、密碼加密
4. 每週七天彈性排班、計時工時輸入、特休抵扣遲到、自訂薪資項目（並修正計時員工表單未切換的 bug）
5. 雲端同步（Firebase，端對端加密）
14. 計時人員國定假日不排班（依勞動契約，`settings.hourlyHolidayOff`，計算時於 `dayAgg` 排除，可隨時切換；出勤仍依 §39 加倍）
13. 計時人員薪資單列出時數：各項目「時數 × 時薪」（`hourDetail`）、出勤摘要「計時工時」（`hoursTotal`），Word 同步
12. 休息日調移（10/9 休息日、10/10 國慶日放假，依勞動契約）
11. 薪資單「出勤摘要」：出勤、缺勤狀況、事假、病假、特休（本月，含遲到抵扣）、特休剩餘（`attSum`／`attPlain`，Word 與 Excel 同步）
10. 颱風假（天災停止上班）：不算缺勤、不扣全勤、工資照給／不給薪、出勤加給可設定
9. 遲到早退順序：特休優先抵扣 → 不足再取消全勤＋扣薪
8. 遲到早退逾寬限：預設取消全勤＋按分鐘扣薪
7. 特休 12 月結算（預設曆年制）、單日缺勤逾 1 小時跳出假別選擇、休息日／例假日未打卡不列為缺勤
6. 快速排班：排班表最上方「快速」列，勾選的日子套用（`applyTpl()`），未勾選手動輸入
