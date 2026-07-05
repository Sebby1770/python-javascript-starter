import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from urllib.request import urlopen

from taskpulse import server as server_module
from taskpulse.server import TaskPulseHandler, create_server


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._temp_dir = tempfile.TemporaryDirectory()
        cls._data_path = Path(cls._temp_dir.name) / "tasks.json"
        cls._server = create_server(host="127.0.0.1", port=0)
        cls._port = cls._server.server_address[1]
        cls._base_url = f"http://127.0.0.1:{cls._port}"

        from taskpulse.store import TaskStore

        TaskPulseHandler.store = TaskStore(data_path=cls._data_path)
        TaskPulseHandler.store.add_task(title="Server task", tags=["api"])

        cls._thread = threading.Thread(target=cls._server.serve_forever, daemon=True)
        cls._thread.start()

    @classmethod
    def tearDownClass(cls):
        cls._server.shutdown()
        cls._server.server_close()
        cls._temp_dir.cleanup()

    def _request(self, method: str, path: str, payload=None, headers=None):
        conn = HTTPConnection("127.0.0.1", self._port, timeout=5)
        body = None
        request_headers = headers or {}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        conn.request(method, path, body=body, headers=request_headers)
        response = conn.getresponse()
        data = response.read()
        conn.close()
        return response.status, json.loads(data.decode("utf-8")) if data else {}

    def test_health_endpoint(self):
        status, data = self._request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "ok")

    def test_export_and_import_endpoints(self):
        status, exported = self._request("GET", "/api/tasks/export")
        self.assertEqual(status, 200)
        self.assertTrue(isinstance(exported, list))

        status, data = self._request(
            "POST",
            "/api/tasks/import",
            payload=[{"id": 1, "title": "Imported via API", "tags": ["sync"]}],
        )
        self.assertEqual(status, 200)
        self.assertEqual(data["tasks"][0]["title"], "Imported via API")

    def test_openapi_endpoint(self):
        response = urlopen(f"{self._base_url}/api/openapi", timeout=5)
        body = response.read().decode("utf-8")
        self.assertIn("openapi:", body)
        self.assertIn("/api/tasks", body)

    def test_api_key_required_for_mutations_when_set(self):
        original = server_module.API_KEY
        server_module.API_KEY = "secret-key"
        try:
            status, _ = self._request("POST", "/api/tasks", payload={"title": "No key"})
            self.assertEqual(status, 401)

            status, data = self._request(
                "POST",
                "/api/tasks",
                payload={"title": "With key"},
                headers={"X-API-Key": "secret-key"},
            )
            self.assertEqual(status, 201)
            self.assertEqual(data["task"]["title"], "With key")
        finally:
            server_module.API_KEY = original


if __name__ == "__main__":
    unittest.main()