# file: projects/ocpp/evcs.py

import asyncio, json, random, time, websockets
from gway import gw


async def simulate(*,
        host: str = "[WEBSITE_HOST|127.0.0.1]",
        ws_port: int = "[WEBSOCKET_PORT|9000]",
        rfid: str = "FFFFFFFF",
        cp_path: str = "CPX",
        duration: int = 60,
        repeat: bool = False,
    ):
    """
    Simulate an EVCS connecting and running charging sessions over OCPP.
    Keeps a single persistent WebSocket connection and reuses it for each transaction.
    Logs all incoming CSMS→CP messages, sending confirmations for CALLs,
    and respects RemoteStopTransaction commands.
    """

    # Resolve connection parameters
    host    = gw.resolve(host)
    ws_port = int(gw.resolve(ws_port))
    uri     = f"ws://{host}:{ws_port}/{cp_path}"

    stop_event = asyncio.Event()

    async def listen_to_csms(ws):
        """
        Background listener for any incoming CSMS messages.
        Sends empty confirmations for CALL requests and triggers stop_event on RemoteStopTransaction.
        Logs any unexpected messages or connection closures.
        """
        try:
            while True:
                raw = await ws.recv()
                print(f"[Simulator ← CSMS] {raw}")
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    print("[Simulator] Warning: Received non-JSON message")
                    continue
                # Confirm any CALL messages
                if isinstance(msg, list) and msg[0] == 2:
                    msg_id, action, payload = msg[1], msg[2], (msg[3] if len(msg) > 3 else {})
                    await ws.send(json.dumps([3, msg_id, {}]))
                    if action == "RemoteStopTransaction":
                        print("[Simulator] Received RemoteStopTransaction → stopping transaction")
                        stop_event.set()
                else:
                    # Log unexpected message types
                    print("[Simulator] Notice: Unexpected message format", msg)
        except websockets.ConnectionClosed:
            print("[Simulator] Connection closed by server")
            stop_event.set()

    async with websockets.connect(uri, subprotocols=["ocpp1.6"]) as ws:
        print(f"[Simulator] Connected to {uri}")
        # Start background listener
        listener = asyncio.create_task(listen_to_csms(ws))

        # Initial handshake: BootNotification and Authorize
        await ws.send(json.dumps([2, "boot", "BootNotification", {
            "chargePointModel": "Simulator",
            "chargePointVendor": "SimVendor"
        }]))
        await ws.recv()

        await ws.send(json.dumps([2, "auth", "Authorize", {"idTag": rfid}]))
        await ws.recv()

        # Main transaction loop
        while not stop_event.is_set():
            # Clear stop_event for this cycle
            stop_event.clear()

            # StartTransaction
            meter_start = random.randint(1000, 2000)
            await ws.send(json.dumps([2, "start", "StartTransaction", {
                "connectorId": 1,
                "idTag": rfid,
                "meterStart": meter_start
            }]))
            resp = await ws.recv()
            tx_id = json.loads(resp)[2].get("transactionId")
            print(f"[Simulator] Transaction {tx_id} started at meter {meter_start}")

            # MeterValues loop with duration variation
            actual_duration = random.uniform(duration * 0.75, duration * 1.25)
            interval = actual_duration / 10
            meter = meter_start

            for _ in range(10):
                if stop_event.is_set():
                    print("[Simulator] Stop event triggered—ending meter loop")
                    break
                meter += random.randint(50, 150)
                meter_kwh = meter / 1000.0
                await ws.send(json.dumps([2, "meter", "MeterValues", {
                    "connectorId": 1,
                    "transactionId": tx_id,
                    "meterValue": [{
                        "timestamp": time.strftime('%Y-%m-%dT%H:%M:%S') + "Z",
                        "sampledValue": [{
                            "value": f"{meter_kwh:.3f}",
                            "measurand": "Energy.Active.Import.Register",
                            "unit": "kWh",
                            "context": "Sample.Periodic"
                        }]
                    }]
                }]))
                await asyncio.sleep(interval)


            # StopTransaction
            await ws.send(json.dumps([2, "stop", "StopTransaction", {
                "transactionId": tx_id,
                "idTag": rfid,
                "meterStop": meter
            }]))
            await ws.recv()
            print(f"[Simulator] Transaction {tx_id} stopped at meter {meter}")

            if not repeat or stop_event.is_set():
                break

            print(f"[Simulator] Waiting {actual_duration:.1f}s before next cycle")
            await asyncio.sleep(actual_duration)

        # Cleanup listener
        listener.cancel()
        try:
            await listener
        except asyncio.CancelledError:
            pass

        print("[Simulator] Simulation ended.")

