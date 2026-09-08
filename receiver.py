#!/usr/bin/env python3
"""Test-mottaker for fake edge-agent.

Liten HTTP-server (kun stdlib) som tar imot POST fra agent.py, lagrer bildet
under received/ og skriver GPS-dataene til konsollen. Bytt den ut med den
ekte backend-URL-en nar den finnes.

Bruk:
    python receiver.py --port 8000
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from email.parser import BytesParser
from email.policy import default as default_policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "received"


def parse_multipart(content_type: str, body: bytes) -> tuple[dict[str, str], list[tuple[str, bytes]]]:
    """Del opp multipart-body i tekstfelter og filer."""
    message = BytesParser(policy=default_policy).parsebytes(
        b"Content-Type: " + content_type.encode() + b"\r\nMIME-Version: 1.0\r\n\r\n" + body
    )

    fields: dict[str, str] = {}
    files: list[tuple[str, bytes]] = []
    for part in message.iter_parts():
        filename = part.get_filename()
        payload = part.get_payload(decode=True) or b""
        if filename:
            files.append((filename, payload))
        else:
            name = part.get_param("name", header="content-disposition")
            if name:
                fields[name] = payload.decode("utf-8", "replace")
    return fields, files


class IngestHandler(BaseHTTPRequestHandler):
    server_version = "SharkDroneTestReceiver/1.0"

    def do_POST(self) -> None:  # noqa: N802 - navnet er gitt av stdlib
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        content_type = self.headers.get("Content-Type", "")

        try:
            fields, files = parse_multipart(content_type, body)
        except Exception as exc:  # noqa: BLE001 - testverktoy, vil bare se feilen
            self._respond(400, {"error": f"kunne ikke lese multipart: {exc}"})
            return

        OUTPUT_DIR.mkdir(exist_ok=True)
        saved: list[str] = []
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        for index, (filename, data) in enumerate(files):
            target = OUTPUT_DIR / f"{stamp}-{fields.get('frame_id', index)}-{filename}"
            target.write_bytes(data)
            saved.append(target.name)

        print(f"[{stamp}] mottatt {fields.get('device_id', '?')} "
              f"lat={fields.get('lat')} lon={fields.get('lon')} "
              f"alt={fields.get('altitude_m')}m -> {', '.join(saved) or 'ingen fil'}",
              flush=True)

        self._respond(200, {"status": "ok", "saved": saved})

    def do_GET(self) -> None:  # noqa: N802
        self._respond(200, {"status": "ok", "hint": "POST multipart til /ingest"})

    def _respond(self, status: int, payload: dict) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args) -> None:
        pass  # Vi skriver var egen, kortere logglinje i do_POST.


def main() -> int:
    parser = argparse.ArgumentParser(description="Test-mottaker for fake edge-agent")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), IngestHandler)
    print(f"Mottaker lytter pa http://{args.host}:{args.port}/ingest "
          f"(lagrer i {OUTPUT_DIR}/) - Ctrl+C for a stoppe")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStoppet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
