# Ensure paths match your local setup
$ProjectDir = "C:\Users\matt\Documents\Agents\Pydantic Scraping Ollama\"
$LogDir     = "$ProjectDir\logs"
$PythonExe  = "C:\Windows\py.exe"  # or your virtual environment python.exe path
$NgrokExe   = (Get-Command ngrok).Source

# Create logs folder if missing
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir }

# 1. FastAPI Gateway Server
nssm install x402-Server $PythonExe "$ProjectDir\server.py"
nssm set x402-Server AppDirectory $ProjectDir
nssm set x402-Server AppStdout "$LogDir\server_out.log"
nssm set x402-Server AppStderr "$LogDir\server_err.log"
nssm set x402-Server Start SERVICE_AUTO_START

# 2. On-Chain Settlement Worker
nssm install x402-Worker $PythonExe "$ProjectDir\settlement_worker.py"
nssm set x402-Worker AppDirectory $ProjectDir
nssm set x402-Worker AppStdout "$LogDir\worker_out.log"
nssm set x402-Worker AppStderr "$LogDir\worker_err.log"
nssm set x402-Worker Start SERVICE_AUTO_START

# 3. Ngrok Public Ingress Tunnel
nssm install x402-Ngrok $NgrokExe "http 8000 --url=flight-dill-hangout.ngrok-free.dev"
nssm set x402-Ngrok AppDirectory $ProjectDir
nssm set x402-Ngrok AppStdout "$LogDir\ngrok_out.log"
nssm set x402-Ngrok AppStderr "$LogDir\ngrok_err.log"
nssm set x402-Ngrok Start SERVICE_AUTO_START
nssm set x402-Ngrok DependOnService x402-Server

Write-Host "Services configured successfully!" -ForegroundColor Green