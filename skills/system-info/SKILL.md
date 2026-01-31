---
name: system-info
description: Get system information including CPU usage, memory, disk space, battery status, and network info. Read-only and safe to use.
version: "1.0.0"
tags:
  - system
  - monitoring
  - device
  - desktop
triggers:
  - "system status"
  - "how much disk space"
  - "battery level"
  - "cpu usage"
  - "memory usage"
  - "system info"
  - "computer status"
entrypoints:
  status:
    script: scripts/system_info.py
    description: Get a comprehensive system status report
  cpu:
    script: scripts/system_info.py --cpu
    description: Get CPU usage information
  memory:
    script: scripts/system_info.py --memory
    description: Get memory/RAM usage information
  disk:
    script: scripts/system_info.py --disk
    description: Get disk space information
  battery:
    script: scripts/system_info.py --battery
    description: Get battery status (if available)
  network:
    script: scripts/system_info.py --network
    description: Get network interface information
required_permissions: []
license: MIT
compatibility: AG3NT 1.x
metadata:
  author: ag3nt-team
  category: device-integration
  node_capability: system_info
---

# System Info Skill

This skill provides read-only access to system information. It's safe to use and doesn't require any special permissions.

## When to Use

- User asks about system status, CPU, memory, disk, or battery
- User wants to know how much storage is available
- User asks about network connectivity
- User wants a health check of their computer

## Available Commands

### Full Status Report
Run `scripts/system_info.py` to get a comprehensive report including:
- Operating system and version
- CPU usage and core count
- Memory usage (used/total)
- Disk space (used/total per drive)
- Battery status (if laptop)
- Network interfaces

### Individual Reports
- `--cpu` - CPU information only
- `--memory` - Memory/RAM information only
- `--disk` - Disk space information only
- `--battery` - Battery status only
- `--network` - Network interfaces only

## Example Output

```
🖥️ System Status Report
========================

📊 Operating System
  OS: Windows 11
  Version: 10.0.22631
  Architecture: AMD64
  Hostname: DESKTOP-ABC123

💻 CPU
  Usage: 15.2%
  Cores: 8 (16 logical)
  Frequency: 3.60 GHz

🧠 Memory
  Used: 12.4 GB / 32.0 GB (38.8%)
  Available: 19.6 GB

💾 Disk Space
  C:\: 234.5 GB / 500.0 GB (46.9% used)
  D:\: 1.2 TB / 2.0 TB (60.0% used)

🔋 Battery
  Status: Plugged in, charging
  Level: 85%

🌐 Network
  Ethernet: 192.168.1.100
  Wi-Fi: Not connected
```

## Notes

- This skill is read-only and safe
- Battery info only available on laptops
- Network info shows active interfaces only
- All data is current at time of execution

