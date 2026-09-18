import json
import tempfile
import threading
import unittest
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from scripts.serve_research_demo import DemoHandler


class DemoRoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        Path(self.temp.name,'index.html').write_text('LIVE APP')
        Path(self.temp.name,'research.html').write_text('SAVED DEMO')
        self.server=ThreadingHTTPServer(('127.0.0.1',0),partial(DemoHandler,directory=self.temp.name))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}'
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()
    def test_home_never_opens_live_app_on_static_server(self):
        for path in ['/','/index.html']:
            with urlopen(self.url+path) as response:
                self.assertEqual(response.read().decode(),'SAVED DEMO')
    def test_live_api_is_explicit_json_error_for_get_and_post(self):
        for method in ['GET','POST']:
            with self.assertRaises(HTTPError) as caught:
                urlopen(Request(self.url+'/api/v1/agents/state',method=method))
            response=caught.exception
            self.assertEqual(response.code,503)
            self.assertEqual(response.headers.get_content_type(),'application/json')
            data=json.load(response)
            response.close()
            self.assertEqual(data['code'],'read_only_demo')
            self.assertEqual('http://127.0.0.1:18780/',data['live_url'])
