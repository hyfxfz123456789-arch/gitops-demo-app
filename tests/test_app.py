import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import build_opener, ProxyHandler

import app


class AppHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"
        cls.opener = build_opener(ProxyHandler({}))

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def test_healthz(self):
        with self.opener.open(self.base_url + "/healthz", timeout=5) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), b"ok\n")

    def test_api_info(self):
        with self.opener.open(self.base_url + "/api/info", timeout=5) as response:
            self.assertEqual(response.status, 200)
            self.assertIn("application/json", response.headers["Content-Type"])
            data = json.load(response)

        self.assertEqual(set(data), {"version", "commit", "pod"})
        self.assertTrue(all(isinstance(value, str) for value in data.values()))

    def test_unknown_path_returns_404(self):
        with self.assertRaises(HTTPError) as caught:
            self.opener.open(self.base_url + "/does-not-exist", timeout=5)

        self.assertEqual(caught.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
