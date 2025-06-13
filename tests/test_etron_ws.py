import unittest
import subprocess
import time
import websockets
import asyncio
import socket
import json


class EtronWebSocketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Launch the CSMS server
        cls.proc = subprocess.Popen(
            ["gway", "-dr", "etron"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        cls._wait_for_port(9000, timeout=10)

    @classmethod
    def tearDownClass(cls):
        if cls.proc:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()

    @staticmethod
    def _wait_for_port(port, timeout=10):
        start = time.time()
        while time.time() - start < timeout:
            try:
                with socket.create_connection(("localhost", port), timeout=1):
                    return
            except OSError:
                time.sleep(0.2)
        raise TimeoutError(f"Port {port} not responding after {timeout} seconds")

    def test_websocket_connection(self):
        uri = "ws://localhost:9000/charger123?token=foo"

        async def run_ws_check():
            async with websockets.connect(uri, subprotocols=["ocpp1.6"]) as websocket:
                message_id = "boot-test"
                payload = {
                    "chargePointModel": "FakeModel",
                    "chargePointVendor": "FakeVendor"
                }
                boot_notification = [2, message_id, "BootNotification", payload]
                await websocket.send(json.dumps(boot_notification))

                response = await websocket.recv()
                parsed = json.loads(response)
                self.assertEqual(parsed[1], message_id)
                self.assertIn("currentTime", parsed[2])

        asyncio.run(run_ws_check())

    def test_authorize_valid_rfid(self):
        uri = "ws://localhost:9000/tester1?token=foo"

        async def run_authorize_check():
            async with websockets.connect(uri, subprotocols=["ocpp1.6"]) as websocket:
                message_id = "auth-valid"
                payload = {
                    "idTag": "FFFFFFFF"  # Replace with known-good tag in rfid.txt
                }
                authorize_msg = [2, message_id, "Authorize", payload]
                await websocket.send(json.dumps(authorize_msg))

                response = await websocket.recv()
                parsed = json.loads(response)
                self.assertEqual(parsed[1], message_id)
                status = parsed[2]["idTagInfo"]["status"]
                self.assertEqual(status, "Accepted")

        asyncio.run(run_authorize_check())

    def test_authorize_invalid_rfid(self):
        uri = "ws://localhost:9000/tester2?token=foo"

        async def run_authorize_check():
            async with websockets.connect(uri, subprotocols=["ocpp1.6"]) as websocket:
                message_id = "auth-invalid"
                payload = {
                    "idTag": "ZZZZZZZZ"  # Replace with a tag you know is NOT in rfid.txt
                }
                authorize_msg = [2, message_id, "Authorize", payload]
                await websocket.send(json.dumps(authorize_msg))

                response = await websocket.recv()
                parsed = json.loads(response)
                self.assertEqual(parsed[1], message_id)
                status = parsed[2]["idTagInfo"]["status"]
                self.assertEqual(status, "Rejected")

        asyncio.run(run_authorize_check())


if __name__ == "__main__":
    unittest.main()
