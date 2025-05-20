import json, os, time, requests
from datetime import datetime
from bottle import Bottle, response, hook
from ws4py.server.wsgiutils import WebSocketWSGIApplication
from ws4py.websocket import WebSocket
from paste.urlmap import URLMap
from dateparser import parse as parse_date
from gway import gw


def setup_csms_app(*,
        app=None,
        host="[OCPP_CSMS_HOST|127.0.0.1]",
        port="[OCPP_CSMS_PORT|8888]",
        endpoint="csms",
        reset=False,
        txn_id=42,
        interval=300,
        auth=False,
        logfile=None,
        filter=None,
        ignore=None,
        evccids=None,
        cutoff=None,
        report=None,
        qr_auth_url=None,
        work_hours=None,
        timeout=30,
        paths=None,
    ):
    """
    Configure a combined Bottle + ws4py app to act as an OCPP CSMS server.
    Returns a WSGI app mapping WebSocket and HTTP endpoints.
    """
    # Bottle app for HTTP routes (QR approval, status page)
    if app is None:
        app = Bottle()

    # CORS middleware
    @hook('after_request')
    def enable_cors():
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = '*'
        response.headers['Access-Control-Allow-Headers'] = '*'

    # Shared state
    allowed_paths = [p.strip() for p in paths.split(',')] if paths else None
    gw.info(f"Configuring CSMS on ws://{host}:{port}/{endpoint}/<path> reset={reset}")
    reset_done = set()
    next_txn_id = txn_id
    cutoff_dt = parse_date(cutoff) if cutoff else None
    session_data = {}
    qr_data = {}

    def should_log(action):
        return not (filter and action not in filter) and not (ignore and action in ignore)

    def log_event(path, label, data=None):
        gw.info(f"[OCPP:CSMS:{path}] {label}", data)
        if logfile:
            with open(gw.resource(logfile), 'a') as f:
                f.write(json.dumps({
                    'timestamp': gw.timestamp(), 'path': path, 'event': label, 
                    'data': data}, default=str) + '\n')

    def save_report(path):
        data = session_data.get(path)
        if not data:
            return
        charger_id = data.get('boot', {}).get('chargePointSerialNumber', 'unknown')
        timestamp = data.get('start_time', gw.timestamp())
        filename = f"{charger_id}_{timestamp.replace(':', '_')}.json"
        if report:
            gw.info(f"Saving report for {path} to {report}/{filename}")
            target = gw.resource(report)
            if os.path.isdir(target):
                with open(target / filename, 'w') as f:
                    f.write(json.dumps(data, default=str))
            else:
                with open(target, 'a') as f:
                    f.write(json.dumps(data, default=str) + '\n')

    def handle_auth(path):
        def parse_time_str(t): return datetime.strptime(t, '%H:%M').time()
        if work_hours:
            now = datetime.now().time()
            if not any(parse_time_str(s) <= now <= parse_time_str(e) for s, e in work_hours):
                gw.warning(f"Rejected auth for {path}: outside work hours")
                return {'status': 'Rejected'}
        if qr_auth_url:
            try:
                res = requests.post(qr_auth_url, json={'path': path})
                if res.status_code == 200:
                    qr_data[path] = res.json()
                    return qr_data[path]
                gw.error(f"QR auth failed: {res.status_code} {res.text}")
            except Exception as e:
                gw.error(f"QR auth request failed: {e}")
                cached = qr_data.get(path)
                if cached:
                    exp = cached.get('expiration')
                    try:
                        from dateutil.parser import parse as parse_exp
                        if exp and parse_exp(exp) < datetime.now():
                            gw.warning(f"Cached QR auth expired for {path}")
                            return {'status': 'Rejected'}
                    except:
                        gw.error(f"Invalid expiration: {exp}")
                    gw.warning(f"Using cached QR auth for {path}")
                    return cached
                return {'status': 'Rejected'}
        return {'status': 'Accepted' if auth else 'Rejected'}

    def handle_evccid_auth(evccid):
        with open(evccids, 'r') as f:
            allowed = set(l.strip() for l in f)
        return {'status': 'Accepted'} if evccid in allowed else {'status': 'Rejected'}

    # WebSocket handler class
    class CSMSWebSocket(WebSocket):
        def opened(self):
            self.path = self.environ.get('PATH_INFO', '').split(f'/{endpoint}/')[-1]
            if allowed_paths and self.path not in allowed_paths:
                self.close()
                return
            session_data[self.path] = {'boot': None, 'status': [], 'start_time': None,
                                       'stop_time': None, 'meter_values': [], 'idTag': None}
            log_event(self.path, 'Connection accepted')

        def received_message(self, message):
            raw = message.data.decode('utf-8')
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                return
            if not (isinstance(msg, list) and len(msg) >= 3 and msg[0] == 2):
                return
            _, msg_id, action, *rest = msg
            payload = rest[0] if rest else {}
            if cutoff_dt and payload.get('timestamp'):
                try:
                    if parse_date(payload['timestamp']) < cutoff_dt:
                        return
                except:
                    pass
            log_event(self.path, f"CALL {action}", payload)
            if not should_log(action):
                return
            nonlocal next_txn_id
            resp = [3, msg_id, {}]
            # reset logic
            if reset and self.path not in reset_done:
                reset_done.add(self.path)
                for cmd in ['Reset', 'ClearCache']:
                    cid = f"{cmd.lower()}-{gw.timestamp()}"
                    body = {'type': 'Hard'} if cmd == 'Reset' else {}
                    self.send(json.dumps([2, cid, cmd, body]))
                    log_event(self.path, f"Sent {cmd}")
            # action handlers...
            if action == 'BootNotification':
                session_data[self.path]['boot'] = payload
                resp[2] = {'status': 'Accepted', 'currentTime': gw.timestamp(), 'interval': interval}
            elif action == 'Authorize':
                tag = payload.get('idTag'); ev = payload.get('customData', {}).get('evccid')
                session_data[self.path]['idTag'] = tag; session_data[self.path]['evccid'] = ev
                result = ev and evccids and handle_evccid_auth(ev) or handle_auth(self.path)
                session_data[self.path]['authorized'] = result['status']=='Accepted'
                resp[2] = {'idTagInfo': result}
            elif action == 'StartTransaction':
                if qr_auth_url and not session_data[self.path].get('authorized'):
                    for _ in range(int(timeout)):
                        time.sleep(1)
                        if session_data[self.path].get('authorized'): break
                status = 'Accepted' if session_data[self.path].get('authorized') else 'Invalid'
                resp[2] = {'transactionId': next_txn_id, 'idTagInfo': {'status': status}}
                session_data[self.path]['start_time'] = gw.timestamp()
                if status=='Accepted': next_txn_id += 1
            elif action == 'StopTransaction':
                session_data[self.path]['stop_time'] = gw.timestamp(); save_report(self.path)
            elif action == 'StatusNotification':
                session_data[self.path]['status'].append(payload)
            elif action == 'MeterValues':
                session_data[self.path]['meter_values'].append(payload)
            elif action == 'Heartbeat':
                resp[2] = {'currentTime': gw.timestamp()}
            # send ACK
            self.send(json.dumps(resp))

        def closed(self, code, reason=None):
            log_event(self.path, 'Disconnected')

    # Mount WebSocket app at /<endpoint>/
    ws_path = f"/{endpoint}/"
    ws_app = WebSocketWSGIApplication(handler_cls=CSMSWebSocket)

    # HTTP routes: QR approval
    @app.post(f"/{endpoint}/qr/approve/<path>")
    def approve_qr(path):
        qr_data[path] = {'status': 'Accepted'}
        session_data.setdefault(path, {})['authorized'] = True
        return {'status': 'approved'}

    # HTTP status page
    if allowed_paths:
        @app.route(f"/{endpoint}")
        def list_paths():
            html = '<h1>Approve Chargers</h1><ul>'
            for p in allowed_paths:
                img = gw.qr_code.generate_img(f"http://{host}:{port}/{endpoint}/qr/approve/{p}", as_base64=True)
                status = session_data.get(p, {}).get('authorized') and 'Authorized' or 'Pending'
                html += f"<li><p>{p}: {status}</p><img src='data:image/png;base64,{img}'/></li>"
            html += '</ul>'
            response.content_type = 'text/html'
            return html

    # Combine WSGI apps: WebSocket under /<endpoint>/, Bottle for everything else
    wsgi_app = URLMap({ws_path: ws_app, '/': app})
    gw.info(f"Prepared CSMS {ws_app=}")
    return wsgi_app
