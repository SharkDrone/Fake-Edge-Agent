#!/usr/bin/env python3
"""Fake edge-agent for SharkDrone.

Sender et tilfeldig bilde fra en mappe + falsk GPS til en URL med jevne
mellomrom. Ingen AI, ingen tredjepartspakker - kun Python stdlib.

Bruk:
    python agent.py --url http://localhost:8000/ingest
"""

from __future__ import annotations

import argparse
import json
import math
import mimetypes
import random
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}

# Startpunkt: Oslofjorden. Overstyres med --lat / --lon.
DEFAULT_LAT = 59.8940
DEFAULT_LON = 10.6180


def find_images(folder: Path) -> list[Path]:
    """Alle bildefiler i mappen (ikke rekursivt)."""
    return sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
    )


class FakeGPS:
    """Enkel random walk rundt et startpunkt, slik at sporet ser troverdig ut."""

    def __init__(self, lat: float, lon: float, speed_mps: float = 3.0) -> None:
        self.lat = lat
        self.lon = lon
        self.speed_mps = speed_mps
        self.heading = random.uniform(0, 360)

    def step(self, seconds: float) -> dict:
        # Sving litt for hvert steg, og flytt deg i den nye retningen.
        self.heading = (self.heading + random.uniform(-25, 25)) % 360
        distance = self.speed_mps * seconds * random.uniform(0.6, 1.4)
        rad = math.radians(self.heading)

        # ~111 320 m per breddegrad; lengdegrader krymper mot polene.
        self.lat += (distance * math.cos(rad)) / 111_320.0
        self.lon += (distance * math.sin(rad)) / (
            111_320.0 * math.cos(math.radians(self.lat))
        )

        return {
            "lat": round(self.lat, 6),
            "lon": round(self.lon, 6),
            "altitude_m": round(random.uniform(15.0, 45.0), 1),
            "heading_deg": round(self.heading, 1),
            "speed_mps": round(self.speed_mps, 2),
            "accuracy_m": round(random.uniform(1.5, 6.0), 1),
        }


def build_multipart(fields: dict[str, str], image_path: Path) -> tuple[bytes, str]:
    """Bygg en multipart/form-data-body: metadatafelter + selve bildet."""
    boundary = f"----sharkdrone{uuid.uuid4().hex}"
    crlf = b"\r\n"
    parts: list[bytes] = []

    for name, value in fields.items():
        parts += [
            f"--{boundary}".encode(),
            f'Content-Disposition: form-data; name="{name}"'.encode(),
            b"",
            str(value).encode("utf-8"),
        ]

    content_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    parts += [
        f"--{boundary}".encode(),
        f'Content-Disposition: form-data; name="image"; filename="{image_path.name}"'.encode(),
        f"Content-Type: {content_type}".encode(),
        b"",
    ]

    body = crlf.join(parts) + crlf + image_path.read_bytes() + crlf
    body += f"--{boundary}--".encode() + crlf
    return body, f"multipart/form-data; boundary={boundary}"


def send(url: str, body: bytes, content_type: str, timeout: float) -> tuple[int, str]:
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": content_type, "User-Agent": "sharkdrone-fake-edge-agent/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, response.read(500).decode("utf-8", "replace").strip()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fake edge-agent for SharkDrone")
    parser.add_argument("--url", default="http://localhost:8000/ingest",
                        help="URL som bilde + GPS postes til")
    parser.add_argument("--images-dir", type=Path, default=Path(__file__).parent / "images",
                        help="Mappe med bilder som skal sendes")
    parser.add_argument("--interval", type=float, default=10.0,
                        help="Sekunder mellom hver sending (standard: 10)")
    parser.add_argument("--count", type=int, default=0,
                        help="Antall sendinger, 0 = kjor til Ctrl+C")
    parser.add_argument("--device-id", default="drone-001", help="Id for denne 'dronen'")
    parser.add_argument("--lat", type=float, default=DEFAULT_LAT, help="Start-breddegrad")
    parser.add_argument("--lon", type=float, default=DEFAULT_LON, help="Start-lengdegrad")
    parser.add_argument("--timeout", type=float, default=15.0, help="HTTP-timeout i sekunder")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if not args.images_dir.is_dir():
        print(f"FEIL: finner ikke bildemappen {args.images_dir}", file=sys.stderr)
        return 1

    images = find_images(args.images_dir)
    if not images:
        print(f"FEIL: ingen bilder i {args.images_dir}", file=sys.stderr)
        print("      Lag noen testbilder: python tools/make_sample_images.py", file=sys.stderr)
        return 1

    gps = FakeGPS(args.lat, args.lon)
    print(f"Fake edge-agent starter: {len(images)} bilder -> {args.url} "
          f"hvert {args.interval:g}. sekund (Ctrl+C for a stoppe)")

    sent = 0
    failed = 0
    try:
        while args.count == 0 or sent + failed < args.count:
            image = random.choice(images)
            position = gps.step(args.interval)
            fields = {
                "device_id": args.device_id,
                "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "frame_id": uuid.uuid4().hex[:12],
                **{k: v for k, v in position.items()},
                # Samme data samlet som JSON, for mottakere som foretrekker det.
                "metadata": json.dumps({"device_id": args.device_id, **position}),
            }

            body, content_type = build_multipart(fields, image)
            try:
                status, preview = send(args.url, body, content_type, args.timeout)
                sent += 1
                print(f"sendt  #{sent}  {image.name}  "
                      f"{position['lat']},{position['lon']}  "
                      f"{len(body) / 1024:.0f} kB  -> HTTP {status} {preview[:80]}")
            except urllib.error.HTTPError as exc:
                failed += 1
                print(f"FEIL   {image.name} -> HTTP {exc.code} {exc.reason}", file=sys.stderr)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                failed += 1
                print(f"FEIL   {image.name} -> {exc}", file=sys.stderr)

            if args.count and sent + failed >= args.count:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print()

    print(f"Stoppet. {sent} sendt, {failed} feilet.")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
