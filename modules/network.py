import asyncio
import logging
import platform
import socket
import urllib.request

import psutil

def get_public_ip() -> str:
    """Retrieves the public IP address."""
    try:
        with urllib.request.urlopen('https://api.ipify.org', timeout=5) as resp:
            return resp.read().decode('utf8')
    except Exception as e:
        logging.warning(f"Could not get public IP: {e}")
        return "Unknown"

def get_network_info() -> str:
    """Gathers detailed network information."""
    try:
        info = {"Public IP": get_public_ip()}
        hostname = socket.gethostname()
        info["Hostname"] = hostname
        try:
            info["Local IPs"] = ", ".join(socket.gethostbyname_ex(hostname)[2])
        except socket.gaierror:
            info["Local IPs"] = "Not found"

        if_addrs = psutil.net_if_addrs()
        interfaces = []
        for interface_name, interface_addresses in if_addrs.items():
            for address in interface_addresses:
                if str(address.family) == 'AddressFamily.AF_INET':
                    interfaces.append(f"  - {interface_name}: IP {address.address}, Mask {address.netmask}")
        info["Interfaces"] = "\n".join(interfaces)

        try:
            connections = psutil.net_connections(kind='inet')
            info["Active TCP Connections"] = str(len(connections))
        except Exception as e:
            info["Active TCP Connections"] = f"Unknown ({e})"

        return "\n".join(f"{k}: {v}" for k, v in info.items())
    except Exception as e:
        return f"Error getting network info: {e}"

async def scan_network(cidr_range: str) -> str:
    """Scans the network for active hosts in the given CIDR range."""
    try:
        import ipaddress
        net = ipaddress.ip_network(cidr_range, strict=False)
        tasks = []
        active_hosts = []

        ping_cmd = "ping -n 1 -w 500" if platform.system() == "Windows" else "ping -c 1 -W 0.5"

        async def ping_host(ip):
            proc = await asyncio.create_subprocess_shell(
                f"{ping_cmd} {ip}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            if proc.returncode == 0:
                active_hosts.append(str(ip))

        for ip in net.hosts():
            tasks.append(ping_host(str(ip)))

        await asyncio.gather(*tasks, return_exceptions=True)

        if not active_hosts:
            return f"No active hosts found in range {cidr_range}."

        return f"Active hosts in {cidr_range}:\n" + "\n".join(sorted(active_hosts))

    except ImportError:
        return "Error: 'ipaddress' module not found."
    except ValueError:
        return f"Error: Invalid CIDR range '{cidr_range}'."
    except Exception as e:
        return f"Error during network scan: {e}"
