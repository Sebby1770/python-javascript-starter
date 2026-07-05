from __future__ import annotations

import json
import mimetypes
import os
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .nlp import parse_task_text
from .store import TaskStoreProtocol, create_store
from .websocket import WebSocketHub, handle_websocket_upgrade


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = PROJECT_ROOT / "web"
OPENAPI_PATH = PROJECT_ROOT / "openapi.yaml"
TASK_ROUTE = re.compile(r"^/api/tasks/(?P<task_id>\d+)$")
API_KEY = os.environ.get("API_KEY", "").strip() or None
WS_HUB = WebSocketHub()


class TaskPulseHandler(BaseHTTPRequestHandler):
    store: TaskStoreProtocol = create_store()

    def do_GET(self) -> None:
        path = urlparse(self.path).path

        if path == "/ws":
            if self.headers.get("Upgrade", "").lower() == "websocket":
                handle_websocket_upgrade(self, WS_HUB)
            else:
                self.send_error(HTTPStatus.BAD_REQUEST, "Expected WebSocket upgrade.")
            return

        if path == "/api/health":
            self.send_json({"status": "ok", "service": "taskpulse"})
            return

        if path == "/api/openapi":
            self.serve_openapi()
            return

        if path == "/api/tasks":
            self.send_json({"tasks": self.store.list_tasks()})
            return

        if path == "/api/tasks/export":
            self.export_tasks()
            return

        if path == "/api/stats":
            self.send_json({"stats": self.store.get_stats()})
            return

        self.serve_static(path)

    def do_POST(self) -> None:
        path = urlparse(self.path).path

        if path == "/api/tasks/import":
            if not self.require_api_key():
                return
            self.import_tasks()
            return

        if path == "/api/tasks/parse":
            if not self.require_api_key():
                return
            self.parse_task_input()
            return

        if path != "/api/tasks":
            self.send_error(HTTPStatus.NOT_FOUND, "Route not found.")
            return

        if not self.require_api_key():
            return

        try:
            payload = self.read_json()
            task = self.store.add_task(
                title=str(payload.get("title", "")),
                owner=str(payload.get("owner", "Unassigned")),
                priority=str(payload.get("priority", "medium")),
                minutes=int(payload.get("minutes", 25)),
                due_date=payload.get("due_date"),
                tags=payload.get("tags"),
                status=str(payload.get("status", "todo")),
                blocked_by=payload.get("blocked_by"),
                recurrence=payload.get("recurrence"),
            )
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        self.broadcast_change()
        self.send_json({"task": task}, status=HTTPStatus.CREATED)

    def do_PATCH(self) -> None:
        path = urlparse(self.path).path
        match = TASK_ROUTE.match(path)

        if not match:
            self.send_error(HTTPStatus.NOT_FOUND, "Route not found.")
            return

        if not self.require_api_key():
            return

        task_id = int(match.group("task_id"))

        try:
            payload = self.read_json()
            if not payload:
                task = self.store.toggle_task(task_id)
            else:
                task = self.store.update_task(task_id, payload)
        except KeyError:
            self.send_json(
                {"error": f"Task {task_id} not found."},
                status=HTTPStatus.NOT_FOUND,
            )
            return
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        self.broadcast_change()
        self.send_json({"task": task})

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path
        match = TASK_ROUTE.match(path)

        if not match:
            self.send_error(HTTPStatus.NOT_FOUND, "Route not found.")
            return

        if not self.require_api_key():
            return

        task_id = int(match.group("task_id"))

        try:
            task = self.store.delete_task(task_id)
        except KeyError:
            self.send_json(
                {"error": f"Task {task_id} not found."},
                status=HTTPStatus.NOT_FOUND,
            )
            return

        self.broadcast_change()
        self.send_json({"task": task})

    def require_api_key(self) -> bool:
        if API_KEY is None:
            return True

        provided = self.headers.get("X-API-Key", "").strip()
        if provided != API_KEY:
            self.send_json(
                {"error": "Invalid or missing API key."},
                status=HTTPStatus.UNAUTHORIZED,
            )
            return False
        return True

    def export_tasks(self) -> None:
        payload = json.dumps(self.store.list_tasks(), indent=2).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("content-type", "application/json")
        self.send_header("content-disposition", 'attachment; filename="tasks.json"')
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def parse_task_input(self) -> None:
        try:
            payload = self.read_json()
            text = str(payload.get("text", "")).strip()
            if not text:
                raise ValueError("text is required.")
            parsed = parse_task_text(text)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        self.send_json({"parsed": parsed})

    def import_tasks(self) -> None:
        try:
            payload = self.read_json()
            if not isinstance(payload, list):
                raise ValueError("Import payload must be a JSON array of tasks.")
            tasks = self.store.import_tasks(payload)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        self.broadcast_change()
        self.send_json({"tasks": tasks})

    def serve_openapi(self) -> None:
        if not OPENAPI_PATH.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "OpenAPI spec not found.")
            return

        data = OPENAPI_PATH.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("content-type", "application/yaml")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def broadcast_change(self) -> None:
        WS_HUB.broadcast(json.dumps({"event": "tasks_changed"}))

    def read_json(self) -> dict[str, object] | list[object]:
        content_length = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(content_length)
        if not body:
            return {}
        return json.loads(body.decode("utf-8"))

    def serve_static(self, path: str) -> None:
        requested = "index.html" if path == "/" else path.lstrip("/")
        file_path = (WEB_ROOT / requested).resolve()

        if WEB_ROOT.resolve() not in file_path.parents and file_path != WEB_ROOT.resolve():
            self.send_error(HTTPStatus.FORBIDDEN, "Invalid path.")
            return

        if not file_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "File not found.")
            return

        content_type, _ = mimetypes.guess_type(str(file_path))
        data = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("content-type", content_type or "application/octet-stream")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, data: dict[str, object], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def create_server(host: str = "127.0.0.1", port: int = 8000) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), TaskPulseHandler)


def main() -> None:
    TaskPulseHandler.store = create_store()
    server = create_server()
    host, port = server.server_address
    print(f"TaskPulse running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping TaskPulse.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()