#!/usr/bin/env python3
"""Logging reverse proxy: dumps every request body before forwarding to vLLM.

Run vLLM as usual on its normal port (default 8000), then run this proxy on a
different port and point Claude Code at the PROXY instead of vLLM directly:

    python3 debug_proxy.py --upstream http://127.0.0.1:8000 --port 8001
    export ANTHROPIC_BASE_URL=http://127.0.0.1:8001

Every request body gets printed to stdout (and saved to requests.log) before
being forwarded upstream unchanged, so you can see exactly what Claude Code
is sending.
"""
import argparse
import http.server
import json

import requests

HOP_BY_HOP = {"content-length", "transfer-encoding", "connection", "host"}


def make_handler(upstream, log_path):
    class LoggingProxy(http.server.BaseHTTPRequestHandler):
        def _forward(self, method):
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b""

            if body:
                try:
                    parsed = json.loads(body)
                    dump = json.dumps(parsed, indent=2, ensure_ascii=False)
                except Exception:
                    dump = body.decode(errors="replace")
                entry = f"\n=== {method} {self.path} ===\n{dump}\n"
                print(entry)
                with open(log_path, "a") as f:
                    f.write(entry)

            fwd_headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP_BY_HOP}
            resp = requests.request(method, upstream + self.path, data=body,
                                     headers=fwd_headers, stream=True, timeout=600)

            self.send_response(resp.status_code)
            for k, v in resp.headers.items():
                if k.lower() not in HOP_BY_HOP:
                    self.send_header(k, v)
            self.end_headers()
            for chunk in resp.iter_content(chunk_size=4096):
                if chunk:
                    self.wfile.write(chunk)

        def do_POST(self):
            self._forward("POST")

        def do_GET(self):
            self._forward("GET")

        def log_message(self, fmt, *args):
            pass  # quiet the default per-request access log; we print our own

    return LoggingProxy


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--upstream", default="http://127.0.0.1:8000")
    p.add_argument("--port", type=int, default=8001)
    p.add_argument("--log-file", default="requests.log")
    args = p.parse_args()

    handler = make_handler(args.upstream, args.log_file)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"Logging proxy on http://127.0.0.1:{args.port} -> {args.upstream}")
    print(f"Also writing every request body to {args.log_file}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
