# Set encoding to UTF8 to prevent any output encoding issues
$OutputEncoding = [System.Text.Encoding]::UTF8

# Get project root path
$ProjectRoot = Get-Location

Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "   windMindOM 服務一鍵啟動腳本 (Windows)" -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan

# 1. 載入 .env 埠號配置
$BackendPort = 8100
$FrontendPort = 3100
$EnvPath = Join-Path $ProjectRoot ".env"

if (Test-Path $EnvPath) {
    Write-Host "偵測到 .env 設定檔，正在載入配置..." -ForegroundColor Gray
    Get-Content $EnvPath -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $parts = $line -split "=", 2
            $key = $parts[0].Trim()
            $value = $parts[1].Trim()
            if ($key -eq "BACKEND_PORT") { $BackendPort = [int]$value }
            if ($key -eq "VITE_PORT") { $FrontendPort = [int]$value }
        }
    }
}

# 2. 自動清理佔用的埠號
function Clear-Port ($Port) {
    # 查找特定 Listening 埠號的連線資訊
    $netstatOutput = netstat -ano
    $found = $false
    foreach ($line in $netstatOutput) {
        if ($line -match "LISTENING" -and $line -match ":$Port\s+") {
            $parts = $line.Trim() -split "\s+"
            $pid = $parts[-1]
            if ($pid -and $pid -ne "0") {
                Write-Host "偵測到埠號 $Port 已被佔用 (PID: $pid)，正在強制終止該程序..." -ForegroundColor Yellow
                Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
                $found = $true
            }
        }
    }
    if ($found) {
        Start-Sleep -Seconds 1
    }
}

Write-Host "正在檢查並釋放埠號..." -ForegroundColor Gray
Clear-Port $BackendPort
Clear-Port $FrontendPort

# 3. 啟動 Backend
Write-Host "正在新視窗中啟動 Backend (Port $BackendPort)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$ProjectRoot'; python run.py" -WindowStyle Normal

# 4. 啟動 Frontend
Write-Host "正在新視窗中啟動 Frontend (Port $FrontendPort)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$ProjectRoot/frontend'; npm run dev" -WindowStyle Normal

Write-Host "`n===============================================" -ForegroundColor Cyan
Write-Host "✔ 服務啟動完成！" -ForegroundColor Green
Write-Host "Backend 網址:  http://localhost:$BackendPort" -ForegroundColor Cyan
Write-Host "Frontend 網址: http://localhost:$FrontendPort" -ForegroundColor Cyan
Write-Host "請使用新視窗觀察 Log 或進行測試。" -ForegroundColor White
Write-Host "===============================================" -ForegroundColor Cyan
