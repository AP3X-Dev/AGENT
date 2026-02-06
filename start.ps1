# AG3NT Start Script
# Starts Gateway, Agent Worker, and Web UI with robust process management

param(
    [int]$GatewayPort = 18789,
    [int]$AgentPort = 18790,
    [int]$UIPort = 3000,
    [int]$BrowserWSPort = 8765,
    [switch]$NoUI,
    [switch]$NoBrowser,
    [switch]$NoBrowserServer,
    [switch]$Help
)

if ($Help) {
    Write-Host @"
AG3NT Start Script

Usage: .\start.ps1 [-GatewayPort <port>] [-AgentPort <port>] [-UIPort <port>] [-BrowserWSPort <port>] [-NoUI] [-NoBrowser] [-NoBrowserServer] [-Help]

Options:
  -GatewayPort     Port for Gateway (default: 18789)
  -AgentPort       Port for Agent Worker (default: 18790)
  -UIPort          Port for Web UI (default: 3000)
  -BrowserWSPort   Port for Browser WS server (default: 8765)
  -NoUI            Don't start the Web UI
  -NoBrowser       Don't open browser automatically
  -NoBrowserServer Don't start the Playwright browser server
  -Help            Show this help message

Examples:
  .\start.ps1                    # Start with default ports
  .\start.ps1 -GatewayPort 8080  # Use custom gateway port
  .\start.ps1 -NoBrowser         # Start without opening browser
  .\start.ps1 -NoUI              # Start without Web UI
"@
    exit 0
}

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "  =======================================" -ForegroundColor Cyan
Write-Host "             " -NoNewline
Write-Host "AG3NT" -ForegroundColor Green -NoNewline
Write-Host " Launcher" -ForegroundColor Cyan
Write-Host "  =======================================" -ForegroundColor Cyan
Write-Host ""

# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

function Test-PortInUse {
    param([int]$Port)
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return $null -ne $conn
}

function Get-AvailablePort {
    param([int]$StartPort)
    $port = $StartPort
    while (Test-PortInUse -Port $port) {
        Write-Host "  [!] Port $port is in use, trying $($port + 1)..." -ForegroundColor Yellow
        $port++
        if ($port -gt $StartPort + 100) {
            throw "Could not find available port after 100 attempts starting from $StartPort"
        }
    }
    return $port
}

function Wait-ForPort {
    <#
    .SYNOPSIS
        Poll a TCP port until something is listening or timeout.
        Returns $true if port became active, $false on timeout.
    #>
    param(
        [int]$Port,
        [int]$TimeoutSeconds = 30,
        [string]$Label = "Service"
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $spinner = @('|','/','-','\')
    $i = 0
    while ((Get-Date) -lt $deadline) {
        if (Test-PortInUse -Port $Port) {
            return $true
        }
        $ch = $spinner[$i % $spinner.Count]
        Write-Host "`r  [$ch] Waiting for $Label on port $Port... " -NoNewline -ForegroundColor Gray
        Start-Sleep -Milliseconds 500
        $i++
    }
    Write-Host ""
    return $false
}

function Wait-ForHttp {
    <#
    .SYNOPSIS
        Poll an HTTP endpoint until it responds (any 2xx/3xx) or timeout.
        Returns $true on success, $false on timeout.
    #>
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 30,
        [string]$Label = "Service"
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $spinner = @('|','/','-','\')
    $i = 0
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-WebRequest -Uri $Url -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
            if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 400) {
                Write-Host "`r  [OK] $Label is responding                  " -ForegroundColor Green
                return $true
            }
        } catch {
            # Not ready yet
        }
        $ch = $spinner[$i % $spinner.Count]
        Write-Host "`r  [$ch] Waiting for $Label at $Url... " -NoNewline -ForegroundColor Gray
        Start-Sleep -Milliseconds 800
        $i++
    }
    Write-Host ""
    return $false
}

