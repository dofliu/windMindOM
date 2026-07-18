# windMindOM 服務啟動與測試指南

本文件介紹如何在 Windows 環境下啟動 **windMindOM（風心智運維平台）** 的後端及前端服務以進行測試。

---

## ⚡ 一鍵啟動 (推薦)

我們提供了一個 PowerShell 腳本，會自動清理目前被佔用的埠號（預設為 `8100` 與 `3100`），並分別在獨立的新視窗中啟動後端與前端服務。

### 使用步驟：
1. 以系統管理員或一般使用者開啟 PowerShell。
2. 進入專案根目錄：
   ```powershell
   cd d:\Project_CodingSimulation\researchTopic\windMindOM
   ```
3. 執行啟動腳本：
   ```powershell
   ./start_servers.ps1
   ```
   *註：如果因 Windows 執行原則限制而無法執行，可以執行 `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` 以暫時解除限制，再執行腳本。*

---

## 🛠 手動啟動步驟

如果您偏好手動在終端機中啟動服務，請按照以下步驟操作：

### 1. 配置環境變數與環境檔
在專案根目錄下確認 `.env` 檔案存在。如果不存在，可從 `.env.example` 複製一份：
```powershell
copy .env.example .env
```
確保含有以下開發測試必備設定（預設已在 `.env` 中開啟）：
```ini
WMOM_DEV_MODE=true
WMOM_JWT_SECRET=super_secret_dev_key_for_wind_mind_om
```

### 2. 啟動後端伺服器 (Backend)
1. 開啟一個新的終端機視窗，進入專案根目錄。
2. 安裝 Python 依賴（若尚未安裝）：
   ```bash
   pip install -r requirements.txt -r requirements-dev.txt
   ```
3. 執行後端伺服器：
   ```bash
   python run.py
   ```
   * 伺服器預設會啟動在 `http://localhost:8100`。
   * Modbus TCP 模擬器會自動於 `5020` 埠啟動。
   * 若要自動尋找可用埠號，可以加上參數：`python run.py --auto-port`。

### 3. 啟動前端開發伺服器 (Frontend)
1. 開啟另一個新的終端機視窗，進入 `frontend` 資料夾。
2. 安裝 Node.js 依賴（若尚未安裝）：
   ```bash
   npm install
   ```
3. 啟動開發伺服器：
   ```bash
   npm run dev
   ```
   * 前端開發伺服器會啟動於 `http://localhost:3100`。
   * 前端會自動代理 API 請求至 `http://localhost:8100` 後端。

---

## 🔑 測試登入帳號

系統目前已強制啟用真驗證（JWT + RBAC），在開發測試模式下可直接使用以下帳密登入：

| 帳號 (Username) | 密碼 (Password) | 角色 (Role) | 用途說明 |
| :--- | :--- | :--- | :--- |
| `alice` | `alice123` | EMPLOYEE | 現場工程師 (Field Engineer) |
| `bob` | `bob123` | LEADER | 班長 (Work Order Dispatcher) |
| `carol` | `carol123` | SUPERVISOR | 運維主管 (Sign-off Manager) |
| `owner` | `owner123` | TREASURY | 業主代表 (Financial Rep) |

---

## ⚙ 疑難排解 (Troubleshooting)

### 1. 埠號衝突 (Address already in use / Port in use)
若啟動時提示埠號已佔用，可使用一鍵啟動腳本 `./start_servers.ps1` 自動清理，或者在 PowerShell 中執行以下命令手動強制關閉程序：
* **找出佔用埠號的 PID**（以 8100 為例）：
  ```powershell
  netstat -ano | findstr 8100
  ```
* **關閉該 PID**（假設 PID 為 12345）：
  ```powershell
  taskkill /F /PID 12345
  ```

### 2. UnicodeEncodeError
Windows 系統在 CMD/PowerShell 終端機預設編碼不為 UTF-8 時可能會發生編碼錯誤，專案內部之列印已全面 ASCII 化。若仍遇到編碼錯誤，請在啟動前執行：
```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
```
