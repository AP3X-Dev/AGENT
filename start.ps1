# AG3NT Start Script
# Starts Gateway and Agent Worker with automatic port detection

param(
    [int]$GatewayPort = 18789,
    [int]$AgentPort = 18790,
    [switch]$NoBrowser,
    [switch]$Help
)

if ($Help) {
    Write-Host @"
AG3NT Start Script

Usage: .\start.ps1 [-GatewayPort <port>] [-AgentPort <port>] [-NoBrowser] [-Help]

Options:
  -GatewayPort  Port for Gateway (default: 18789)
  -AgentPort    Port for Agent Worker (default: 18790)
  -NoBrowser    Don't open browser automatically
  -Help         Show this help message

Examples:
  .\start.ps1                    # Start with default ports
  .\start.ps1 -GatewayPort 8080  # Use custom gateway port
  .\start.ps1 -NoBrowser         # Start without opening browser
"@
    exit 0
}

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "`n" -NoNewline
Write-Host "  =======================================  " -ForegroundColor Cyan
Write-Host "             " -NoNewline
Write-Host "AG3NT" -ForegroundColor Green -NoNewline
Write-Host " Launcher              " -ForegroundColor Cyan
Write-Host "  =======================================  " -ForegroundColor Cyan
Write-Host ""

# Function to check if port is in use (only LISTEN state means actually bound)
function Test-PortInUse {
    param([int]$Port)
    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return $null -ne $connection
}

# Function to find next available port
function Get-AvailablePort {
    param([int]$StartPort)
    $port = $StartPort
    while (Test-PortInUse -Port $port) {
        Write-Host "  [!] Port $port is in use, trying $($port + 1)..." -ForegroundColor Yellow
        $port++
        if ($port -gt $StartPort + 100) {
            throw "Could not find available port after 100 attempts"
        }
    }
    return $port
}

# Pre-flight cleanup: Kill any stale AG3NT processes on default ports
Write-Host "  [*] Checking for stale AG3NT processes..." -ForegroundColor Gray
$stalePorts = 18789..18799
$staleKilled = 0
foreach ($port in $stalePorts) {
    $connections = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    $processIds = $connections | Select-Object -ExpandProperty OwningProcess -Unique | Where-Object { $_ -ne 0 }
    foreach ($procId in $processIds) {
        try {
            $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
            if ($proc -and ($proc.ProcessName -eq "node" -or $proc.ProcessName -like "python*")) {
                Write-Host "  [*] Killing stale $($proc.ProcessName) (PID: $procId) on port $port..." -ForegroundColor Yellow
                Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
                $staleKilled++
            }
        } catch { }
    }
}
if ($staleKilled -gt 0) {
    Write-Host "  [OK] Cleaned up $staleKilled stale process(es)" -ForegroundColor Green
    Start-Sleep -Seconds 2
}

# Find available ports (ensure they don't conflict with each other)
Write-Host "  [*] Checking ports..." -ForegroundColor Gray
$GatewayPort = Get-AvailablePort -StartPort $GatewayPort
# Agent port must be different from Gateway port
if ($AgentPort -eq $GatewayPort) {
    $AgentPort = $GatewayPort + 1
}
$AgentPort = Get-AvailablePort -StartPort $AgentPort
# Double-check they're different
if ($AgentPort -eq $GatewayPort) {
    $AgentPort = $GatewayPort + 1
    $AgentPort = Get-AvailablePort -StartPort $AgentPort
}

Write-Host "  [OK] Gateway port: $GatewayPort" -ForegroundColor Green
Write-Host "  [OK] Agent port:   $AgentPort" -ForegroundColor Green
Write-Host ""

# Ensure Gateway is compiled (and recompile when src is newer than dist)
$GatewayDir = Join-Path $ScriptDir "apps\gateway"
$GatewayDist = Join-Path $GatewayDir "dist\index.js"
$GatewaySrcDir = Join-Path $GatewayDir "src"

