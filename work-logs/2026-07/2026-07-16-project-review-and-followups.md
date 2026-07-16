# 2026-07-16 — 專案檢視 + 後續 follow-up（M6-4 auth 基礎層）

> Session 類型：專案檢視（review）→ 逐步 follow-up
> 產出：4 PR 進 main（#105-108）+ 本 P2 收尾（#追加）
> 對應 issue：WMOM-20260716-01~06｜DEC-20260716-01/02

---

## 做了什麼

1. **全 repo 檢視**（乾淨環境實跑測試驗證健康度，非引用舊 STATUS）→ `docs/product/PROJECT_REVIEW_2026-07-16.md`，6 大發現：
   - F1 onboarding 文件全停在 M1（實際 M5 75%）｜F2 工程超前商業驗證、M6 卡在人｜F3 飛輪 2026-06-08 停擺、停前補低價值 render 測試｜F4 CI 漏 monitoring/physics（188 tests）｜F5 M6 硬前提未動（真 auth + torch footprint）｜F6 工程衛生（ISSUES.md 292KB、STATUS 巨型段落、openopc2 vendored）
2. **P0（#106）**：CLAUDE/ROADMAP/README/TODO 對齊真相（M1→M5 75%）+ CI 補 `modules/monitoring/tests/` + `tests/`（+188）。
3. **M6 決策簡報（#107）**：auth + footprint 兩決策 + `bachmann/README.md`。**新發現**：openopc2 為 **GPL-2.0-or-later**、產品 `opc_adapter.py` 有 import（僅真-PLC 路徑，Docker image 因 `.dockerignore` 排除故不涉）。
4. **M6-4 auth 基礎層（#108，DEC-20260716-01）**：新 `modules/auth/`（roles/tokens/passwords/users/dependencies/router），**HS256 JWT + PBKDF2 純 stdlib（零新依賴、無原生 build）**，RBAC 對映既有 signoff 角色，seeded store（dev 4 user / prod 空），`/api/auth/login` + `/me`，34 tests。**非破壞**：既有 router 不動、dev fallback、全 backend 899 passed / 0 failed。
5. **footprint 量測（DEC-20260716-02）**：image ~4-5GB、半數 CUDA torch → 採 deploy 專用 CPU-torch pin（Dockerfile follow-up）。
6. **P2 收尾（本檔）**：STATUS/ISSUES 對齊本 session + slim 巨型 blurb。

## 眉角 / 決策

- **auth 純 stdlib crypto**：sandbox 實測 bcrypt/cryptography 原生 build 失敗；HS256+PBKDF2 只需 stdlib，且呼應 footprint 顧慮。介面已隔離，未來要非對稱金鑰再換 PyJWT。
- **GitGuardian 誤報**：`test_passwords.py` 的假密碼被判 Generic Password → 改用 `secrets` 執行期生成 + 改寫分支歷史（held 分支、solely-mine，安全）→ 綠。
- **PR 治理**：review/decision 類 PR 加 `hold` 擋飛輪等劉老師 review；P0 類具體修正放行飛輪。劉老師本人 merge #105/#107/#108，飛輪 merge #106。
- **環境注意**：本 sandbox `run.py` 整機 boot 會因 pymodbus 版本不合在 Modbus lifespan 崩（**與 auth 無關**的既有環境問題）；auth 以 34 HTTP 層測試端到端驗證。

## 卡在哪 / 下次怎麼接手

- **auth follow-up 待續**（WMOM-20260716-04/05/06）：
  - `-04` DB-backed user store + 建帳 API（🔵 非破壞，介面已預留 `build_default_store()`）
  - `-05` router 逐支強制授權 + 前端真登入（🟡 **②③配套、會改行為**——router 開始要 token 但前端還送 body actor_id，兩者必須一起否則登不進，需劉老師在場排）
  - `-06` footprint CPU-torch pin Dockerfile（🔵 本地無 docker，待部署環境驗）
- **M6 商業前提**（非程式）：客戶接觸 WMOM-20260503-05（素材齊、待劉老師執行）。
- **接手指引**：先讀 `PROJECT_REVIEW_2026-07-16.md` 全貌 + `decision_log` DEC-20260716-01/02。
