#!/usr/bin/env python3
"""
System Information Script for AG3NT.

Provides read-only access to system information including:
- OS details
- CPU usage
- Memory usage
- Disk space
- Battery status
- Network interfaces

Usage:
    python system_info.py           # Full report
    python system_info.py --cpu     # CPU only
    python system_info.py --memory  # Memory only
    python system_info.py --disk    # Disk only
    python system_info.py --battery # Battery only
    python system_info.py --network # Network only
"""

import argparse
import json
import os
import platform
import socket
from typing import Any

# Try to import psutil, provide helpful error if not available
try:
    import psutil
except ImportError:
    print("Error: psutil is required for system info.")
    print("Install with: pip install psutil")
    exit(1)


def get_os_info() -> dict[str, Any]:
    """Get operating system information."""
    return {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "hostname": socket.gethostname(),
    }


def get_cpu_info() -> dict[str, Any]:
    """Get CPU information."""
    freq = psutil.cpu_freq()
    return {
        "usage_percent": psutil.cpu_percent(interval=0.5),
        "cores_physical": psutil.cpu_count(logical=False),
        "cores_logical": psutil.cpu_count(logical=True),
        "frequency_mhz": freq.current if freq else None,
        "frequency_max_mhz": freq.max if freq else None,
    }


def get_memory_info() -> dict[str, Any]:
    """Get memory/RAM information."""
    mem = psutil.virtual_memory()
    return {
        "total_gb": round(mem.total / (1024**3), 2),
        "available_gb": round(mem.available / (1024**3), 2),
        "used_gb": round(mem.used / (1024**3), 2),
        "percent_used": mem.percent,
    }


def get_disk_info() -> list[dict[str, Any]]:
    """Get disk space information for all partitions."""
    disks = []
    for partition in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(partition.mountpoint)
            disks.append({
                "device": partition.device,
                "mountpoint": partition.mountpoint,
                "fstype": partition.fstype,
                "total_gb": round(usage.total / (1024**3), 2),
                "used_gb": round(usage.used / (1024**3), 2),
                "free_gb": round(usage.free / (1024**3), 2),
                "percent_used": usage.percent,
            })
        except (PermissionError, OSError):
            # Skip partitions we can't access
            continue
    return disks


def get_battery_info() -> dict[str, Any] | None:
    """Get battery information (if available)."""
    battery = psutil.sensors_battery()
    if battery is None:
        return None
    return {
        "percent": battery.percent,
        "plugged_in": battery.power_plugged,
        "seconds_left": battery.secsleft if battery.secsleft != psutil.POWER_TIME_UNLIMITED else None,
    }


def get_network_info() -> list[dict[str, Any]]:
    """Get network interface information."""
    interfaces = []
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()

    for iface, addr_list in addrs.items():
        iface_info = {
            "name": iface,
            "is_up": stats[iface].isup if iface in stats else False,
            "addresses": [],
        }
        for addr in addr_list:
            if addr.family == socket.AF_INET:
                iface_info["addresses"].append({
                    "type": "IPv4",
                    "address": addr.address,
                    "netmask": addr.netmask,
                })
            elif addr.family == socket.AF_INET6:
                iface_info["addresses"].append({
                    "type": "IPv6",
                    "address": addr.address,
                })
        if iface_info["addresses"]:  # Only include interfaces with addresses
            interfaces.append(iface_info)
    return interfaces


def format_report(data: dict[str, Any]) -> str:
    """Format the system info as a human-readable report."""
    lines = ["🖥️ System Status Report", "=" * 40, ""]

    if "os" in data:
        os_info = data["os"]
        lines.extend([
            "📊 Operating System",
            f"  OS: {os_info['system']} {os_info['release']}",
            f"  Version: {os_info['version'][:50]}",
            f"  Architecture: {os_info['machine']}",
            f"  Hostname: {os_info['hostname']}",
            "",
        ])

    if "cpu" in data:
        cpu = data["cpu"]
        freq_str = f"{cpu['frequency_mhz']:.0f} MHz" if cpu["frequency_mhz"] else "N/A"
        lines.extend([
            "💻 CPU",
            f"  Usage: {cpu['usage_percent']:.1f}%",
            f"  Cores: {cpu['cores_physical']} physical, {cpu['cores_logical']} logical",
            f"  Frequency: {freq_str}",
            "",
        ])

    if "memory" in data:
        mem = data["memory"]
        lines.extend([
            "🧠 Memory",
            f"  Used: {mem['used_gb']:.1f} GB / {mem['total_gb']:.1f} GB ({mem['percent_used']:.1f}%)",
            f"  Available: {mem['available_gb']:.1f} GB",
            "",
        ])

    if "disks" in data:
        lines.append("💾 Disk Space")
        for disk in data["disks"]:
            lines.append(
                f"  {disk['mountpoint']}: {disk['used_gb']:.1f} GB / {disk['total_gb']:.1f} GB "
                f"({disk['percent_used']:.1f}% used)"
            )
        lines.append("")

    if "battery" in data:
        battery = data["battery"]
        if battery:
            status = "Plugged in" if battery["plugged_in"] else "On battery"
            lines.extend([
                "🔋 Battery",
                f"  Status: {status}",
                f"  Level: {battery['percent']}%",
                "",
            ])
        else:
            lines.extend(["🔋 Battery", "  Not available (desktop)", ""])

    if "network" in data:
        lines.append("🌐 Network Interfaces")
        for iface in data["network"]:
            status = "Up" if iface["is_up"] else "Down"
            lines.append(f"  {iface['name']} ({status}):")
            for addr in iface["addresses"]:
                lines.append(f"    {addr['type']}: {addr['address']}")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Get system information")
    parser.add_argument("--cpu", action="store_true", help="CPU info only")
    parser.add_argument("--memory", action="store_true", help="Memory info only")
    parser.add_argument("--disk", action="store_true", help="Disk info only")
    parser.add_argument("--battery", action="store_true", help="Battery info only")
    parser.add_argument("--network", action="store_true", help="Network info only")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    # Determine what to include
    include_all = not any([args.cpu, args.memory, args.disk, args.battery, args.network])

    data: dict[str, Any] = {}

    if include_all:
        data["os"] = get_os_info()

    if include_all or args.cpu:
        data["cpu"] = get_cpu_info()

    if include_all or args.memory:
        data["memory"] = get_memory_info()

    if include_all or args.disk:
        data["disks"] = get_disk_info()

    if include_all or args.battery:
        data["battery"] = get_battery_info()

    if include_all or args.network:
        data["network"] = get_network_info()

    # Output
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(format_report(data))


if __name__ == "__main__":
    main()