$needsCompile = -not (Test-Path $GatewayDist)
if (-not $needsCompile -and (Test-Path $GatewaySrcDir)) {
    try {
        $distTime = (Get-Item $GatewayDist).LastWriteTimeUtc
        $srcLatest = Get-ChildItem $GatewaySrcDir -Recurse -File -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTimeUtc -Descending |
            Select-Object -First 1

        if ($srcLatest -and $srcLatest.LastWriteTimeUtc -gt $distTime) {
            $needsCompile = $true
        }
    } catch {
        # If anything goes wrong in timestamp checking, fall back to compiling.
        $needsCompile = $true
    }
}

if ($needsCompile) {
    Write-Host "  [*] Compiling Gateway..." -ForegroundColor Yellow
    Push-Location $GatewayDir
    npx tsc -p tsconfig.json
    Pop-Location
    Write-Host "  [OK] Gateway compiled" -ForegroundColor Green
}

# Load .env file if it exists
$EnvFile = Join-Path $ScriptDir ".env"
if (Test-Path $EnvFile) {
    Write-Host "  [*] Loading environment from .env..." -ForegroundColor Gray
    $envCount = 0
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        # Skip empty lines and comments
        if ($line -and -not $line.StartsWith("#")) {
            # Parse KEY=VALUE format
            $parts = $line -split "=", 2
            if ($parts.Count -eq 2) {
                $key = $parts[0].Trim()
                $value = $parts[1].Trim()
                # Remove surrounding quotes if present
                if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
                    ($value.StartsWith("'") -and $value.EndsWith("'"))) {
                    $value = $value.Substring(1, $value.Length - 2)
                }
                # Use $env: syntax for reliable child process inheritance
                Set-Item -Path "Env:$key" -Value $value
                $envCount++
            }
        }
    }
    Write-Host "  [OK] Loaded $envCount environment variables" -ForegroundColor Green
}

# Set additional environment variables
$env:PORT = $GatewayPort.ToString()
$env:AG3NT_GATEWAY_URL = "http://127.0.0.1:$GatewayPort"

# Write runtime configuration to ~/.ag3nt/runtime.json for CLI/TUI discovery
$Ag3ntDir = Join-Path $env:USERPROFILE ".ag3nt"
if (-not (Test-Path $Ag3ntDir)) {
    New-Item -ItemType Directory -Path $Ag3ntDir -Force | Out-Null
}
$RuntimeFile = Join-Path $Ag3ntDir "runtime.json"
$RuntimeConfig = @{
    gatewayPort = $GatewayPort
    agentPort = $AgentPort
    gatewayUrl = "http://127.0.0.1:$GatewayPort"
    agentUrl = "http://127.0.0.1:$AgentPort"
    startedAt = (Get-Date).ToString("o")
} | ConvertTo-Json
$RuntimeConfig | Set-Content -Path $RuntimeFile -Encoding UTF8
Write-Host "  [OK] Runtime config written to $RuntimeFile" -ForegroundColor Green

# Start Gateway as a background process
Write-Host "  [*] Starting Gateway on port $GatewayPort..." -ForegroundColor Yellow
$GatewayProcess = Start-Process -FilePath "node" -ArgumentList "dist/index.js" -WorkingDirectory $GatewayDir -PassThru -WindowStyle Hidden

Start-Sleep -Seconds 2

# Start Agent Worker as a background process
# Environment variables are inherited from current process
Write-Host "  [*] Starting Agent Worker on port $AgentPort..." -ForegroundColor Yellow
$AgentDir = Join-Path $ScriptDir "apps\agent"
$AgentProcess = Start-Process -FilePath "python" -ArgumentList "-m","uvicorn","ag3nt_agent.worker:app","--host","127.0.0.1","--port",$AgentPort.ToString() -WorkingDirectory $AgentDir -PassThru -WindowStyle Hidden

Start-Sleep -Seconds 3

