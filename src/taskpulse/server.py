from __future__ import annotations

import json
import mimetypes
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .store import TaskStore, create_default_store


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = PROJECT_ROOT / "web"
TASK_ROUTE = re.compile(r"^/api/tasks/(?P<task_id>\d+)$")


class TaskPulseHandler(BaseHTTPRequestHandler):
    store: TaskStore = create_default_store()

    def do_GET(self) -> None:
        path = urlparse(self.path).path

        if path == "/api/health":
            self.send_json({"status": "ok", "service": "taskpulse"})
            return

        if path == "/api/tasks":
            self.send_json({"tasks": self.store.list_tasks()})
            return

        if path == "/api/stats":
            self.send_json({"stats": self.store.get_stats()})
            return

        self.serve_static(path)

    def do_POST(self) -> None:
        path = urlparse(self.path).path

        if path != "/api/tasks":
            self.send_error(HTTPStatus.NOT_FOUND, "Route not found.")
            return

        try:
            payload = self.read_json()
            task = self.store.add_task(
                title=str(payload.get("title", "")),
                owner=str(payload.get("owner", "Unassigned")),
                priority=str(payload.get("priority", "medium")),
                minutes=int(payload.get("minutes", 25)),
            )
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        self.send_json({"task": task}, status=HTTPStatus.CREATED)

    def do_PATCH(self) -> None:
        path = urlparse(self.path).path
        match = TASK_ROUTE.match(path)

        if not match:
            self.send_error(HTTPStatus.NOT_FOUND, "Route not found.")
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

        self.send_json({"task": task})

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path
        match = TASK_ROUTE.match(path)

        if not match:
            self.send_error(HTTPStatus.NOT_FOUND, "Route not found.")
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

        self.send_json({"task": task})

    def read_json(self) -> dict[str, object]:
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