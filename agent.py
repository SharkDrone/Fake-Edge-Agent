#!/usr/bin/env python3
"""Fake edge-agent for SharkDrone.

Sends a random image from a folder plus fake GPS to a URL at a fixed
interval. No AI involved - this is only the transport half of the pipeline.

Usage:
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
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}

# Burleigh Beach, Gold Coast QLD. The anchor sits on the waterline near the
# surf club; the patrol area is defined relative to it. Override with
# --lat / --lon / --shore-bearing to fly a different beach.
DEFAULT_LAT = -28.0890
DEFAULT_LON = 153.4520

# Compass bearing of the coastline heading north along the beach. The open
# water is 90 degrees clockwise from this, i.e. roughly east-north-east.
DEFAULT_SHORE_BEARING = 339.0

# Patrol box in metres, measured in the coastline frame: how far along the
# beach from the anchor, and how far out to sea. The lower offshore bound is
# what keeps the drone off the sand.
ALONGSHORE_RANGE_M = (-200.0, 1500.0)
OFFSHORE_RANGE_M = (80.0, 600.0)

METRES_PER_DEGREE = 111_320.0


def find_images(folder: Path) -> list[Path]:
    """Return every image file directly inside the folder (not recursive)."""
    return sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
    )


class OverWaterPatrol:
    """Random walk constrained to the water off the beach.

    Positions are generated in a local metre frame rotated onto the coastline:
    `along` runs parallel to the beach, `across` points straight out to sea.
    Wandering in that frame and bouncing off the edges of the patrol box keeps
    every fix over water, which a plain lat/lon random walk cannot guarantee -
    it would eventually drift onto the sand.
    """

    def __init__(self, anchor_lat: float, anchor_lon: float,
                 shore_bearing_deg: float = DEFAULT_SHORE_BEARING,
                 speed_mps: float = 6.0, altitude_m: float = 50.0) -> None:
        self.anchor_lat = anchor_lat
        self.anchor_lon = anchor_lon
        self.shore_bearing = math.radians(shore_bearing_deg)
        self.speed_mps = speed_mps
        self.altitude_m = altitude_m

        # Start somewhere random inside the patrol box, on a random course.
        self.along = random.uniform(*ALONGSHORE_RANGE_M)
        self.across = random.uniform(*OFFSHORE_RANGE_M)
        self.course = random.uniform(0.0, 360.0)

    def step(self, seconds: float) -> dict:
        # Turn slightly on every step, then run along the new course.
        self.course = (self.course + random.uniform(-25.0, 25.0)) % 360.0
        distance = self.speed_mps * seconds * random.uniform(0.6, 1.4)
        rad = math.radians(self.course)
        self.along += distance * math.cos(rad)
        self.across += distance * math.sin(rad)
        self._bounce_off_edges()

        lat, lon = self._to_latlon()
        return {
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "altitude_m": round(self.altitude_m + random.uniform(-4.0, 4.0), 1),
            "heading_deg": round(self._true_heading(), 1),
            "speed_mps": round(self.speed_mps, 2),
            "accuracy_m": round(random.uniform(1.5, 6.0), 1),
            "offshore_m": round(self.across, 1),
        }

    def _bounce_off_edges(self) -> None:
        """Reflect off the patrol box instead of leaving it."""
        low, high = ALONGSHORE_RANGE_M
        if not low <= self.along <= high:
            self.along = min(max(self.along, low), high)
            # Mirror the course about the offshore axis.
            self.course = (180.0 - self.course) % 360.0

        low, high = OFFSHORE_RANGE_M
        if not low <= self.across <= high:
            self.across = min(max(self.across, low), high)
            # Mirror the course about the alongshore axis.
            self.course = -self.course % 360.0

    def _to_latlon(self) -> tuple[float, float]:
        """Rotate the local metre frame back onto true north/east."""
        bearing = self.shore_bearing
        north = self.along * math.cos(bearing) - self.across * math.sin(bearing)
        east = self.along * math.sin(bearing) + self.across * math.cos(bearing)

        lat = self.anchor_lat + north / METRES_PER_DEGREE
        lon = self.anchor_lon + east / (METRES_PER_DEGREE * math.cos(math.radians(lat)))
        return lat, lon

    def _true_heading(self) -> float:
        """Course in the local frame expressed as a compass bearing."""
        return (math.degrees(self.shore_bearing) + self.course) % 360.0


def build_payload(device_id: str, position: dict, image_path: Path) -> dict:
    """Build the form fields that accompany the image."""
    return {
        "device_id": device_id,
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "frame_id": uuid.uuid4().hex[:12],
        **position,
        # The same data bundled as JSON, for receivers that prefer one field.
        "metadata": json.dumps({"device_id": device_id, **position}),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fake edge-agent for SharkDrone")
    parser.add_argument("--url", default="http://localhost:8000/ingest",
                        help="URL that the image + GPS is posted to")
    parser.add_argument("--images-dir", type=Path, default=Path(__file__).parent / "images",
                        help="Folder holding the images to send")
    parser.add_argument("--interval", type=float, default=10.0,
                        help="Seconds between sends (default: 10)")
    parser.add_argument("--count", type=int, default=0,
                        help="Number of sends, 0 = run until Ctrl+C")
    parser.add_argument("--device-id", default="drone-001", help="Identifier for this 'drone'")
    parser.add_argument("--lat", type=float, default=DEFAULT_LAT,
                        help="Latitude of the shoreline anchor")
    parser.add_argument("--lon", type=float, default=DEFAULT_LON,
                        help="Longitude of the shoreline anchor")
    parser.add_argument("--shore-bearing", type=float, default=DEFAULT_SHORE_BEARING,
                        help="Compass bearing of the coastline; water lies 90 deg clockwise")
    parser.add_argument("--altitude", type=float, default=50.0,
                        help="Nominal flight altitude in metres")
    parser.add_argument("--speed", type=float, default=6.0,
                        help="Patrol speed in metres per second")
    parser.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout in seconds")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if not args.images_dir.is_dir():
        print(f"ERROR: image folder not found: {args.images_dir}", file=sys.stderr)
        return 1

    images = find_images(args.images_dir)
    if not images:
        print(f"ERROR: no images in {args.images_dir}", file=sys.stderr)
        return 1

    gps = OverWaterPatrol(args.lat, args.lon, args.shore_bearing,
                          speed_mps=args.speed, altitude_m=args.altitude)
    print(f"Fake edge-agent starting: {len(images)} images -> {args.url} "
          f"every {args.interval:g}s (Ctrl+C to stop)")

    sent = 0
    failed = 0
    # One session keeps the TCP connection alive between sends.
    with requests.Session() as session:
        session.headers["User-Agent"] = "sharkdrone-fake-edge-agent/1.0"
        try:
            while args.count == 0 or sent + failed < args.count:
                image = random.choice(images)
                position = gps.step(args.interval)
                fields = build_payload(args.device_id, position, image)
                content_type = mimetypes.guess_type(image.name)[0] or "application/octet-stream"

                try:
                    with image.open("rb") as handle:
                        response = session.post(
                            args.url,
                            data=fields,
                            files={"image": (image.name, handle, content_type)},
                            timeout=args.timeout,
                        )
                    response.raise_for_status()
                    sent += 1
                    print(f"sent  #{sent}  {image.name}  "
                          f"{position['lat']},{position['lon']}  "
                          f"{image.stat().st_size / 1024:.0f} kB  "
                          f"-> HTTP {response.status_code} {response.text.strip()[:80]}")
                except requests.RequestException as exc:
                    failed += 1
                    print(f"FAIL  {image.name} -> {exc}", file=sys.stderr)

                if args.count and sent + failed >= args.count:
                    break
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print()

    print(f"Stopped. {sent} sent, {failed} failed.")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
