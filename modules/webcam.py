
import asyncio
import base64
import json
import logging

try:
    import cv2
except ImportError:
    cv2 = None
    logging.warning("OpenCV not found. Webcam functionality will be disabled.")

class WebcamStreamer:
    def __init__(self):
        self._task = None
        self._running = False
        self._ws = None
        self._cap = None

    async def start(self, ws, cam_index=0, resolution=None):
        if not cv2:
            await ws.send(json.dumps({"type": "command_output", "output": "Error: OpenCV is not installed on the client."}))
            return

        if self._running:
            await ws.send(json.dumps({"type": "command_output", "output": "Webcam stream is already running."}))
            return
        
        self._running = True
        self._ws = ws
        self._task = asyncio.create_task(self._stream(cam_index, resolution))
        logging.info(f"Starting webcam stream from camera {cam_index}.")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._cap:
            self._cap.release()
            self._cap = None
        logging.info("Webcam streaming stopped.")

    async def _stream(self, cam_index, resolution):
        try:
            self._cap = cv2.VideoCapture(cam_index)
            if not self._cap.isOpened():
                raise IOError(f"Camera {cam_index} not found or access denied.")

            if resolution:
                width, height = resolution
                self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                actual_width = self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)
                actual_height = self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
                logging.info(f"Attempting resolution {width}x{height}, got {actual_width}x{actual_height}")
                await self._ws.send(json.dumps({"type": "command_output", "output": f"Stream started with resolution: {actual_width}x{actual_height}"}))
            
            while self._running:
                ret, frame = self._cap.read()
                if not ret:
                    logging.warning(f"Could not read frame from camera {cam_index}. Stopping stream.")
                    if self._ws:
                        await self._ws.send(json.dumps({"type": "command_output", "output": f"Error: Camera {cam_index} connection lost."}))
                    break

                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                img_base64 = base64.b64encode(buffer).decode('utf-8')
                
                if self._ws:
                    await self._ws.send(json.dumps({"type": "webcam_frame", "data": img_base64}))
                
                await asyncio.sleep(0.05)  # ~20 FPS

        except (IOError, Exception) as e:
            logging.error(f"Error in webcam stream: {e}")
            if self._ws:
                await self._ws.send(json.dumps({"type": "command_output", "output": f"Error starting webcam stream: {e}"}))
        finally:
            if self._cap:
                self._cap.release()
            self._running = False
            logging.info("Webcam stream loop ended.")

def list_webcams() -> str:
    if not cv2:
        return "Error: OpenCV is not installed on the client."

    try:
        cams = []
        for i in range(10):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                cams.append(f"Camera {i}: Available")
                cap.release()
            else:
                # No need to report "Not available", just means we reached the end
                pass
        
        if not cams:
            return "No webcams found."
            
        return "\n".join(cams)
    except Exception as e:
        return f"Error listing webcams: {e}"
