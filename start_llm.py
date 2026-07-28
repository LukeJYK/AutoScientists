#!/usr/bin/env python3
"""Launch a local vLLM server as the LLM backend for AutoScientists agents.

Run this on the machine with the GPU (e.g. your A100 node on Discover), not
on a CUDA-less laptop. Once it's up, point Claude Code at it:

    export ANTHROPIC_BASE_URL=http://<host>:<port>
    export ANTHROPIC_AUTH_TOKEN=local
    export CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING=1
"""
import argparse
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

DEFAULT_MODEL = os.environ.get("VLLM_MODEL", "/projects/jiangyank/models/Qwen3-Coder-30B-A3B-Instruct/")


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--served-model-name", default=None,
                   help="name clients must use in the 'model' field (default: basename of --model)")
    p.add_argument("--host", default="127.0.0.1",
                   help="0.0.0.0 exposes the server on the network with no auth by default — "
                        "only widen this if you also set --api-key")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--api-key", default=None,
                   help="require this bearer token for requests — strongly recommended if --host is not 127.0.0.1")
    p.add_argument("--max-model-len", type=int, default=131072,
                   help="Claude Code's own system prompt + tool schemas alone can run ~30k tokens, "
                        "so this needs real headroom beyond your task content")
    p.add_argument("--max-num-seqs", type=int, default=16,
                   help="max concurrent sequences — set >= number of agents you'll run in parallel")
    p.add_argument("--gpu-memory-utilization", type=float, default=0.90)
    p.add_argument("--no-prefix-caching", action="store_true",
                   help="disable KV-cache reuse across requests sharing the same system prompt")
    p.add_argument("--tool-call-parser", default="qwen3_coder",
                    help="vLLM tool-call parser matching your model family — required for Claude Code's tool use")
    p.add_argument("--no-auto-tool-choice", action="store_true",
                    help="disable --enable-auto-tool-choice (Claude Code needs this on to call tools at all)")
    return p.parse_args()


def wait_for_server(display_host, port, timeout=1800):
    url = f"http://{display_host}:{port}/v1/models"
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionResetError, TimeoutError):
            pass
        time.sleep(3)
    return False


def main():
    args = parse_args()

    if shutil.which("vllm") is None:
        sys.exit("vllm CLI not found on PATH. Install it first: pip install vllm")

    served_name = args.served_model_name or os.path.basename(os.path.normpath(args.model))

    cmd = [
        "vllm", "serve", args.model,
        "--served-model-name", served_name,
        "--host", args.host,
        "--port", str(args.port),
        "--max-model-len", str(args.max_model_len),
        "--max-num-seqs", str(args.max_num_seqs),
        "--gpu-memory-utilization", str(args.gpu_memory_utilization),
    ]
    if not args.no_prefix_caching:
        cmd.append("--enable-prefix-caching")
    if not args.no_auto_tool_choice:
        cmd += ["--enable-auto-tool-choice", "--tool-call-parser", args.tool_call_parser]
    if args.api_key:
        cmd += ["--api-key", args.api_key]
    elif args.host != "127.0.0.1":
        print("WARNING: binding to a non-loopback host with no --api-key — "
              "the model will be reachable by anyone who can route to this address.")

    print(f"Launching: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd)

    display_host = "localhost" if args.host in ("0.0.0.0", "127.0.0.1") else args.host
    base_url = f"http://{display_host}:{args.port}"

    try:
        print("Waiting for server to become ready...")
        if wait_for_server(display_host, args.port):
            print(f"\nServer ready at {base_url}")
            print(f"Served model name (use this in the 'model' field): {served_name}")
            print("Point Claude Code at it with:")
            print(f"  export ANTHROPIC_BASE_URL={base_url}")
            print("  export ANTHROPIC_AUTH_TOKEN=local")
            print("  export CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING=1")
            print("\n(If your vLLM build doesn't expose /v1/messages natively, you'll need a")
            print(" translation proxy in front of this server instead of pointing Claude Code")
            print(" directly at it — check `vllm serve --help` for Anthropic-API-related flags.)")
        else:
            print("Server did not become ready within timeout — check the vllm output above for errors.")
        proc.wait()
    except KeyboardInterrupt:
        print("\nShutting down vLLM server...")
        proc.terminate()
        proc.wait()


if __name__ == "__main__":
    main()
