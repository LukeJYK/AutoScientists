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
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--max-model-len", type=int, default=32768)
    p.add_argument("--max-num-seqs", type=int, default=16,
                   help="max concurrent sequences — set >= number of agents you'll run in parallel")
    p.add_argument("--gpu-memory-utilization", type=float, default=0.90)
    p.add_argument("--no-prefix-caching", action="store_true",
                   help="disable KV-cache reuse across requests sharing the same system prompt")
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

    cmd = [
        "vllm", "serve", args.model,
        "--host", args.host,
        "--port", str(args.port),
        "--max-model-len", str(args.max_model_len),
        "--max-num-seqs", str(args.max_num_seqs),
        "--gpu-memory-utilization", str(args.gpu_memory_utilization),
    ]
    if not args.no_prefix_caching:
        cmd.append("--enable-prefix-caching")

    print(f"Launching: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd)

    display_host = "localhost" if args.host == "0.0.0.0" else args.host
    base_url = f"http://{display_host}:{args.port}"

    try:
        print("Waiting for server to become ready...")
        if wait_for_server(display_host, args.port):
            print(f"\nServer ready at {base_url}")
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
