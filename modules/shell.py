
import asyncio
import logging
import os
import platform
import subprocess

class ShellManager:
    def __init__(self, websocket):
        self._ws = websocket
        self._proc = None
        self._running = False

    async def start(self):
        if self._running:
            return "Shell is already running."

        self._running = True
        shell = 'cmd.exe' if platform.system() == "Windows" else '/bin/bash'
        
        try:
            self._proc = await asyncio.create_subprocess_shell(
                shell,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=os.getcwd(),
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if platform.system() == "Windows" else 0
            )
            
            # Start tasks to forward stdout and stderr
            asyncio.create_task(self._read_stream(self._proc.stdout, "stdout"))
            asyncio.create_task(self._read_stream(self._proc.stderr, "stderr"))

            logging.info("Interactive shell started.")
            return "Interactive shell started successfully."
        except Exception as e:
            self._running = False
            logging.error(f"Failed to start shell: {e}")
            return f"Error starting shell: {e}"

    async def stop(self):
        if not self._running or not self._proc:
            return "Shell is not running."

        self._running = False
        try:
            self._proc.terminate()
            await self._proc.wait()
            logging.info("Interactive shell stopped.")
            return "Interactive shell stopped."
        except Exception as e:
            logging.error(f"Error stopping shell: {e}")
            return f"Error stopping shell: {e}"

    async def write(self, command: str):
        if not self._running or not self._proc or not self._proc.stdin:
            return "Shell is not running or stdin is not available."

        try:
            self._proc.stdin.write(command.encode() + b'\n')
            await self._proc.stdin.drain()
        except Exception as e:
            logging.error(f"Error writing to shell: {e}")
            return f"Error writing to shell: {e}"

    async def _read_stream(self, stream, stream_name):
        while self._running and stream and not stream.at_eof():
            try:
                line = await stream.readline()
                if line:
                    await self._ws.send_json({
                        "type": "shell_output",
                        "stream": stream_name,
                        "data": line.decode(errors='ignore')
                    })
            except Exception as e:
                logging.error(f"Error reading from shell {stream_name}: {e}")
                break