function Start-BackgroundProcess {
    <#
    .SYNOPSIS
        Starts a process reliably on Windows, returning the actual process object.
        Works around the npm.cmd wrapper issue by launching via cmd /c and tracking
        the real child process by port binding.
    #>
    param(
        [string]$Command,
        [string[]]$Arguments,
        [string]$WorkingDirectory,
        [string]$LogFile,
        [hashtable]$Environment = @{}
    )

    # Build environment block: inherit current env + overrides
    $envBlock = @{}
    Get-ChildItem Env: | ForEach-Object { $envBlock[$_.Name] = $_.Value }
    foreach ($k in $Environment.Keys) {
        $envBlock[$k] = $Environment[$k]
    }

    # Create ProcessStartInfo for full control
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "cmd.exe"
    $psi.Arguments = "/c $Command $($Arguments -join ' ') > `"$LogFile`" 2>&1"
    $psi.WorkingDirectory = $WorkingDirectory
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $false
    $psi.RedirectStandardError = $false

    # Set environment on the process
    $psi.EnvironmentVariables.Clear()
    foreach ($k in $envBlock.Keys) {
        try { $psi.EnvironmentVariables[$k] = $envBlock[$k] } catch {}
    }

    $proc = [System.Diagnostics.Process]::Start($psi)
    return $proc
}

function Stop-ProcessTree {
    <#
    .SYNOPSIS
        Kill a process and all its descendants efficiently.
        Uses a single CIM query and builds a lookup table.
    #>
    param([int]$ProcessId)

    # Build parent->children map with ONE query
    $allProcs = Get-CimInstance Win32_Process -Property ProcessId,ParentProcessId -ErrorAction SilentlyContinue
    $childMap = @{}
    foreach ($p in $allProcs) {
        $ppid = [int]$p.ParentProcessId
        if (-not $childMap.ContainsKey($ppid)) {
            $childMap[$ppid] = [System.Collections.ArrayList]::new()
        }
        [void]$childMap[$ppid].Add([int]$p.ProcessId)
    }

    # BFS to collect all descendants
    $toKill = [System.Collections.ArrayList]::new()
    $queue = [System.Collections.Queue]::new()
    $queue.Enqueue($ProcessId)
    while ($queue.Count -gt 0) {
        $pid_ = $queue.Dequeue()
        [void]$toKill.Add($pid_)
        if ($childMap.ContainsKey($pid_)) {
            foreach ($child in $childMap[$pid_]) {
                $queue.Enqueue($child)
            }
        }
    }

    # Kill bottom-up (children first)
    $toKill.Reverse()
    foreach ($pid_ in $toKill) {
        Stop-Process -Id $pid_ -Force -ErrorAction SilentlyContinue
    }
}

function Get-ProcessOnPort {
    <#
    .SYNOPSIS
        Get the PID listening on a given port.
    #>
    param([int]$Port)
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($conn) { return $conn.OwningProcess }
    return $null
}

# ---------------------------------------------------------------------------
# Pre-flight: Kill stale AG3NT processes
# ---------------------------------------------------------------------------
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
                Stop-ProcessTree -ProcessId $procId
                $staleKilled++
            }
        } catch { }
    }
}
if ($staleKilled -gt 0) {
    Write-Host "  [OK] Cleaned up $staleKilled stale process(es)" -ForegroundColor Green
    Start-Sleep -Seconds 2
}

# ---------------------------------------------------------------------------
# Port allocation
# ---------------------------------------------------------------------------
Write-Host "  [*] Checking ports..." -ForegroundColor Gray
$GatewayPort = Get-AvailablePort -StartPort $GatewayPort

if ($AgentPort -eq $GatewayPort) { $AgentPort = $GatewayPort + 1 }
$AgentPort = Get-AvailablePort -StartPort $AgentPort
if ($AgentPort -eq $GatewayPort) {
    $AgentPort = $GatewayPort + 1
    $AgentPort = Get-AvailablePort -StartPort $AgentPort
}

Write-Host "  [OK] Gateway port: $GatewayPort" -ForegroundColor Green
Write-Host "  [OK] Agent port:   $AgentPort" -ForegroundColor Green

if (-not $NoUI) {
    $UIPort = Get-AvailablePort -StartPort $UIPort
    while ($UIPort -eq $GatewayPort -or $UIPort -eq $AgentPort) {
        $UIPort++
        $UIPort = Get-AvailablePort -StartPort $UIPort
    }
    Write-Host "  [OK] UI port:      $UIPort" -ForegroundColor Green
}
Write-Host ""

# ---------------------------------------------------------------------------
# Compile Gateway if needed
# ---------------------------------------------------------------------------
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
    } catch { $needsCompile = $true }
}

if ($needsCompile) {
    Write-Host "  [*] Compiling Gateway..." -ForegroundColor Yellow
    Push-Location $GatewayDir
    npx tsc -p tsconfig.json
    Pop-Location
    Write-Host "  [OK] Gateway compiled" -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# Load .env
# ---------------------------------------------------------------------------
$EnvFile = Join-Path $ScriptDir ".env"
if (Test-Path $EnvFile) {
    Write-Host "  [*] Loading environment from .env..." -ForegroundColor Gray
    $envCount = 0
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#")) {
            $parts = $line -split "=", 2
            if ($parts.Count -eq 2) {
                $key = $parts[0].Trim()
                $value = $parts[1].Trim()
                if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
                    ($value.StartsWith("'") -and $value.EndsWith("'"))) {
                    $value = $value.Substring(1, $value.Length - 2)
                }
                Set-Item -Path "Env:$key" -Value $value
                $envCount++
            }
        }
    }
    Write-Host "  [OK] Loaded $envCount environment variables" -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# Set environment variables shared by all services
# ---------------------------------------------------------------------------
$env:AG3NT_GATEWAY_URL = "http://127.0.0.1:$GatewayPort"

# ---------------------------------------------------------------------------
# Write runtime config
# ---------------------------------------------------------------------------
$Ag3ntDir = Join-Path $env:USERPROFILE ".ag3nt"
if (-not (Test-Path $Ag3ntDir)) {
    New-Item -ItemType Directory -Path $Ag3ntDir -Force | Out-Null
}
$RuntimeFile = Join-Path $Ag3ntDir "runtime.json"
$RuntimeConfigObj = @{
    gatewayPort = $GatewayPort
    agentPort   = $AgentPort
    gatewayUrl  = "http://127.0.0.1:$GatewayPort"
    agentUrl    = "http://127.0.0.1:$AgentPort"
    startedAt   = (Get-Date).ToString("o")
}
if (-not $NoUI) {
    $RuntimeConfigObj.uiPort = $UIPort
    $RuntimeConfigObj.uiUrl  = "http://127.0.0.1:$UIPort"
}
if (-not $NoBrowserServer) {
    $RuntimeConfigObj.browserWsPort = $BrowserWSPort
    $RuntimeConfigObj.browserWsUrl  = "ws://127.0.0.1:$BrowserWSPort"
}
$RuntimeConfig = $RuntimeConfigObj | ConvertTo-Json
$RuntimeConfig | Set-Content -Path $RuntimeFile -Encoding UTF8
Write-Host "  [OK] Runtime config written to $RuntimeFile" -ForegroundColor Green

# ---------------------------------------------------------------------------
# Create log directory
# ---------------------------------------------------------------------------
$LogDir = Join-Path $Ag3ntDir "logs"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}
$GatewayLog   = Join-Path $LogDir "gateway.log"
$AgentLog     = Join-Path $LogDir "agent.log"
$UILog        = Join-Path $LogDir "ui.log"
$BrowserWSLog = Join-Path $LogDir "browser-ws.log"

# ---------------------------------------------------------------------------
# Start Gateway
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "  [*] Starting Gateway on port $GatewayPort..." -ForegroundColor Yellow

$env:PORT = $GatewayPort.ToString()
$GatewayProcess = Start-BackgroundProcess `
    -Command "node" `
    -Arguments @("dist/index.js") `
    -WorkingDirectory $GatewayDir `
    -LogFile $GatewayLog `
    -Environment @{ PORT = $GatewayPort.ToString(); AG3NT_GATEWAY_URL = "http://127.0.0.1:$GatewayPort" }

$gwReady = Wait-ForPort -Port $GatewayPort -TimeoutSeconds 15 -Label "Gateway"
if (-not $gwReady) {
    Write-Host "  [!] Gateway failed to start. Check log: $GatewayLog" -ForegroundColor Red
    # Show last few lines of log
    if (Test-Path $GatewayLog) {
        Write-Host "  --- Last 5 lines of gateway.log ---" -ForegroundColor Gray
        Get-Content $GatewayLog -Tail 5 | ForEach-Object { Write-Host "      $_" -ForegroundColor Gray }
    }
    # Try to get the real process on the port (in case cmd.exe wrapper exited)
} else {
    Write-Host "  [OK] Gateway is ready" -ForegroundColor Green
}

# Track the real PID (the node process on the port, not the cmd wrapper)
$GatewayRealPid = Get-ProcessOnPort -Port $GatewayPort
if (-not $GatewayRealPid) { $GatewayRealPid = $GatewayProcess.Id }

# ---------------------------------------------------------------------------
# Start Agent Worker
# ---------------------------------------------------------------------------
Write-Host "  [*] Starting Agent Worker on port $AgentPort..." -ForegroundColor Yellow

$AgentDir = Join-Path $ScriptDir "apps\agent"
$AgentProcess = Start-BackgroundProcess `
    -Command "python" `
    -Arguments @("-m", "uvicorn", "ag3nt_agent.worker:app", "--host", "127.0.0.1", "--port", $AgentPort.ToString()) `
    -WorkingDirectory $AgentDir `
    -LogFile $AgentLog `
    -Environment @{ AG3NT_GATEWAY_URL = "http://127.0.0.1:$GatewayPort" }

$agentReady = Wait-ForPort -Port $AgentPort -TimeoutSeconds 30 -Label "Agent Worker"
if (-not $agentReady) {
    Write-Host "  [!] Agent Worker failed to start. Check log: $AgentLog" -ForegroundColor Red
    if (Test-Path $AgentLog) {
        Write-Host "  --- Last 5 lines of agent.log ---" -ForegroundColor Gray
        Get-Content $AgentLog -Tail 5 | ForEach-Object { Write-Host "      $_" -ForegroundColor Gray }
    }
} else {
    Write-Host "  [OK] Agent Worker is ready" -ForegroundColor Green
}

$AgentRealPid = Get-ProcessOnPort -Port $AgentPort
if (-not $AgentRealPid) { $AgentRealPid = $AgentProcess.Id }

# ---------------------------------------------------------------------------
# Start Browser WebSocket Server (Playwright live browser streaming)
# ---------------------------------------------------------------------------
$BrowserWSProcess = $null
$BrowserWSRealPid = $null
if (-not $NoBrowserServer) {
    # Check if port is available
    $BrowserWSPort = Get-AvailablePort -StartPort $BrowserWSPort
    Write-Host "  [*] Starting Browser Server on port $BrowserWSPort..." -ForegroundColor Yellow

    $BrowserWSDir = Join-Path $ScriptDir "apps\ui"
    $BrowserWSScript = Join-Path $BrowserWSDir "python\browser_ws_server.py"

    if (Test-Path $BrowserWSScript) {
        $BrowserWSProcess = Start-BackgroundProcess `
            -Command "python" `
            -Arguments @("`"$BrowserWSScript`"") `
            -WorkingDirectory $BrowserWSDir `
            -LogFile $BrowserWSLog `
            -Environment @{
                BROWSER_WS_PORT = $BrowserWSPort.ToString()
                BROWSER_WS_HOST = "127.0.0.1"
            }

        $bwsReady = Wait-ForPort -Port $BrowserWSPort -TimeoutSeconds 20 -Label "Browser Server"
        if (-not $bwsReady) {
            Write-Host "  [!] Browser Server failed to start. Check log: $BrowserWSLog" -ForegroundColor Red
            if (Test-Path $BrowserWSLog) {
                Write-Host "  --- Last 5 lines of browser-ws.log ---" -ForegroundColor Gray
                Get-Content $BrowserWSLog -Tail 5 | ForEach-Object { Write-Host "      $_" -ForegroundColor Gray }
            }
            Write-Host "  [!] Continuing without Browser Server. Agent Browser will use mock mode." -ForegroundColor Yellow
        } else {
            Write-Host "  [OK] Browser Server is ready (ws://localhost:$BrowserWSPort)" -ForegroundColor Green
        }

        $BrowserWSRealPid = Get-ProcessOnPort -Port $BrowserWSPort
        if (-not $BrowserWSRealPid -and $BrowserWSProcess) { $BrowserWSRealPid = $BrowserWSProcess.Id }
    } else {
        Write-Host "  [!] Browser server script not found: $BrowserWSScript" -ForegroundColor Yellow
        Write-Host "  [!] Continuing without Browser Server." -ForegroundColor Yellow
    }
}

