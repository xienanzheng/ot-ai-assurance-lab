#!/usr/bin/env python3
"""Serve the built, read-only research demo on localhost without Docker or Node."""
import argparse
import json
from urllib.parse import urlsplit
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import webbrowser
from urllib.request import urlopen


class DemoHandler(SimpleHTTPRequestHandler):
    def api_unavailable(self):
        payload=json.dumps({'code':'read_only_demo','detail':'This is the recorded demo. Live controls are available at http://127.0.0.1:18780/.','live_url':'http://127.0.0.1:18780/'}).encode()
        self.send_response(503)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(payload)))
        self.end_headers()
        if self.command!='HEAD':self.wfile.write(payload)

    def send_head(self):
        path=urlsplit(self.path).path
        if path in ('/','/index.html'):
            self.send_response(302)
            self.send_header('Location','/research.html')
            self.send_header('Content-Length','0')
            self.end_headers()
            return None
        if path.startswith('/api/'):
            self.api_unavailable()
            return None
        return super().send_head()

    def do_POST(self):
        if urlsplit(self.path).path.startswith('/api/'):
            self.api_unavailable()
        else:self.send_error(405,'Read-only demo')

    do_PUT=do_POST
    do_PATCH=do_POST
    do_DELETE=do_POST

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-WaterLab-Demo', 'read-only')
        super().end_headers()

    def log_message(self, format, *args):
        # Show failures; avoid filling the presenter's Terminal with asset requests.
        if len(args) > 1 and str(args[1]).startswith(('4', '5')):
            super().log_message(format, *args)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=18774)
    parser.add_argument('--no-open', action='store_true')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Choose a port between 1024 and 65535')
    root = Path(__file__).resolve().parents[1]
    build = root / 'services/web/dist'
    if not (build / 'research.html').is_file() or not (build / 'research/index.json').is_file():
        parser.error('Demo build or evidence missing. Run: python3 scripts/research_evidence.py followed by npm run build --prefix services/web')
    url = f'http://127.0.0.1:{args.port}/research.html'
    try:
        server = ThreadingHTTPServer(('127.0.0.1', args.port), partial(DemoHandler, directory=str(build)))
    except OSError as exc:
        try:
            with urlopen(url, timeout=2) as response:
                existing = response.headers.get('X-WaterLab-Demo') == 'read-only'
        except OSError:
            existing = False
        if existing:
            print(f'Demo already running: {url}', flush=True)
            if not args.no_open:
                webbrowser.open(url)
            return
        parser.error(f'Cannot open localhost port {args.port}: {exc}. Close the previous demo or choose --port 18775.')
    print(f'Local AI research demo: {url}\nSaved evidence only. Press Ctrl+C to stop.', flush=True)
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nDemo stopped.')
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
