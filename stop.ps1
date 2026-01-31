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
and also scans the default port range (18789-18799) for any AG3NT processes.

Examples:
  .\stop.ps1       # Stop AG3NT processes on known ports
  .\stop.ps1 -All  # Stop all node/python processes (nuclear option)
"@
    exit 0
}

Write-Host "`n" -NoNewline
Write-Host "  =======================================  " -ForegroundColor Cyan
Write-Host "             " -NoNewline
Write-Host "AG3NT" -ForegroundColor Red -NoNewline
Write-Host " Stopper               " -ForegroundColor Cyan
Write-Host "  =======================================  " -ForegroundColor Cyan
Write-Host ""

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

# Read ports from runtime.json if available
$RuntimeFile = Join-Path $env:USERPROFILE ".ag3nt" "runtime.json"
$portsFromRuntime = @()
if (Test-Path $RuntimeFile) {
    try {
        $runtime = Get-Content $RuntimeFile -Raw | ConvertFrom-Json
        if ($runtime.gatewayPort) { $portsFromRuntime += $runtime.gatewayPort }
        if ($runtime.agentPort) { $portsFromRuntime += $runtime.agentPort }
        Write-Host "  [*] Found runtime config: Gateway=$($runtime.gatewayPort), Agent=$($runtime.agentPort)" -ForegroundColor Gray
    } catch {
        Write-Host "  [!] Could not read runtime.json" -ForegroundColor Yellow
    }
}

# Scan the default port range (18789-18799) plus any from runtime
$defaultPorts = 18789..18799
$ports = ($portsFromRuntime + $defaultPorts) | Select-Object -Unique

# Find and kill processes on AG3NT ports
$killed = 0

# Track killed PIDs to avoid duplicates
$killedPids = @{}

Write-Host "  [*] Scanning ports 18789-18799 for AG3NT processes..." -ForegroundColor Gray
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

# If -All flag, kill ALL node and python processes
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

Write-Host ""
if ($killed -gt 0) {
    Write-Host "  [OK] Stopped $killed process(es)" -ForegroundColor Green
} else {
    Write-Host "  [OK] No AG3NT processes found running" -ForegroundColor Green
}

# Wait for processes to fully terminate
Start-Sleep -Seconds 2

# Verify key ports are free (just check the main ones)
$keyPorts = @(18789, 18790, 18791, 18792)
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

# Clean up runtime.json file
if (Test-Path $RuntimeFile) {
    Remove-Item $RuntimeFile -Force -ErrorAction SilentlyContinue
    Write-Host "  [OK] Cleaned up runtime config" -ForegroundColor Green
}

Write-Host ""