# ---------------------------------------------------------------------------
# Start Web UI
# ---------------------------------------------------------------------------
$UIProcess = $null
$UIRealPid = $null
if (-not $NoUI) {
    Write-Host "  [*] Starting Web UI on port $UIPort..." -ForegroundColor Yellow

    $UIDir = Join-Path $ScriptDir "apps\ui"

    # Resolve the actual next binary to avoid npm.cmd wrapper issues
    $NextBin = Join-Path $UIDir "node_modules\.bin\next.cmd"
    if (-not (Test-Path $NextBin)) {
        $NextBin = Join-Path $UIDir "node_modules\next\dist\bin\next"
    }

    # Build UI environment - pass browser WS URL if server is running
    $UIEnv = @{
        PORT = $UIPort.ToString()
        AG3NT_GATEWAY_URL = "http://127.0.0.1:$GatewayPort"
        NEXT_PUBLIC_AG3NT_GATEWAY_URL = "http://127.0.0.1:$GatewayPort"
    }
    if ($BrowserWSRealPid) {
        $UIEnv["NEXT_PUBLIC_BROWSER_WS_URL"] = "ws://localhost:$BrowserWSPort"
        $UIEnv["NEXT_PUBLIC_USE_LOCAL_BROWSER"] = "true"
    }

    # Use npx next dev with proper port - this is more reliable than npm run dev
    $UIProcess = Start-BackgroundProcess `
        -Command "npx" `
        -Arguments @("next", "dev", "--port", $UIPort.ToString()) `
        -WorkingDirectory $UIDir `
        -LogFile $UILog `
        -Environment $UIEnv

    $uiReady = Wait-ForPort -Port $UIPort -TimeoutSeconds 45 -Label "Web UI"
    if (-not $uiReady) {
        Write-Host "  [!] Web UI failed to start on port $UIPort. Check log: $UILog" -ForegroundColor Red
        if (Test-Path $UILog) {
            Write-Host "  --- Last 10 lines of ui.log ---" -ForegroundColor Gray
            Get-Content $UILog -Tail 10 | ForEach-Object { Write-Host "      $_" -ForegroundColor Gray }
        }
        # UI failure is non-fatal - keep Gateway and Agent running
        Write-Host "  [!] Continuing without Web UI. Gateway and Agent are still running." -ForegroundColor Yellow
    } else {
        Write-Host "  [OK] Web UI is ready" -ForegroundColor Green
    }

    $UIRealPid = Get-ProcessOnPort -Port $UIPort
    if (-not $UIRealPid -and $UIProcess) { $UIRealPid = $UIProcess.Id }
}

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "  =======================================" -ForegroundColor Green
Write-Host "           " -NoNewline
Write-Host "AG3NT is running!" -ForegroundColor White
Write-Host "  =======================================" -ForegroundColor Green
Write-Host ""

if (-not $NoUI -and $UIRealPid) {
    Write-Host "  Web UI:        " -NoNewline
    Write-Host "http://localhost:$UIPort" -ForegroundColor Cyan
}
Write-Host "  Control Panel: " -NoNewline
Write-Host "http://localhost:$GatewayPort" -ForegroundColor Cyan
Write-Host "  Agent API:     " -NoNewline
Write-Host "http://localhost:$AgentPort" -ForegroundColor Cyan
if ($BrowserWSRealPid) {
    Write-Host "  Browser WS:    " -NoNewline
    Write-Host "ws://localhost:$BrowserWSPort" -ForegroundColor Cyan
}
Write-Host ""
Write-Host "  Gateway PID:   $GatewayRealPid"
Write-Host "  Agent PID:     $AgentRealPid"
if ($UIRealPid) {
    Write-Host "  UI PID:        $UIRealPid"
}
if ($BrowserWSRealPid) {
    Write-Host "  Browser PID:   $BrowserWSRealPid"
}
Write-Host ""
Write-Host "  Logs:          $LogDir" -ForegroundColor Gray
Write-Host ""
Write-Host "  Press " -NoNewline
Write-Host "Ctrl+C" -ForegroundColor Yellow -NoNewline
Write-Host " to stop all services"
Write-Host ""

# Open browser
if (-not $NoBrowser) {
    if (-not $NoUI -and $UIRealPid) {
        Start-Process "http://localhost:$UIPort"
    } else {
        Start-Process "http://localhost:$GatewayPort"
    }
}

# ---------------------------------------------------------------------------
# Cleanup function
# ---------------------------------------------------------------------------
function Stop-AG3NT {
    Write-Host "`n  [*] Shutting down..." -ForegroundColor Yellow

    # Kill UI
    if ($UIRealPid) {
        Write-Host "  [*] Stopping UI (PID: $UIRealPid)..." -ForegroundColor Gray
        Stop-ProcessTree -ProcessId $UIRealPid
    }
    if ($UIProcess -and -not $UIProcess.HasExited) {
        Stop-ProcessTree -ProcessId $UIProcess.Id
    }

    # Kill Browser WS Server
    if ($BrowserWSRealPid) {
        Write-Host "  [*] Stopping Browser Server (PID: $BrowserWSRealPid)..." -ForegroundColor Gray
        Stop-ProcessTree -ProcessId $BrowserWSRealPid
    }
    if ($BrowserWSProcess -and -not $BrowserWSProcess.HasExited) {
        Stop-ProcessTree -ProcessId $BrowserWSProcess.Id
    }

    # Kill Gateway
    if ($GatewayRealPid) {
        Write-Host "  [*] Stopping Gateway (PID: $GatewayRealPid)..." -ForegroundColor Gray
        Stop-ProcessTree -ProcessId $GatewayRealPid
    }
    if ($GatewayProcess -and -not $GatewayProcess.HasExited) {
        Stop-ProcessTree -ProcessId $GatewayProcess.Id
    }

    # Kill Agent
    if ($AgentRealPid) {
        Write-Host "  [*] Stopping Agent (PID: $AgentRealPid)..." -ForegroundColor Gray
        Stop-ProcessTree -ProcessId $AgentRealPid
    }
    if ($AgentProcess -and -not $AgentProcess.HasExited) {
        Stop-ProcessTree -ProcessId $AgentProcess.Id
    }

    # Sweep: kill anything left on our ports
    $portsToClean = @($GatewayPort, $AgentPort)
    if (-not $NoUI) { $portsToClean += $UIPort }
    if (-not $NoBrowserServer) { $portsToClean += $BrowserWSPort }
    foreach ($port in $portsToClean) {
        $pid_ = Get-ProcessOnPort -Port $port
        if ($pid_ -and $pid_ -ne 0) {
            Write-Host "  [*] Cleaning up orphan on port $port (PID: $pid_)..." -ForegroundColor Gray
            Stop-Process -Id $pid_ -Force -ErrorAction SilentlyContinue
        }
    }

    Start-Sleep -Seconds 1

    # Clean up runtime.json
    $rtFile = Join-Path (Join-Path $env:USERPROFILE ".ag3nt") "runtime.json"
    if (Test-Path $rtFile) {
        Remove-Item $rtFile -Force -ErrorAction SilentlyContinue
        Write-Host "  [OK] Cleaned up runtime config" -ForegroundColor Green
    }

    Write-Host "  [OK] AG3NT stopped" -ForegroundColor Green
}

