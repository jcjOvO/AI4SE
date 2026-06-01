"""Tiny stdlib HTTP server that mimics the Anthropic /v1/messages SSE endpoint.

Used by the E2E test to verify the agent loop end-to-end without a real key.
"""

from __future__ import annotations

import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

# Each event is one logical "event: ...\ndata: ...\n\n" record. We keep
# them as separate string literals and join with empty separator so that
# each line stays short and ruff's line-length check (E501) is satisfied.
_SSE_EVENTS = [
    "event: message_start\n"
    'data: {"type":"message_start","message":{'
    '"id":"m","role":"assistant","content":[],'
    '"stop_reason":null,"usage":{'
    '"input_tokens":1,"output_tokens":0}}}\n\n',
    "event: content_block_start\n"
    'data: {"type":"content_block_start","index":0,'
    '"content_block":{"type":"text","text":""}}\n\n',
    "event: content_block_delta\n"
    'data: {"type":"content_block_delta","index":0,'
    '"delta":{"type":"text_delta",'
    '"text":"Hello from mock LLM!"}}\n\n',
    'event: content_block_stop\ndata: {"type":"content_block_stop","index":0}\n\n',
    'event: message_delta\ndata: {"type":"message_delta","delta":{"stop_reason":"end_turn"}}\n\n',
    'event: message_stop\ndata: {"type":"message_stop"}\n\n',
]
SSE = "".join(_SSE_EVENTS)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/v1/messages":
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.end_headers()
            self.wfile.write(SSE.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args, **kwargs) -> None:  # silence
        pass


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    server = HTTPServer(("127.0.0.1", port), Handler)
    print(f"mock-anthropic listening on http://127.0.0.1:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
