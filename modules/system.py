import asyncio
import logging
import os
import platform
import shutil
import socket

import psutil

def get_detailed_system_info(initial_info: dict) -> str:
    """Gathers detailed system information."""
    try:
        info = initial_info.copy()
        info["Local IPs"] = ", ".join(socket.gethostbyname_ex(info["hostname"])[2])
        info["CPU"] = platform.processor()
        try:
            ram = psutil.virtual_memory()
            info["RAM Total (MB)"] = round(ram.total / (1024 ** 2), 2)
            info["RAM Used (MB)"] = round(ram.used / (1024 ** 2), 2)
        except Exception as e:
            info["RAM"] = f"Unknown ({e})"
        try:
            disk = shutil.disk_usage('.')
            info["Disk Total (GB)"] = round(disk.total / (1024 ** 3), 2)
            info["Disk Used (GB)"] = round(disk.used / (1024 ** 3), 2)
            info["Disk Free (GB)"] = round(disk.free / (1024 ** 3), 2)
        except Exception as e:
            info["Disk"] = f"Unknown ({e})"
        
        return "\n".join(f"{k.replace('_', ' ').title()}: {v}" for k, v in info.items())
    except Exception as e:
        return f"Error getting system info: {e}"

def get_process_list() -> str:
    """Lists running processes."""
    try:
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'username', 'cpu_percent', 'memory_info']):
            try:
                pinfo = proc.as_dict(attrs=['pid', 'name', 'username', 'cpu_percent', 'memory_info'])
                pinfo['memory_mb'] = round(pinfo['memory_info'].rss / (1024 * 1024), 2)
                processes.append(pinfo)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        
        processes.sort(key=lambda p: p.get('cpu_percent', 0), reverse=True)
        
        output = ["PID\tCPU(%)\tMEM(MB)\tUsername\tName"]
        for p in processes[:50]:
            output.append(f"{p['pid']}\t{p.get('cpu_percent', 0):.2f}\t{p['memory_mb']:.2f}\t{p.get('username', 'N/A')}\t{p['name']}")
        return "\n".join(output)
    except Exception as e:
        return f"Error listing processes: {e}"

def kill_process(pid: str) -> str:
    """Terminates a process by its PID."""
    try:
        pid_int = int(pid)
        process = psutil.Process(pid_int)
        process.terminate()
        return f"Process {pid_int} ({process.name()}) terminated."
    except ValueError:
        return "Error: Invalid PID."
    except psutil.NoSuchProcess:
        return f"Error: Process with PID {pid} not found."
    except psutil.AccessDenied:
        return f"Error: Access denied to terminate process {pid}."
    except Exception as e:
        return f"Error terminating process: {e}"

async def run_shell_command(command: str) -> str:
    """Executes a shell command and returns its output."""
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=os.getcwd()
        )
        stdout, stderr = await proc.communicate()
        output = (stdout.decode(errors='ignore') + stderr.decode(errors='ignore')).strip()
        return output if output else f"Command '{command}' executed with no output."
    except FileNotFoundError:
        return f"Error: Command or shell not found. Check the system's PATH."
    except Exception as e:
        return f"Error executing '{command}': {e}"
