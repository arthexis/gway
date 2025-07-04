# file: tests/test_etron_ws.py

import unittest
import sys
import subprocess
import time
import websockets
import asyncio
import socket
import json
import os
import shutil
import requests
from gway import gw

KNOWN_GOOD_TAG = "FFFFFFFF"
ADMIN_TAG = "8505010F"
UNKNOWN_TAG = "ZZZZZZZZ"

import signal

class EtronWebSocketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proc = None
        try:
            cls.data_dir = os.path.join("data", "etron")
            cls.rfids_cdv = os.path.join(cls.data_dir, "rfids.cdv")
            cls.backup_cdv = cls.rfids_cdv + ".bak"
            cls.initial_files = set(os.listdir(cls.data_dir))
            if os.path.exists(cls.rfids_cdv):
                shutil.copy2(cls.rfids_cdv, cls.backup_cdv)
            else:
                with open(cls.rfids_cdv, "w") as f:
                    pass
                shutil.copy2(cls.rfids_cdv, cls.backup_cdv)
            gw.cdv.update(cls.rfids_cdv, KNOWN_GOOD_TAG, user="test", balance="100")
            gw.cdv.update(cls.rfids_cdv, ADMIN_TAG, user="Admin", balance="150")

            # --- START SERVER ---
            cls.proc = subprocess.Popen(
                ["gway", "-r", "etron/cloud"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            cls._wait_for_port(9000, timeout=12)
        except Exception as e:
            # Read and print whatever the process wrote
            try:
                output = cls.proc.stdout.read()
                print("=== etron/cloud subprocess output ===", file=sys.stderr)
                print(output, file=sys.stderr)
            except Exception as out_exc:
                print("Could not read subprocess output:", out_exc, file=sys.stderr)
            # Kill process
            cls._cleanup_server()
            raise

    @classmethod
    def tearDownClass(cls):
        cls._cleanup_server()

    @classmethod
    def _cleanup_server(cls):
        # Kill the subprocess
        proc = getattr(cls, "proc", None)
        if proc:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # Try a SIGKILL if not already dead
                    if hasattr(proc, "kill"):
                        proc.kill()
                    else:
                        # On Windows, terminate is kill, but just in case
                        os.kill(proc.pid, signal.SIGTERM)
            except Exception:
                pass
            cls.proc = None
            time.sleep(1)  # Let OS free the port

        # Restore/remove rfids.cdv and delete any new files
        data_dir = getattr(cls, "data_dir", None)
        rfids_cdv = getattr(cls, "rfids_cdv", None)
        backup_cdv = getattr(cls, "backup_cdv", None)
        initial_files = getattr(cls, "initial_files", set())
        if backup_cdv and os.path.exists(backup_cdv):
            shutil.move(backup_cdv, rfids_cdv)
        if data_dir and os.path.isdir(data_dir):
            current_files = set(os.listdir(data_dir))
            new_files = current_files - initial_files
            for fname in new_files:
                fpath = os.path.join(data_dir, fname)
                try:
                    if os.path.isfile(fpath):
                        os.remove(fpath)
                    elif os.path.isdir(fpath):
                        shutil.rmtree(fpath)
                except Exception:
                    pass

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

    def test_remote_stop_transaction(self):
        """Dashboard Stop action triggers RemoteStopTransaction on the CP."""
        uri = "ws://localhost:9000/stopper?token=foo"

        async def run_stop_check():
            async with websockets.connect(uri, subprotocols=["ocpp1.6"]) as ws:
                # Boot and authorize
                await ws.send(json.dumps([2, "boot", "BootNotification", {
                    "chargePointModel": "Fake", "chargePointVendor": "Fake"}]))
                await ws.recv()
                await ws.send(json.dumps([2, "auth", "Authorize", {"idTag": KNOWN_GOOD_TAG}]))
                await ws.recv()
                # StartTransaction
                await ws.send(json.dumps([2, "start", "StartTransaction", {
                    "connectorId": 1,
                    "idTag": KNOWN_GOOD_TAG,
                    "meterStart": 1000
                }]))
                await ws.recv()

                # Issue Stop from dashboard
                await asyncio.to_thread(
                    requests.post,
                    "http://127.0.0.1:8000/ocpp/csms/charger-status",
                    data={"charger_id": "stopper", "action": "remote_stop", "do": "send"},
                    timeout=5,
                )

                raw = await asyncio.wait_for(ws.recv(), timeout=10)
                msg = json.loads(raw)
                self.assertEqual(msg[2], "RemoteStopTransaction")

        asyncio.run(run_stop_check())


if __name__ == "__main__":
    unittest.main()
