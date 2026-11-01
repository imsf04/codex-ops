"""Explicit loopback-only, read-only dashboard serving; no arbitrary file routes."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from urllib.parse import urlsplit


def _allowed(handler):
    authority = f'127.0.0.1:{handler.server.server_port}'
    if handler.headers.get('Host') != authority:
        return False
    origin = handler.headers.get('Origin')
    return origin is None or origin == 'http://' + authority


def _route(path):
    if len(path) > 512:
        return None
    parsed = urlsplit(path)
    if parsed.query or parsed.fragment:
        return None
    return parsed.path if parsed.path in ('/', '/snapshot') else None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def _send(self, status, body, kind):
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not _allowed(self):
            self._send(403, b'Forbidden', 'text/plain')
            return
        route = _route(self.path)
        if route is None:
            self._send(404, b'Not found', 'text/plain')
            return
        try:
            value = self.server.collect()
            body, kind = self._body(route, value)
            self._send(200, body.encode('utf-8'), kind)
        except (OSError, ValueError):
            self._send(503, b'Snapshot unavailable', 'text/plain')

    def _body(self, route, value):
        if route == '/snapshot':
            return json.dumps(value, ensure_ascii=True), 'application/json; charset=utf-8'
        return self.server.render(value), 'text/html; charset=utf-8'

    def do_POST(self):
        self._send(405, b'Read-only endpoint', 'text/plain')

    do_PUT = do_DELETE = do_PATCH = do_POST


def server(collect, render, port=0):
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError('port must be 0..65535')
    result = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    result.daemon_threads = True
    result.collect, result.render = collect, render
    return result