Write-Host ""
Write-Host "  =======================================  " -ForegroundColor Green
Write-Host "           " -NoNewline
Write-Host "AG3NT is running!" -ForegroundColor White -NoNewline
Write-Host "              " -ForegroundColor Green
Write-Host "  =======================================  " -ForegroundColor Green
Write-Host ""
Write-Host "  Control Panel: " -NoNewline
Write-Host "http://localhost:$GatewayPort" -ForegroundColor Cyan
Write-Host "  Agent API:     " -NoNewline
Write-Host "http://localhost:$AgentPort" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Gateway PID:   $($GatewayProcess.Id)"
Write-Host "  Agent PID:     $($AgentProcess.Id)"
Write-Host ""
Write-Host "  Press " -NoNewline
Write-Host "Ctrl+C" -ForegroundColor Yellow -NoNewline
Write-Host " to stop all services"
Write-Host ""

# Open browser
if (-not $NoBrowser) {
    Start-Process "http://localhost:$GatewayPort"
}

# Function to kill process and all children
function Stop-ProcessTree {
    param([int]$ProcessId)

    # Get all child processes
    $children = Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $ProcessId }
    foreach ($child in $children) {
        Stop-ProcessTree -ProcessId $child.ProcessId
    }

    # Kill the process itself
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

# Function to cleanup all AG3NT processes
function Stop-AG3NT {
    Write-Host "`n  [*] Shutting down..." -ForegroundColor Yellow

    # Kill Gateway process tree
    if ($null -ne $GatewayProcess -and -not $GatewayProcess.HasExited) {
        Write-Host "  [*] Stopping Gateway (PID: $($GatewayProcess.Id))..." -ForegroundColor Gray
        Stop-ProcessTree -ProcessId $GatewayProcess.Id
    }

    # Kill Agent process tree
    if ($null -ne $AgentProcess -and -not $AgentProcess.HasExited) {
        Write-Host "  [*] Stopping Agent (PID: $($AgentProcess.Id))..." -ForegroundColor Gray
        Stop-ProcessTree -ProcessId $AgentProcess.Id
    }

    # Also kill any orphaned processes on our ports
    $portProcesses = Get-NetTCPConnection -LocalPort $GatewayPort,$AgentPort -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($procId in $portProcesses) {
        if ($procId -ne 0) {
            Write-Host "  [*] Cleaning up process on port (PID: $procId)..." -ForegroundColor Gray
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        }
    }

    # Wait briefly for processes to fully terminate
    Start-Sleep -Seconds 1

    # Clean up runtime.json file
    $RuntimeCleanup = Join-Path $env:USERPROFILE ".ag3nt" "runtime.json"
    if (Test-Path $RuntimeCleanup) {
        Remove-Item $RuntimeCleanup -Force -ErrorAction SilentlyContinue
        Write-Host "  [OK] Cleaned up runtime config" -ForegroundColor Green
    }

    Write-Host "  [OK] AG3NT stopped" -ForegroundColor Green
}

# Register Ctrl+C handler
$null = Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action {
    Stop-AG3NT
}

# Also use console handler for Ctrl+C
[Console]::TreatControlCAsInput = $false

# Wait and handle cleanup
try {
    while ($true) {
        # Check if processes are still running
        if ($GatewayProcess.HasExited) {
            Write-Host "  [!] Gateway exited with code $($GatewayProcess.ExitCode)" -ForegroundColor Red
            break
        }
        if ($AgentProcess.HasExited) {
            Write-Host "  [!] Agent exited with code $($AgentProcess.ExitCode)" -ForegroundColor Red
            break
        }
        Start-Sleep -Seconds 1
    }
} catch {
    # Ctrl+C throws an exception
    Write-Host ""
} finally {
    Stop-AG3NT

    # Unregister the event handler
    Unregister-Event -SourceIdentifier PowerShell.Exiting -ErrorAction SilentlyContinue
}

