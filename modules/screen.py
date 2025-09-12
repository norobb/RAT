
import asyncio
import base64
import io
import json
import logging

try:
    import mss
    import mss.tools
    from PIL import Image
except ImportError:
    mss = None
    Image = None
    logging.warning("Screen-related libraries not found. Screen streaming will be disabled.")

class ScreenStreamer:
    def __init__(self):
        self._task = None
        self._running = False
        self._ws = None

    async def start(self, ws):
        if not mss or not Image:
            await ws.send(json.dumps({"type": "command_output", "output": "Error: Screen streaming libraries are not installed on the client."}))
            return

        if self._running:
            return
        self._running = True
        self._ws = ws
        self._task = asyncio.create_task(self._stream())
        logging.info("Screen streaming started.")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logging.info("Screen streaming stopped.")

    async def _stream(self):
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            while self._running:
                try:
                    sct_img = sct.grab(monitor)
                    img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                    
                    # Use ANTIALIAS if LANCZOS is not available
                    resample_method = Image.Resampling.LANCZOS if hasattr(Image.Resampling, 'LANCZOS') else Image.Resampling.BICUBIC
                    img.thumbnail((1280, 720), resample_method)
                    
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG")
                    img_base64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                    
                    if self._ws and hasattr(self._ws, 'send'):
                        await self._ws.send(json.dumps({"type": "screen_frame", "data": img_base64}))
                    
                    await asyncio.sleep(0.1)
                except Exception as e:
                    logging.error(f"Error in screen stream: {e}")
                    break
        logging.info("Screen stream loop ended.")

def get_screenshot():
    if not mss:
        return {"type": "screenshot", "data": "", "error": "MSS library not installed."}
    with mss.mss() as sct:
        sct_img = sct.grab(sct.monitors[1])
        img_bytes = mss.tools.to_png(sct_img.rgb, sct_img.size) if sct_img else b""
    return {"type": "screenshot", "data": base64.b64encode(img_bytes).decode("utf-8")}
