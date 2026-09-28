"""Minimal QA-only reverse proxy that strips /smt/ before forwarding."""
from __future__ import annotations

import argparse
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


HOP_BY_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade"}


def handler_factory(upstream_host: str, upstream_port: int):
    class SubpathProxyHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _forward(self) -> None:
            if self.path == "/smt":
                self.send_response(308)
                self.send_header("Location", "/smt/")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if not self.path.startswith("/smt/"):
                body = b"QA proxy only serves /smt/"
                self.send_response(404)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            target = self.path[len("/smt"):] or "/"
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length) if length else None
            headers = {key: value for key, value in self.headers.items() if key.lower() not in HOP_BY_HOP | {"host", "content-length"}}
            headers["Host"] = f"{upstream_host}:{upstream_port}"
            headers["X-Forwarded-Prefix"] = "/smt"

            connection = http.client.HTTPConnection(upstream_host, upstream_port, timeout=180)
            try:
                connection.request(self.command, target, body=body, headers=headers)
                response = connection.getresponse()
                payload = response.read()
                self.send_response(response.status, response.reason)
                for key, value in response.getheaders():
                    if key.lower() not in HOP_BY_HOP | {"content-length"}:
                        self.send_header(key, value)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                if self.command != "HEAD":
                    try:
                        self.wfile.write(payload)
                    except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                        # Map renderers cancel obsolete tiles while the camera moves.
                        pass
            finally:
                connection.close()

        do_GET = _forward
        do_POST = _forward
        do_PUT = _forward
        do_PATCH = _forward
        do_DELETE = _forward
        do_HEAD = _forward

        def log_message(self, fmt: str, *args: object) -> None:
            print(f"SUBPATH QA {self.address_string()} {fmt % args}")

    return SubpathProxyHandler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, default=8804)
    parser.add_argument("--upstream-host", default="127.0.0.1")
    parser.add_argument("--upstream-port", type=int, default=8803)
    args = parser.parse_args()
    class QaThreadingHttpServer(ThreadingHTTPServer):
        daemon_threads = True
        request_queue_size = 128

    server = QaThreadingHttpServer((args.listen_host, args.listen_port), handler_factory(args.upstream_host, args.upstream_port))
    print(f"Subpath QA proxy http://{args.listen_host}:{args.listen_port}/smt/ -> http://{args.upstream_host}:{args.upstream_port}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
