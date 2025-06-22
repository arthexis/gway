# file: tests/test_etron_ws.py

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

KNOWN_GOOD_TAG = "FFFFFFFF"
ADMIN_TAG = "8505010F"
UNKNOWN_TAG = "ZZZZZZZZ"

class EtronWebSocketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data_dir = os.path.join("data", "etron")
        cls.rfids_cdv = os.path.join(cls.data_dir, "rfids.cdv")
        cls.backup_cdv = cls.rfids_cdv + ".bak"

        # List initial files (full paths) so we can revert and delete as needed
        cls.initial_files = set(os.listdir(cls.data_dir))

        # Backup existing CDV or create a new blank one and back it up
        if os.path.exists(cls.rfids_cdv):
            shutil.copy2(cls.rfids_cdv, cls.backup_cdv)
        else:
            with open(cls.rfids_cdv, "w") as f:
                pass
            shutil.copy2(cls.rfids_cdv, cls.backup_cdv)

        # Prepare known tags in the file used by both prod and test
        gw.cdv.update(cls.rfids_cdv, KNOWN_GOOD_TAG, user="test", balance="100")
        gw.cdv.update(cls.rfids_cdv, ADMIN_TAG, user="Admin", balance="150")

        # Start the OCPP/etron server (uses data/etron/rfids.cdv)
        cls.proc = subprocess.Popen(
            ["gway", "-r", "etron/cloud"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        cls._wait_for_port(9000, timeout=12)
        time.sleep(2)  # Let the server start fully

    @classmethod
    def tearDownClass(cls):
        # Kill the subprocess
        if hasattr(cls, "proc") and cls.proc:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()

        # Restore (or remove) rfids.cdv
        if os.path.exists(cls.backup_cdv):
            shutil.move(cls.backup_cdv, cls.rfids_cdv)
        # Remove any *new* files created in data/etron/ during the test run
        current_files = set(os.listdir(cls.data_dir))
        new_files = current_files - cls.initial_files
        for fname in new_files:
            fpath = os.path.join(cls.data_dir, fname)
            if os.path.isfile(fpath):
                os.remove(fpath)
            elif os.path.isdir(fpath):
                shutil.rmtree(fpath)

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
        self.__class__.gw_cdv_update(tag, balance=str(balance))

    @classmethod
    def gw_cdv_update(cls, tag, **fields):
        gw.cdv.update(cls.rfids_cdv, tag, **fields)

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
        self._set_balance(KNOWN_GOOD_TAG, 100)
        uri = "ws://localhost:9000/tester1?token=foo"
        async def run_authorize_check():
            async with websockets.connect(uri, subprotocols=["ocpp1.6"]) as websocket:
                message_id = "auth-valid"
                payload = {"idTag": KNOWN_GOOD_TAG}
                authorize_msg = [2, message_id, "Authorize", payload]
                await websocket.send(json.dumps(authorize_msg))
                response = await websocket.recv()
                parsed = json.loads(response)
                self.assertEqual(parsed[1], message_id)
                status = parsed[2]["idTagInfo"]["status"]
                self.assertEqual(status, "Accepted")
        asyncio.run(run_authorize_check())

    def test_authorize_with_extra_fields(self):
        """RFID with additional fields in CDV still authorizes correctly"""
        self.__class__.gw_cdv_update(KNOWN_GOOD_TAG, balance="55", foo="bar", baz="qux")
        uri = "ws://localhost:9000/tester2?token=foo"
        async def run_authorize_check():
            async with websockets.connect(uri, subprotocols=["ocpp1.6"]) as websocket:
                message_id = "auth-extra"
                payload = {"idTag": KNOWN_GOOD_TAG}
                authorize_msg = [2, message_id, "Authorize", payload]
                await websocket.send(json.dumps(authorize_msg))
                response = await websocket.recv()
                parsed = json.loads(response)
                self.assertEqual(parsed[1], message_id)
                status = parsed[2]["idTagInfo"]["status"]
                self.assertEqual(status, "Accepted")
        asyncio.run(run_authorize_check())

    def test_authorize_low_balance(self):
        """RFID present but balance <1 should be Rejected"""
        self._set_balance(KNOWN_GOOD_TAG, 0)
        uri = "ws://localhost:9000/tester3?token=foo"
        async def run_authorize_check():
            async with websockets.connect(uri, subprotocols=["ocpp1.6"]) as websocket:
                message_id = "auth-lowbal"
                payload = {"idTag": KNOWN_GOOD_TAG}
                authorize_msg = [2, message_id, "Authorize", payload]
                await websocket.send(json.dumps(authorize_msg))
                response = await websocket.recv()
                parsed = json.loads(response)
                self.assertEqual(parsed[1], message_id)
                status = parsed[2]["idTagInfo"]["status"]
                self.assertEqual(status, "Rejected")
        asyncio.run(run_authorize_check())

    def test_authorize_admin_tag(self):
        """Admin tag should be accepted (if balance >=1)"""
        self._set_balance(ADMIN_TAG, 150)
        uri = "ws://localhost:9000/admin?token=foo"
        async def run_authorize_check():
            async with websockets.connect(uri, subprotocols=["ocpp1.6"]) as websocket:
                message_id = "auth-admin"
                payload = {"idTag": ADMIN_TAG}
                authorize_msg = [2, message_id, "Authorize", payload]
                await websocket.send(json.dumps(authorize_msg))
                response = await websocket.recv()
                parsed = json.loads(response)
                self.assertEqual(parsed[1], message_id)
                status = parsed[2]["idTagInfo"]["status"]
                self.assertEqual(status, "Accepted")
        asyncio.run(run_authorize_check())

    def test_authorize_unknown_rfid(self):
        """Unknown tag must be rejected"""
        uri = "ws://localhost:9000/unknown?token=foo"
        async def run_authorize_check():
            async with websockets.connect(uri, subprotocols=["ocpp1.6"]) as websocket:
                message_id = "auth-unknown"
                payload = {"idTag": UNKNOWN_TAG}
                authorize_msg = [2, message_id, "Authorize", payload]
                await websocket.send(json.dumps(authorize_msg))
                response = await websocket.recv()
                parsed = json.loads(response)
                self.assertEqual(parsed[1], message_id)
                status = parsed[2]["idTagInfo"]["status"]
                self.assertEqual(status, "Rejected")
        asyncio.run(run_authorize_check())

    def test_concurrent_connections(self):
        """Multiple OCPP connections can be active at once without auth leakage."""
        self._set_balance(KNOWN_GOOD_TAG, 100)
        self._set_balance(ADMIN_TAG, 0)
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
        self.__class__.gw_cdv_update(KNOWN_GOOD_TAG, user="test")  # No balance field!
        uri = "ws://localhost:9000/missingbal?token=foo"
        async def run_authorize_check():
            async with websockets.connect(uri, subprotocols=["ocpp1.6"]) as websocket:
                message_id = "auth-missingbal"
                payload = {"idTag": KNOWN_GOOD_TAG}
                authorize_msg = [2, message_id, "Authorize", payload]
                await websocket.send(json.dumps(authorize_msg))
                response = await websocket.recv()
                parsed = json.loads(response)
                self.assertEqual(parsed[1], message_id)
                status = parsed[2]["idTagInfo"]["status"]
                self.assertEqual(status, "Rejected")
        asyncio.run(run_authorize_check())

    def test_server_ignores_callresult_messages(self):
        """Server should ignore valid [3, ...] CALLRESULT messages from client."""
        uri = "ws://localhost:9000/callresult1?token=foo"
        async def run_ignore_callresult():
            async with websockets.connect(uri, subprotocols=["ocpp1.6"]) as websocket:
                message_id = "irrelevant-id"
                callresult = [3, message_id, {"some": "result"}]
                await websocket.send(json.dumps(callresult))
                boot_message_id = "boot-check"
                boot_notification = [2, boot_message_id, "BootNotification", {
                    "chargePointModel": "FakeModel",
                    "chargePointVendor": "FakeVendor"
                }]
                await websocket.send(json.dumps(boot_notification))
                response = await websocket.recv()
                parsed = json.loads(response)
                self.assertEqual(parsed[1], boot_message_id)
                self.assertIn("currentTime", parsed[2])
        asyncio.run(run_ignore_callresult())

    def test_server_ignores_callerror_messages(self):
        """Server should ignore valid [4, ...] CALLERROR messages from client."""
        uri = "ws://localhost:9000/callerror1?token=foo"
        async def run_ignore_callerror():
            async with websockets.connect(uri, subprotocols=["ocpp1.6"]) as websocket:
                message_id = "irrelevant-id"
                callerror = [4, message_id, "SomeErrorCode", "Description", {"errorDetails": "optional"}]
                await websocket.send(json.dumps(callerror))
                boot_message_id = "boot-check2"
                boot_notification = [2, boot_message_id, "BootNotification", {
                    "chargePointModel": "FakeModel",
                    "chargePointVendor": "FakeVendor"
                }]
                await websocket.send(json.dumps(boot_notification))
                response = await websocket.recv()
                parsed = json.loads(response)
                self.assertEqual(parsed[1], boot_message_id)
                self.assertIn("currentTime", parsed[2])
        asyncio.run(run_ignore_callerror())

    def test_power_consumed_and_extract_meter(self):
        """Test power calculation and latest meter value extraction."""
        # Simulated transaction with MeterValues in kWh
        tx1 = {
            "meterStart": 150000,
            "meterStop": 152000,
            "MeterValues": [
                {"timestamp": 1, "sampledValue": [
                    {"value": 150.0, "measurand": "Energy.Active.Import.Register", "unit": "kWh"}
                ]},
                {"timestamp": 2, "sampledValue": [
                    {"value": 152.0, "measurand": "Energy.Active.Import.Register", "unit": "kWh"}
                ]},
            ]
        }
        pc = gw.ocpp.csms.power_consumed(tx1)
        self.assertAlmostEqual(pc, 2.0, places=2)
        lm = gw.ocpp.csms.extract_meter(tx1)
        self.assertAlmostEqual(lm, 152.0, places=2)

        # Simulated transaction with MeterValues in Wh (should convert to kWh)
        tx2 = {
            "meterStart": 100000,
            "meterStop": 102500,
            "MeterValues": [
                {"timestamp": 1, "sampledValue": [
                    {"value": 100000, "measurand": "Energy.Active.Import.Register", "unit": "Wh"}
                ]},
                {"timestamp": 2, "sampledValue": [
                    {"value": 102500, "measurand": "Energy.Active.Import.Register", "unit": "Wh"}
                ]},
            ]
        }
        pc = gw.ocpp.csms.power_consumed(tx2)
        self.assertAlmostEqual(pc, 2.5, places=2)
        lm = gw.ocpp.csms.extract_meter(tx2)
        self.assertAlmostEqual(lm, 102.5, places=2)

        # Only meterStart/meterStop (no MeterValues)
        tx3 = {"meterStart": 123000, "meterStop": 124500, "MeterValues": []}
        pc = gw.ocpp.csms.power_consumed(tx3)
        self.assertAlmostEqual(pc, 1.5, places=2)
        lm = gw.ocpp.csms.extract_meter(tx3)
        self.assertAlmostEqual(lm, 124.5, places=2)

        # Edge: no data
        pc = gw.ocpp.csms.power_consumed({})
        self.assertEqual(pc, 0.0)
        lm = gw.ocpp.csms.extract_meter({})
        self.assertEqual(lm, "-")

        # Edge: MeterValues present but missing correct measurand
        tx4 = {"MeterValues": [
            {"timestamp": 1, "sampledValue": [
                {"value": 12.34, "measurand": "NotEnergy", "unit": "kWh"}
            ]}
        ]}
        pc = gw.ocpp.csms.power_consumed(tx4)
        self.assertEqual(pc, 0.0)
        lm = gw.ocpp.csms.extract_meter(tx4)
        self.assertEqual(lm, "-")


if __name__ == "__main__":
    unittest.main()
