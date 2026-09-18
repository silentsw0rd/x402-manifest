# Startup_Services.ps1 - Interactive Menu for x402 Stack Management

$ProjectDir     =$PSScriptRoot
$LogDir         = "$ProjectDir\logs"
$PythonExe      = (Get-Command python).Source
$CloudflaredExe = (Get-Command cloudflared).Source

# Ensure logs directory exists
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path$LogDir | Out-Null }

function Show-Menu {
    Clear-Host
    Write-Host "==================================================" -ForegroundColor Cyan
    Write-Host "        x402 Gateway Stack Management             " -ForegroundColor Cyan
    Write-Host "==================================================" -ForegroundColor Cyan
    Write-Host " 1) Run Interactively in Console (Foreground)" -ForegroundColor Yellow
    Write-Host " 2) Install Windows Services via NSSM" -ForegroundColor Green
    Write-Host " 3) Start Windows Services" -ForegroundColor Green
    Write-Host " 4) Stop Windows Services" -ForegroundColor DarkYellow
    Write-Host " 5) Check Service Status" -ForegroundColor Gray
    Write-Host " 6) Exit" -ForegroundColor Red
    Write-Host "==================================================" -ForegroundColor Cyan
}

Show-Menu
$Choice = Read-Host "Select an option [1-6]"

switch ($Choice) {
    "1" {
        # ==========================================
        # INTERACTIVE FOREGROUND SUPERVISOR
        # ==========================================
        Write-Host "`n[+] Starting x402 Gateway Stack (Interactive Mode)..." -ForegroundColor Cyan

        Write-Host "[1/3] Starting FastAPI Server (server.py)..." -ForegroundColor Yellow
        $Server = Start-Process $PythonExe -ArgumentList "server.py" -WorkingDirectory $ProjectDir -RedirectStandardOutput "$LogDir\server_out.log" -RedirectStandardError "$LogDir\server_err.log" -NoNewWindow -PassThru

        Write-Host "[2/3] Starting Settlement Worker (settlement_worker.py)..." -ForegroundColor Yellow
        $Worker = Start-Process $PythonExe -ArgumentList "settlement_worker.py" -WorkingDirectory $ProjectDir -RedirectStandardOutput "$LogDir\worker_out.log" -RedirectStandardError "$LogDir\worker_err.log" -NoNewWindow -PassThru

        Write-Host "[3/3] Starting Cloudflare Tunnel..." -ForegroundColor Yellow
        $Tunnel = Start-Process $CloudflaredExe -ArgumentList "tunnel --url http://localhost:8000" -WorkingDirectory $ProjectDir -RedirectStandardOutput "$LogDir\cloudflare_out.log" -RedirectStandardError "$LogDir\cloudflare_err.log" -NoNewWindow -PassThru

        Write-Host "`n[✓] All processes running!" -ForegroundColor Green
        Write-Host "PIDs -> Server: $($Server.Id) | Worker: $($Worker.Id) | Cloudflare: $($Tunnel.Id)" -ForegroundColor DarkGray
        Write-Host "Press Ctrl+C to stop all processes.`n" -ForegroundColor Cyan

        try {
            while ($true) {
                if ($Server.HasExited) { Write-Host "[WARNING] server.py stopped unexpectedly!" -ForegroundColor Red }
                if ($Worker.HasExited) { Write-Host "[WARNING] settlement_worker.py stopped unexpectedly!" -ForegroundColor Red }
                if ($Tunnel.HasExited) { Write-Host "[WARNING] cloudflared stopped unexpectedly!" -ForegroundColor Red }
                Start-Sleep -Seconds 3
            }
        }
        finally {
            Write-Host "`nTerminating gateway processes..." -ForegroundColor Red
            Stop-Process -Id $Server.Id, $Worker.Id, $Tunnel.Id -ErrorAction SilentlyContinue
            Write-Host "Gateway stopped cleanly." -ForegroundColor Red
        }
    }

    "2" {
        # ==========================================
        # INSTALL NSSM SERVICES MODE
        # ==========================================
        Write-Host "`n[+] Installing x402 stack as Windows Services via NSSM..." -ForegroundColor Cyan

        nssm install x402-Server $PythonExe "$ProjectDir\server.py"
        nssm set x402-Server AppDirectory $ProjectDir
        nssm set x402-Server AppStdout "$LogDir\server_out.log"
        nssm set x402-Server AppStderr "$LogDir\server_err.log"
        nssm set x402-Server Start SERVICE_AUTO_START

        nssm install x402-Worker $PythonExe "$ProjectDir\settlement_worker.py"
        nssm set x402-Worker AppDirectory $ProjectDir
        nssm set x402-Worker AppStdout "$LogDir\worker_out.log"
        nssm set x402-Worker AppStderr "$LogDir\worker_err.log"
        nssm set x402-Worker Start SERVICE_AUTO_START

        nssm install x402-Cloudflare $CloudflaredExe "tunnel --url http://localhost:8000"
        nssm set x402-Cloudflare AppDirectory $ProjectDir
        nssm set x402-Cloudflare AppStdout "$LogDir\cloudflare_out.log"
        nssm set x402-Cloudflare AppStderr "$LogDir\cloudflare_err.log"
        nssm set x402-Cloudflare Start SERVICE_AUTO_START
        nssm set x402-Cloudflare DependOnService x402-Server

        Write-Host "[✓] Windows Services installed successfully." -ForegroundColor Green
    }

    "3" {
        Write-Host "`n[+] Starting x402 Windows Services..." -ForegroundColor Cyan
        Start-Service x402-Server, x402-Worker, x402-Cloudflare
        Write-Host "[✓] Services started." -ForegroundColor Green
    }

    "4" {
        Write-Host "`n[-] Stopping x402 Windows Services..." -ForegroundColor Yellow
        Stop-Service x402-Server, x402-Worker, x402-Cloudflare -ErrorAction SilentlyContinue
        Write-Host "[✓] Services stopped." -ForegroundColor Red
    }

    "5" {
        Write-Host "`n[?] Checking status of x402 Windows Services..." -ForegroundColor Gray
        Get-Service x402-Server, x402-Worker, x402-Cloudflare -ErrorAction SilentlyContinue
    }

    "6" {
        Write-Host "`nExiting..." -ForegroundColor DarkGray
        exit
    }

    default {
        Write-Host "`n[!] Invalid selection. Exiting." -ForegroundColor Red
    }
}