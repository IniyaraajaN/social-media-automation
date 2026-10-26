"""Serve a small local dashboard for the social reporting demo."""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from src.ai_analyzer import AnalysisAPIError, InputValidationError, analyze_post
from src.report import (
    DEFAULT_DATA,
    DEFAULT_OUTPUT,
    Window,
    engagement_rate,
    get_windows,
    load_demo_posts,
    summarize,
)


ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"
HOST = "127.0.0.1"
PORT = 8765


def period_posts(posts: list[dict[str, Any]], window: Window) -> list[dict[str, Any]]:
    return [
        post
        for post in posts
        if window.start.isoformat() <= post["published_at"] <= window.end.isoformat()
    ]


def ollama_status() -> dict[str, Any]:
    request = urllib.request.Request("http://127.0.0.1:11434/api/tags")
    try:
        with urllib.request.urlopen(request, timeout=1.5) as response:
            data = json.loads(response.read().decode("utf-8"))
        models = [item.get("name", "") for item in data.get("models", [])]
        return {"running": True, "models": models}
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return {"running": False, "models": []}


def dashboard_data() -> dict[str, Any]:
    as_of = date.today()
    posts = load_demo_posts(DEFAULT_DATA, as_of)
    current_window, previous_window = get_windows(as_of)
    current_posts = period_posts(posts, current_window)
    previous_posts = period_posts(posts, previous_window)
    top_posts = sorted(
        current_posts,
        key=lambda post: (engagement_rate(post), post["reach"]),
        reverse=True,
    )[:3]
    return {
        "as_of": as_of.isoformat(),
        "current_period": current_window.label(),
        "previous_period": previous_window.label(),
        "current": summarize(current_posts),
        "previous": summarize(previous_posts),
        "top_posts": [
            {
                "post_id": post["post_id"],
                "published_at": post["published_at"],
                "post_type": post["post_type"].replace("_ALBUM", ""),
                "caption": post["caption"],
                "reach": post["reach"],
                "interactions": post["likes"] + post["comments"] + post["shares"] + post["saves"],
                "engagement_rate": engagement_rate(post),
            }
            for post in top_posts
        ],
        "ollama": ollama_status(),
        "report_available": DEFAULT_OUTPUT.exists(),
    }


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "SocialMediaDashboard/1.0"

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path, content_type: str) -> None:
        if not path.is_file():
            self.send_error(404, "File not found")
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        route = self.path.split("?", 1)[0]
        if route == "/" or route == "/index.html":
            self._file(WEB_DIR / "index.html", "text/html; charset=utf-8")
        elif route == "/api/dashboard":
            try:
                self._json(200, dashboard_data())
            except Exception as exc:
                self._json(500, {"error": f"Could not load dashboard data: {exc}"})
        elif route == "/output/report.pdf":
            self._file(DEFAULT_OUTPUT, "application/pdf")
        elif route == "/output/report-preview.png":
            self._file(ROOT / "output" / "report_preview.png", "image/png")
        else:
            self.send_error(404, "Not found")

    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        route = self.path.split("?", 1)[0]
        if route == "/api/analyze-top-post":
            self._analyze_top_post()
        elif route == "/api/generate-report":
            self._generate_report()
        else:
            self.send_error(404, "Not found")

    def _analyze_top_post(self) -> None:
        try:
            data = dashboard_data()
            if not data["top_posts"]:
                self._json(400, {"error": "There are no posts in the current reporting period."})
                return
            post_id = data["top_posts"][0]["post_id"]
            posts = load_demo_posts(DEFAULT_DATA, date.fromisoformat(data["as_of"]))
            post = next(item for item in posts if item["post_id"] == post_id)
            result = analyze_post(
                {
                    "caption": post["caption"],
                    "post_type": post["post_type"],
                    "metrics": {
                        key: post[key]
                        for key in ("reach", "likes", "comments", "shares", "saves")
                    },
                }
            )
            result["post_caption"] = post["caption"]
            self._json(200, result)
        except (AnalysisAPIError, InputValidationError) as exc:
            self._json(503, {"error": str(exc)})
        except Exception as exc:
            self._json(500, {"error": f"Could not analyze the top post: {exc}"})

    def _generate_report(self) -> None:
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "src.report"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
        except subprocess.TimeoutExpired:
            self._json(504, {"error": "Report generation took too long. Check that Ollama is running."})
            return
        if completed.returncode:
            self._json(500, {"error": completed.stderr.strip() or "Report generation failed."})
            return
        self._json(200, {"message": "Report generated.", "log": completed.stdout.strip(), "pdf_url": "/output/report.pdf"})

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[dashboard] {self.address_string()} - {format % args}")


def main() -> None:
    if not (WEB_DIR / "index.html").is_file():
        raise SystemExit(f"Dashboard page not found: {WEB_DIR / 'index.html'}")
    server = ThreadingHTTPServer((HOST, PORT), DashboardHandler)
    print(f"Social Media dashboard running at http://{HOST}:{PORT}")
    print("Press Ctrl+C to stop the dashboard.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
