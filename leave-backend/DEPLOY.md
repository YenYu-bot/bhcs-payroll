# 百宏請假入口：上線前檢查

這是薪資系統的請假模組，不另存一套薪資。版本庫只含 Firebase Web App 公開設定，不含正式會員、個資、附件、部署憑證或 Functions 的本機環境檔。沒有設定時，正式薪資不應受影響，主管模組會顯示尚未啟用。

## 權限與環境

1. 建立一個**獨立的 Firebase 專案**作為請假服務；絕不能用這套 Firestore 規則覆蓋現行薪資專案的規則。先用測試帳號、合成資料跑一輪。
2. 開設 Firestore、Firebase Hosting、Google Auth，登記主管薪資頁及員工入口網域。員工 Hosting 與薪資 GitHub Pages 必須是不同來源，避免共享瀏覽器端資料。方案不新增 Storage 公開下載網址。
3. `leave-public/config.mjs` 隨 GitHub Pages 與獨立 Firebase Hosting 提供**請假專案的公開 Web App 設定**與兩個正式來源。正式入口使用教室日誌既有公開 Web App 設定；功能部署參數另存本機 `leave-functions/.env.bhcs-leave`，不可加入版本庫。可發布 Web App 公開識別設定，不可加入 service account、私鑰、薪資密碼或個資。主管端 URL 是原薪資頁的「請假登記 → 開啟主管審核」。員工端只發布 `leave-public/` 到獨立 Hosting。
4. 在驗證非薪資專案的 project ID 後，以有權限的管理者部署，避免誤用預設專案：`firebase deploy --project <leave-project-id> --only firestore:rules,firestore:indexes,hosting`。索引就緒後才開放使用。
5. Firebase Auth 中取得已驗證的 Google 帳戶 UID，由授權部署管理者建 `leaveMembers/{uid}`；**自動登入不等於有權限**。主管資料為 `{role:"manager",active:true}`；員工資料與教室身分的雙向核對按 [教室日誌登入橋接](JOURNAL-SSO.md) 設定。不用姓名或員工自行輸入的值配對。離職或失去角色時由管理者撤銷或停用會員。
6. 上線前由公司確認附件的告知、最少蒐集、留存及調閱程序和負責人。此版用 Firestore 私有資料，並非端到端加密；雲端專案管理員屬受控特權。不要保存診斷內容或身分證影本，不要放入薪資備份或 Git。此版照片由管理人員依公司政策透過有權管道刪除；沒有自動清除。需定義看得見的保留期限和異常處理，再開給真實員工。

## 第一版行為

- 一張單同一天，支援整班或部分時段。從手機直接拍照或選相簿，一張照片，可提交時一起上傳或稍後補；重編碼 JPEG 去除原本中繼資料，大小最多 650 KB。檔案存於獨立權限集合，非公用 URL。員工只能查自己的假單與證明（不能看他人或薪資）；主管核對證明後核准、要求補件或不核准；兩入口不得共用來源。主管在已加密、解鎖的薪資畫面仍需另外用主管 Google 帳號登入。
- 已核准、一般出勤日且無衝突的 **月薪整班**請假，可使用既有登記途徑填入開放月份。核准是假單狀態；即使入帳失敗仍會保留「已核准，待登記」，可重試。保留假單 ID 作為不可重複登記依據，刪除舊考勤紀錄不能使假單自動再登記。
- 兼職、部分時段、已有打卡／請假、已核定月份或其他班表衝突，先比對原班表與打卡，不可讓系統覆蓋或重算。主管人工處理後才標記「已人工處理」。員工不填寫薪資、照片不上薪資帳本。
- 試行只由一位實際負責薪資的主管操作，入帳前核對原薪資雲端是否已同步，待寫入本機薪資與儲存確認後再依原流程同步。兩個不同資料服務不是一個分散式交易；跨裝置同時批次審核未開放，不應以此功能代替薪資備份或對帳。

## 驗證

- `node --test tests/*.test.cjs`
- 開發依賴：在獨立測試目錄安裝相容的 `firebase@10.12.2`、`@firebase/rules-unit-testing@3.0.3`、`firebase-tools@13.35.1`（和 Java）。由 repo 跑 `NODE_PATH=<測試目錄>/node_modules firebase emulators:exec --only firestore --project demo-bhcs-leave 'node tests/leave-backend/permissions.cjs'`。
- 上線前須要在 Android/iPhone 真機用合成證明測登入、拍照、選相簿、文字清晰、補件、撤回；用兩個員工與一個主管帳號重測互相隔離，確認鎖定後擦除畫面。兩個裝置測離職停權、重試和雲端同步衝突。先不使用真實個資。
