"""Small dependency-free web app for the GitOps delivery exercise."""

import html
import json
import os
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


VERSION = os.getenv("APP_VERSION", "dev")
COMMIT = os.getenv("GIT_COMMIT", "unknown")
POD = os.getenv("POD_NAME", socket.gethostname())
PORT = int(os.getenv("PORT", "8080"))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz":
            body = b"ok\n"
            content_type = "text/plain; charset=utf-8"
        elif self.path == "/api/info":
            body = json.dumps(
                {"version": VERSION, "commit": COMMIT, "pod": POD},
                ensure_ascii=False,
            ).encode("utf-8")
            content_type = "application/json; charset=utf-8"
        elif self.path == "/":
            body = (
                "<!doctype html><html lang='zh-CN'><meta charset='utf-8'>"
                "<meta name='viewport' content='width=device-width, initial-scale=1'>"
                "<title>GitOps Demo</title>"
                "<style>body{font-family:system-ui,sans-serif;max-width:44rem;"
                "margin:4rem auto;padding:0 1rem;line-height:1.7}"
                "code{background:#eef;padding:.2rem .4rem;border-radius:.3rem}</style>"
                "<h1>GitOps Demo</h1>"
                "<p>新版本先在 lab 验证，再经 MR 发布到 staging。</p>"
                f"<p>版本：<code>{html.escape(VERSION)}</code></p>"
                f"<p>Git commit：<code>{html.escape(COMMIT)}</code></p>"
                f"<p>运行 Pod：<code>{html.escape(POD)}</code></p>"
                "<p><a href='/api/info'>查看 JSON</a> · "
                "<a href='/healthz'>健康检查</a></p></html>"
            ).encode("utf-8")
            content_type = "text/html; charset=utf-8"
        else:
            self.send_error(404, "Not Found")
            return

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
