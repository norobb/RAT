
import pytest
import asyncio
import websockets
import json

@pytest.mark.asyncio
async def test_client_server_connection(server_process):
    """
    Tests the basic connection between a client and the server.
    """
    test_server_uri = "ws://127.0.0.1:8001/rat"
    
    try:
        async with websockets.connect(test_server_uri) as websocket:
            # 1. Send initial info message
            initial_info = {
                "type": "info",
                "data": {
                    "hostname": "test-client",
                    "os": "pytest-os",
                }
            }
            await websocket.send(json.dumps(initial_info))

            # 2. Receive a response (the server doesn't send a direct response to info,
            #    but we can check if the connection is alive)
            #    Let's test the heartbeat
            await websocket.send(json.dumps({"type": "ping"}))
            response = await websocket.recv()
            response_data = json.loads(response)
            
            assert response_data.get("type") == "pong"

    except websockets.exceptions.ConnectionClosed as e:
        pytest.fail(f"WebSocket connection failed: {e}")
    except Exception as e:
        pytest.fail(f"An unexpected error occurred: {e}")

