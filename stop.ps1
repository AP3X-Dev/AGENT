# AG3NT Stop Script
# Stops all AG3NT processes and frees up ports

param(
    [switch]$All,
    [switch]$Help
)

if ($Help) {
    Write-Host @"
AG3NT Stop Script

Usage: .\stop.ps1 [-All] [-Help]

Options:
  -All    Kill ALL node and python processes (use with caution)
  -Help   Show this help message

The script automatically reads ports from ~/.ag3nt/runtime.json if available,
and also scans the default port range (18789-18799) plus UI ports (3000-3010)
for any AG3NT processes.

Examples:
  .\stop.ps1       # Stop AG3NT processes on known ports
  .\stop.ps1 -All  # Stop all node/python processes (nuclear option)
"@
    exit 0
}

Write-Host ""
Write-Host "  =======================================" -ForegroundColor Cyan
Write-Host "             " -NoNewline
Write-Host "AG3NT" -ForegroundColor Red -NoNewline
Write-Host " Stopper" -ForegroundColor Cyan
Write-Host "  =======================================" -ForegroundColor Cyan
Write-Host ""

# ---------------------------------------------------------------------------
# Helper: Efficient process tree killer (single CIM query + BFS)
# ---------------------------------------------------------------------------
function Stop-ProcessTree {
    param([int]$ProcessId)

    $allProcs = Get-CimInstance Win32_Process -Property ProcessId,ParentProcessId -ErrorAction SilentlyContinue
    $childMap = @{}
    foreach ($p in $allProcs) {
        $ppid = [int]$p.ParentProcessId
        if (-not $childMap.ContainsKey($ppid)) {
            $childMap[$ppid] = [System.Collections.ArrayList]::new()
        }
        [void]$childMap[$ppid].Add([int]$p.ProcessId)
    }

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

    $toKill.Reverse()
    foreach ($pid_ in $toKill) {
        Stop-Process -Id $pid_ -Force -ErrorAction SilentlyContinue
    }
}

# ---------------------------------------------------------------------------
# Read ports from runtime.json
# ---------------------------------------------------------------------------
$RuntimeFile = Join-Path (Join-Path $env:USERPROFILE ".ag3nt") "runtime.json"
$portsFromRuntime = @()
if (Test-Path $RuntimeFile) {
    try {
        $runtime = Get-Content $RuntimeFile -Raw | ConvertFrom-Json
        if ($runtime.gatewayPort)   { $portsFromRuntime += $runtime.gatewayPort }
        if ($runtime.agentPort)     { $portsFromRuntime += $runtime.agentPort }
        if ($runtime.uiPort)        { $portsFromRuntime += $runtime.uiPort }
        if ($runtime.browserWsPort) { $portsFromRuntime += $runtime.browserWsPort }
        $parts = @()
        if ($runtime.gatewayPort)   { $parts += "Gateway=$($runtime.gatewayPort)" }
        if ($runtime.agentPort)     { $parts += "Agent=$($runtime.agentPort)" }
        if ($runtime.uiPort)        { $parts += "UI=$($runtime.uiPort)" }
        if ($runtime.browserWsPort) { $parts += "BrowserWS=$($runtime.browserWsPort)" }
        Write-Host "  [*] Found runtime config: $($parts -join ', ')" -ForegroundColor Gray
    } catch {
        Write-Host "  [!] Could not read runtime.json" -ForegroundColor Yellow
    }
}

# ---------------------------------------------------------------------------
# Scan default port ranges: gateway/agent (18789-18799) + UI (3000-3010)
# ---------------------------------------------------------------------------
$defaultPorts = 18789..18799
$uiPorts = 3000..3010
$browserWsPorts = 8765..8769
$ports = ($portsFromRuntime + $defaultPorts + $uiPorts + $browserWsPorts) | Select-Object -Unique

$killed = 0
$killedPids = @{}

Write-Host "  [*] Scanning for AG3NT processes..." -ForegroundColor Gray
foreach ($port in $ports) {
    $connections = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    $processIds = $connections | Select-Object -ExpandProperty OwningProcess -Unique | Where-Object { $_ -ne 0 }

    foreach ($procId in $processIds) {
        if ($killedPids.ContainsKey($procId)) { continue }
        try {
            $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
            if ($proc -and ($proc.ProcessName -eq "node" -or $proc.ProcessName -like "python*")) {
                Write-Host "  [*] Stopping $($proc.ProcessName) (PID: $procId) on port $port..." -ForegroundColor Yellow
                Stop-ProcessTree -ProcessId $procId
                $killedPids[$procId] = $true
                $killed++
            }
        } catch {
            # Process may have already exited
        }
    }
}

# ---------------------------------------------------------------------------
# Nuclear option: -All flag
# ---------------------------------------------------------------------------
if ($All) {
    Write-Host "  [!] -All flag: Stopping ALL node and python processes..." -ForegroundColor Red

    Get-Process -Name "node" -ErrorAction SilentlyContinue | ForEach-Object {
        if (-not $killedPids.ContainsKey($_.Id)) {
            Write-Host "  [*] Stopping node (PID: $($_.Id))..." -ForegroundColor Yellow
            Stop-ProcessTree -ProcessId $_.Id
            $killedPids[$_.Id] = $true
            $killed++
        }
    }

    Get-Process -Name "python*" -ErrorAction SilentlyContinue | ForEach-Object {
        if (-not $killedPids.ContainsKey($_.Id)) {
            Write-Host "  [*] Stopping python (PID: $($_.Id))..." -ForegroundColor Yellow
            Stop-ProcessTree -ProcessId $_.Id
            $killedPids[$_.Id] = $true
            $killed++
        }
    }
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
Write-Host ""
if ($killed -gt 0) {
    Write-Host "  [OK] Stopped $killed process(es)" -ForegroundColor Green
} else {
    Write-Host "  [OK] No AG3NT processes found running" -ForegroundColor Green
}

# Wait for processes to fully terminate
Start-Sleep -Seconds 2

# Verify key ports are free
$keyPorts = @(18789, 18790, 3000, 3001, 8765)
$stillInUse = @()
foreach ($port in $keyPorts) {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -ne 0 }
    if ($conn) {
        $stillInUse += $port
    }
}

if ($stillInUse.Count -gt 0) {
    Write-Host "  [!] Warning: Ports still in use: $($stillInUse -join ', ')" -ForegroundColor Yellow
    Write-Host "      Run '.\stop.ps1 -All' to force kill all node/python processes." -ForegroundColor Gray
} else {
    Write-Host "  [OK] AG3NT ports are now free" -ForegroundColor Green
}

# Clean up runtime.json
if (Test-Path $RuntimeFile) {
    Remove-Item $RuntimeFile -Force -ErrorAction SilentlyContinue
    Write-Host "  [OK] Cleaned up runtime config" -ForegroundColor Green
}

# Clean up stale log files (older than 7 days)
$LogDir = Join-Path (Join-Path $env:USERPROFILE ".ag3nt") "logs"
if (Test-Path $LogDir) {
    $cutoff = (Get-Date).AddDays(-7)
    Get-ChildItem $LogDir -File -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -lt $cutoff } |
        ForEach-Object {
            Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue
        }
}

Write-Host ""