# Register exit handler
$null = Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action { Stop-AG3NT }
[Console]::TreatControlCAsInput = $false

# ---------------------------------------------------------------------------
# Main loop: monitor processes, restart UI on failure
# ---------------------------------------------------------------------------
$uiRestarts = 0
$maxUIRestarts = 3

try {
    while ($true) {
        # Check Gateway health (critical - exit if dead)
        $gwPid = Get-ProcessOnPort -Port $GatewayPort
        if (-not $gwPid) {
            # Gateway might have died - check if it's truly gone
            $gwProc = Get-Process -Id $GatewayRealPid -ErrorAction SilentlyContinue
            if (-not $gwProc) {
                Write-Host "  [!] Gateway has stopped. Shutting down." -ForegroundColor Red
                if (Test-Path $GatewayLog) {
                    Write-Host "  --- Last 5 lines of gateway.log ---" -ForegroundColor Gray
                    Get-Content $GatewayLog -Tail 5 | ForEach-Object { Write-Host "      $_" -ForegroundColor Gray }
                }
                break
            }
        }

        # Check Agent health (critical - exit if dead)
        $agPid = Get-ProcessOnPort -Port $AgentPort
        if (-not $agPid) {
            $agProc = Get-Process -Id $AgentRealPid -ErrorAction SilentlyContinue
            if (-not $agProc) {
                Write-Host "  [!] Agent Worker has stopped. Shutting down." -ForegroundColor Red
                if (Test-Path $AgentLog) {
                    Write-Host "  --- Last 5 lines of agent.log ---" -ForegroundColor Gray
                    Get-Content $AgentLog -Tail 5 | ForEach-Object { Write-Host "      $_" -ForegroundColor Gray }
                }
                break
            }
        }

        # Check UI health (non-critical - auto-restart if possible)
        if (-not $NoUI -and $UIRealPid) {
            $uiPid = Get-ProcessOnPort -Port $UIPort
            if (-not $uiPid) {
                $uiProc = Get-Process -Id $UIRealPid -ErrorAction SilentlyContinue
                if (-not $uiProc) {
                    if ($uiRestarts -lt $maxUIRestarts) {
                        $uiRestarts++
                        Write-Host "  [!] Web UI stopped. Restarting ($uiRestarts/$maxUIRestarts)..." -ForegroundColor Yellow

                        $UIDir = Join-Path $ScriptDir "apps\ui"
                        # Build restart env - same as initial launch
                        $restartEnv = @{
                            PORT = $UIPort.ToString()
                            AG3NT_GATEWAY_URL = "http://127.0.0.1:$GatewayPort"
                            NEXT_PUBLIC_AG3NT_GATEWAY_URL = "http://127.0.0.1:$GatewayPort"
                        }
                        if ($BrowserWSRealPid) {
                            $restartEnv["NEXT_PUBLIC_BROWSER_WS_URL"] = "ws://localhost:$BrowserWSPort"
                            $restartEnv["NEXT_PUBLIC_USE_LOCAL_BROWSER"] = "true"
                        }

                        $UIProcess = Start-BackgroundProcess `
                            -Command "npx" `
                            -Arguments @("next", "dev", "--port", $UIPort.ToString()) `
                            -WorkingDirectory $UIDir `
                            -LogFile $UILog `
                            -Environment $restartEnv

                        $uiReady = Wait-ForPort -Port $UIPort -TimeoutSeconds 45 -Label "Web UI"
                        if ($uiReady) {
                            $UIRealPid = Get-ProcessOnPort -Port $UIPort
                            if (-not $UIRealPid) { $UIRealPid = $UIProcess.Id }
                            Write-Host "  [OK] Web UI restarted (PID: $UIRealPid)" -ForegroundColor Green
                        } else {
                            Write-Host "  [!] Web UI restart failed. Check log: $UILog" -ForegroundColor Red
                            if (Test-Path $UILog) {
                                Get-Content $UILog -Tail 5 | ForEach-Object { Write-Host "      $_" -ForegroundColor Gray }
                            }
                        }
                    } else {
                        Write-Host "  [!] Web UI exceeded max restarts ($maxUIRestarts). Running without UI." -ForegroundColor Yellow
                        $UIRealPid = $null
                    }
                }
            }
        }

        Start-Sleep -Seconds 3
    }
} catch {
    # Ctrl+C throws an exception
    Write-Host ""
} finally {
    Stop-AG3NT
    Unregister-Event -SourceIdentifier PowerShell.Exiting -ErrorAction SilentlyContinue
}
