# tests/test_etron_ws.py

import unittest
import subprocess
import time
import websockets
import asyncio
import socket
import json
import os
import shutil
from gway import gw

CDV_PATH = 'data/etron/rfids.cdv'
KNOWN_GOOD_TAG = "FFFFFFFF"
ADMIN_TAG = "8505010F"
UNKNOWN_TAG = "ZZZZZZZZ"

ORIG_CDV_PATH = CDV_PATH + ".orig"

class EtronWebSocketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Backup the original file (if not already backed up)
        if os.path.exists(CDV_PATH):
            shutil.copy2(CDV_PATH, ORIG_CDV_PATH)
        else:
            # If file missing, create a minimal valid file and back it up
            with open(CDV_PATH, "w") as f:
                pass
            shutil.copy2(CDV_PATH, ORIG_CDV_PATH)

        # Now operate on the working copy
        gw.cdv.update(CDV_PATH, KNOWN_GOOD_TAG, user="test", balance="100")
        gw.cdv.update(CDV_PATH, ADMIN_TAG, user="Admin", balance="150")

        cls.proc = subprocess.Popen(
            ["gway", "-dr", "etron"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        cls._wait_for_port(9000, timeout=12)
        time.sleep(2)  # Let the server start fully

    @classmethod
    def tearDownClass(cls):
        if cls.proc:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
        # Restore the original file to avoid extraneous commits
        if os.path.exists(ORIG_CDV_PATH):
            shutil.move(ORIG_CDV_PATH, CDV_PATH)

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

    def _set_balance(self, tag, balance):
        gw.cdv.update(CDV_PATH, tag, balance=str(balance))

    def test_websocket_connection(self):
        """Confirm we can connect to the OCPP server and receive BootNotification response."""
        uri = "ws://localhost:9000/charger123?token=foo"
        async def run_ws_check():
            async with websockets.connect(uri, subprotocols=["ocpp1.6"], open_timeout=15) as websocket:
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
        """RFID in allowlist with balance >=1 should be Accepted"""
        # print("\n[test_authorize_valid_rfid] Set balance to 100 for FFFFFFFF")
        self._set_balance(KNOWN_GOOD_TAG, 100)
        # print_cdv_state("[test_authorize_valid_rfid] ")
        uri = "ws://localhost:9000/tester1?token=foo"
        async def run_authorize_check():
            async with websockets.connect(uri, subprotocols=["ocpp1.6"]) as websocket:
                message_id = "auth-valid"
                payload = {"idTag": KNOWN_GOOD_TAG}
                authorize_msg = [2, message_id, "Authorize", payload]
                await websocket.send(json.dumps(authorize_msg))
                response = await websocket.recv()
                # print(f"[test_authorize_valid_rfid] WS Response: {response}")
                parsed = json.loads(response)
                self.assertEqual(parsed[1], message_id)
                status = parsed[2]["idTagInfo"]["status"]
                self.assertEqual(status, "Accepted")
        asyncio.run(run_authorize_check())

    def test_authorize_with_extra_fields(self):
        """RFID with additional fields in CDV still authorizes correctly"""
        # print("\n[test_authorize_with_extra_fields] Set balance to 55 and add fields")
        gw.cdv.update(CDV_PATH, KNOWN_GOOD_TAG, balance="55", foo="bar", baz="qux")
        # print_cdv_state("[test_authorize_with_extra_fields] ")
        uri = "ws://localhost:9000/tester2?token=foo"
        async def run_authorize_check():
            async with websockets.connect(uri, subprotocols=["ocpp1.6"]) as websocket:
                message_id = "auth-extra"
                payload = {"idTag": KNOWN_GOOD_TAG}
                authorize_msg = [2, message_id, "Authorize", payload]
                await websocket.send(json.dumps(authorize_msg))
                response = await websocket.recv()
                # print(f"[test_authorize_with_extra_fields] WS Response: {response}")
                parsed = json.loads(response)
                self.assertEqual(parsed[1], message_id)
                status = parsed[2]["idTagInfo"]["status"]
                self.assertEqual(status, "Accepted")
        asyncio.run(run_authorize_check())

    def test_authorize_low_balance(self):
        """RFID present but balance <1 should be Rejected"""
        # print("\n[test_authorize_low_balance] Set balance to 0 for FFFFFFFF")
        self._set_balance(KNOWN_GOOD_TAG, 0)
        # print_cdv_state("[test_authorize_low_balance] ")
        uri = "ws://localhost:9000/tester3?token=foo"
        async def run_authorize_check():
            async with websockets.connect(uri, subprotocols=["ocpp1.6"]) as websocket:
                message_id = "auth-lowbal"
                payload = {"idTag": KNOWN_GOOD_TAG}
                authorize_msg = [2, message_id, "Authorize", payload]
                await websocket.send(json.dumps(authorize_msg))
                response = await websocket.recv()
                # print(f"[test_authorize_low_balance] WS Response: {response}")
                parsed = json.loads(response)
                self.assertEqual(parsed[1], message_id)
                status = parsed[2]["idTagInfo"]["status"]
                self.assertEqual(status, "Rejected")
        asyncio.run(run_authorize_check())

    def test_authorize_admin_tag(self):
        """Admin tag should be accepted (if balance >=1)"""
        # print("\n[test_authorize_admin_tag] Set balance to 150 for ADMIN_TAG")
        self._set_balance(ADMIN_TAG, 150)
        # print_cdv_state("[test_authorize_admin_tag] ")
        uri = "ws://localhost:9000/admin?token=foo"
        async def run_authorize_check():
            async with websockets.connect(uri, subprotocols=["ocpp1.6"]) as websocket:
                message_id = "auth-admin"
                payload = {"idTag": ADMIN_TAG}
                authorize_msg = [2, message_id, "Authorize", payload]
                await websocket.send(json.dumps(authorize_msg))
                response = await websocket.recv()
                # print(f"[test_authorize_admin_tag] WS Response: {response}")
                parsed = json.loads(response)
                self.assertEqual(parsed[1], message_id)
                status = parsed[2]["idTagInfo"]["status"]
                self.assertEqual(status, "Accepted")
        asyncio.run(run_authorize_check())

    def test_authorize_unknown_rfid(self):
        """Unknown tag must be rejected"""
        # print("\n[test_authorize_unknown_rfid] Unknown tag (ZZZZZZZZ)")
        # print_cdv_state("[test_authorize_unknown_rfid] ")
        uri = "ws://localhost:9000/unknown?token=foo"
        async def run_authorize_check():
            async with websockets.connect(uri, subprotocols=["ocpp1.6"]) as websocket:
                message_id = "auth-unknown"
                payload = {"idTag": UNKNOWN_TAG}
                authorize_msg = [2, message_id, "Authorize", payload]
                await websocket.send(json.dumps(authorize_msg))
                response = await websocket.recv()
                # print(f"[test_authorize_unknown_rfid] WS Response: {response}")
                parsed = json.loads(response)
                self.assertEqual(parsed[1], message_id)
                status = parsed[2]["idTagInfo"]["status"]
                self.assertEqual(status, "Rejected")
        asyncio.run(run_authorize_check())

    def test_concurrent_connections(self):
        """Multiple OCPP connections can be active at once without auth leakage."""
        # print("\n[test_concurrent_connections] Set FFFFFFFF balance=100, 8505010F balance=0")
        self._set_balance(KNOWN_GOOD_TAG, 100)
        self._set_balance(ADMIN_TAG, 0)
        # print_cdv_state("[test_concurrent_connections] ")
        uris = [
            "ws://localhost:9000/chargerA?token=foo",
            "ws://localhost:9000/chargerB?token=foo"
        ]
        async def run_concurrent():
            async def connect_and_auth(uri, idtag):
                async with websockets.connect(uri, subprotocols=["ocpp1.6"]) as websocket:
                    await websocket.send(json.dumps([2, "boot", "BootNotification", {}]))
                    await websocket.recv()
                    await websocket.send(json.dumps([2, "auth", "Authorize", {"idTag": idtag}]))
                    response = await websocket.recv()
                    # print(f"[test_concurrent_connections][{uri}] WS Response: {response}")
                    parsed = json.loads(response)
                    return parsed[2]["idTagInfo"]["status"]
            statuses = await asyncio.gather(
                connect_and_auth(uris[0], KNOWN_GOOD_TAG),
                connect_and_auth(uris[1], ADMIN_TAG),
            )
            self.assertEqual(statuses[0], "Accepted")
            self.assertEqual(statuses[1], "Rejected")
        asyncio.run(run_concurrent())

    def test_authorize_missing_balance(self):
        """If balance is missing, should be treated as 0 and Rejected."""
        # print("\n[test_authorize_missing_balance] Remove balance for FFFFFFFF")
        gw.cdv.update(CDV_PATH, KNOWN_GOOD_TAG, user="test")  # No balance field!
        # print_cdv_state("[test_authorize_missing_balance] ")
        uri = "ws://localhost:9000/missingbal?token=foo"
        async def run_authorize_check():
            async with websockets.connect(uri, subprotocols=["ocpp1.6"]) as websocket:
                message_id = "auth-missingbal"
                payload = {"idTag": KNOWN_GOOD_TAG}
                authorize_msg = [2, message_id, "Authorize", payload]
                await websocket.send(json.dumps(authorize_msg))
                response = await websocket.recv()
                # print(f"[test_authorize_missing_balance] WS Response: {response}")
                parsed = json.loads(response)
                self.assertEqual(parsed[1], message_id)
                status = parsed[2]["idTagInfo"]["status"]
                self.assertEqual(status, "Rejected")
        asyncio.run(run_authorize_check())

if __name__ == "__main__":
    unittest.main()
