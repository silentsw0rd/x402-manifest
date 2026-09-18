# Startup_gateway.ps1 - Supervisor script with background logging

$ProjectDir = (Get-Location).Path
$LogDir     = "$ProjectDir\logs"

# Ensure logs directory exists
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path$LogDir | Out-Null }

# Resolve executable paths
$Python      = (Get-Command python).Source
$Cloudflared = (Get-Command cloudflared).Source

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " Starting x402 Micropayment Gateway Stack         " -ForegroundColor Cyan
Write-Host " Logs directory: $LogDir" -ForegroundColor DarkGray
Write-Host "==================================================" -ForegroundColor Cyan

# 1. Start FastAPI Gateway Server
Write-Host "[1/3] Starting FastAPI Server (server.py)..." -ForegroundColor Yellow
$Server = Start-Process$Python `
    -ArgumentList "server.py" `
    -WorkingDirectory $ProjectDir `
    -RedirectStandardOutput "$LogDir\server_out.log" `
    -RedirectStandardError "$LogDir\server_err.log" `
    -NoNewWindow -PassThru

# 2. Start Settlement Worker
Write-Host "[2/3] Starting Settlement Worker (settlement_worker.py)..." -ForegroundColor Yellow
$Worker = Start-Process $Python `
    -ArgumentList "settlement_worker.py" `
    -WorkingDirectory $ProjectDir `
    -RedirectStandardOutput "$LogDir\worker_out.log" `
    -RedirectStandardError "$LogDir\worker_err.log" `
    -NoNewWindow -PassThru

# 3. Start Cloudflare Tunnel
Write-Host "[3/3] Starting Cloudflare Tunnel..." -ForegroundColor Yellow
$Tunnel = Start-Process$Cloudflared `
    -ArgumentList "tunnel --url http://localhost:8000" `
    -WorkingDirectory $ProjectDir `
    -RedirectStandardOutput "$LogDir\cloudflare_out.log" `
    -RedirectStandardError "$LogDir\cloudflare_err.log" `
    -NoNewWindow -PassThru

Write-Host "`nAll processes running!" -ForegroundColor Green
Write-Host "PIDs -> Server: $($Server.Id) | Worker: $($Worker.Id) | Cloudflare: $($Tunnel.Id)" -ForegroundColor DarkGray
Write-Host "Press Ctrl+C in this window to stop all processes.`n" -ForegroundColor Cyan

try {
    while ($true) {
        if ($Server.HasExited) { Write-Host "[WARNING] server.py stopped unexpectedly!" -ForegroundColor Red }
        if ($Worker.HasExited) { Write-Host "[WARNING] settlement_worker.py stopped unexpectedly!" -ForegroundColor Red }
        if ($Tunnel.HasExited) { Write-Host "[WARNING] cloudflared stopped unexpectedly!" -ForegroundColor Red }
        Start-Sleep -Seconds 3
    }
}
finally {
    Write-Host "`nTerminating all gateway processes..." -ForegroundColor Red
    Stop-Process -Id $Server.Id, $Worker.Id, $Tunnel.Id -ErrorAction SilentlyContinue
    Write-Host "Gateway stopped cleanly." -ForegroundColor Red
}