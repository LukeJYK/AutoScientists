#!/usr/bin/env python3
"""Logging reverse proxy: records per-request token usage for every Claude
Code <-> vLLM exchange, then forwards the response unchanged.

Run vLLM as usual, then run this proxy on a different port and point Claude
Code at the PROXY instead of vLLM directly:

    python3 token_logger.py --upstream http://127.0.0.1:8000 --port 8001
    export ANTHROPIC_BASE_URL=http://127.0.0.1:8001

Each request's usage (input/output tokens, plus cache_creation/cache_read if
the backend reports them) gets appended as one JSON line to usage.jsonl.
Handles both streaming (SSE) and non-streaming responses.
"""
import argparse
import http.server
import json
import time

import requests

HOP_BY_HOP = {"content-length", "transfer-encoding", "connection", "host"}


def _extract_usage_from_event(data_line, usage_acc):
    try:
        payload = json.loads(data_line)
    except Exception:
        return
    ev_type = payload.get("type")
    if ev_type == "message_start":
        u = payload.get("message", {}).get("usage", {})
        usage_acc.update({k: v for k, v in u.items() if v is not None})
    elif ev_type == "message_delta":
        u = payload.get("usage", {})
        usage_acc.update({k: v for k, v in u.items() if v is not None})


def make_handler(upstream, log_path):
    class TokenLoggingProxy(http.server.BaseHTTPRequestHandler):
        def _log_usage(self, path, usage):
            if not usage:
                return
            entry = {"ts": time.time(), "path": path, **usage}
            print(f"usage: {entry}")
            with open(log_path, "a") as f:
                f.write(json.dumps(entry) + "\n")

        def _forward(self, method):
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b""
            fwd_headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP_BY_HOP}

            resp = requests.request(method, upstream + self.path, data=body,
                                     headers=fwd_headers, stream=True, timeout=600)

            self.send_response(resp.status_code)
            for k, v in resp.headers.items():
                if k.lower() not in HOP_BY_HOP:
                    self.send_header(k, v)
            self.end_headers()

            content_type = resp.headers.get("content-type", "")
            usage_acc = {}

            if "text/event-stream" in content_type:
                buf = b""
                for chunk in resp.iter_content(chunk_size=1024):
                    if not chunk:
                        continue
                    self.wfile.write(chunk)
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        line = line.decode(errors="replace").strip()
                        if line.startswith("data:"):
                            _extract_usage_from_event(line[len("data:"):].strip(), usage_acc)
                self._log_usage(self.path, usage_acc)
            else:
                raw = resp.content
                self.wfile.write(raw)
                try:
                    payload = json.loads(raw)
                    usage_acc = payload.get("usage", {}) or {}
                except Exception:
                    pass
                self._log_usage(self.path, usage_acc)

        def do_POST(self):
            self._forward("POST")

        def do_GET(self):
            self._forward("GET")

        def log_message(self, fmt, *args):
            pass

    return TokenLoggingProxy


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--upstream", default="http://127.0.0.1:8000")
    p.add_argument("--port", type=int, default=8001)
    p.add_argument("--log-file", default="usage.jsonl")
    args = p.parse_args()

    handler = make_handler(args.upstream, args.log_file)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"Token-usage logging proxy on http://127.0.0.1:{args.port} -> {args.upstream}")
    print(f"Logging per-request usage to {args.log_file}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
