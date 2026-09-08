# Fake Edge-Agent (SharkDrone, step 1)

A Python script that every 10 seconds sends a random image from `images/`
together with fake GPS to a URL. No AI - this is only the transport half of
the pipeline.

## Getting started

```bash
pip install -r requirements.txt
python receiver.py --port 8000                       # terminal 1: test receiver
python agent.py --url http://localhost:8000/ingest   # terminal 2: the agent
```

Put your images in `images/` (jpg, jpeg, png, webp, bmp, gif). The agent picks
one at random for every send and writes one line per successful send:

```
sent  #1  shark_04.jpg  -28.090008,153.451967  10 kB  -> HTTP 200 {"status": "ok", ...}
```

## agent.py

| Flag | Default | Description |
| --- | --- | --- |
| `--url` | `http://localhost:8000/ingest` | URL the image + GPS is posted to |
| `--images-dir` | `./images` | Folder holding the images to send |
| `--interval` | `10` | Seconds between sends |
| `--count` | `0` | Number of sends, 0 = run until Ctrl+C |
| `--device-id` | `drone-001` | Identifier for this "drone" |
| `--lat` / `--lon` | `-28.0890, 153.4520` | Shoreline anchor the patrol area hangs off |
| `--shore-bearing` | `339` | Compass bearing of the coastline; water is 90 deg clockwise |
| `--altitude` | `50` | Nominal flight altitude in metres |
| `--speed` | `6` | Patrol speed in metres per second |
| `--timeout` | `15` | HTTP timeout in seconds |

Exit code is 0 when everything went through, 2 if at least one send failed.

## What gets sent

A `POST` with `multipart/form-data`:

- `image` - the image file itself
- `device_id`, `captured_at` (UTC ISO-8601), `frame_id`
- `lat`, `lon`, `altitude_m`, `heading_deg`, `speed_mps`, `accuracy_m`, `offshore_m`
- `metadata` - the same GPS fields bundled as JSON, for receivers that prefer that

## Flight area

The drone patrols the water off Burleigh Beach, Gold Coast - it never flies
over the sand. Positions are generated in a local metre frame rotated onto the
coastline, so `along` runs parallel to the beach and `across` points straight
out to sea. The walk bounces off the edges of a patrol box:

- **80 - 600 m offshore** - the lower bound is what keeps it off the beach
- **1.7 km along the beach**, from just north of Burleigh Heads headland

A plain lat/lon random walk cannot promise this; given enough steps it drifts
onto land. Working in the rotated frame means the box follows the angle of the
coast for free.

The coordinates are approximate. Before you trust the track, paste a corner
into Google Maps and check it lands in the sea:

```
-28.09042, 153.45349      -28.07449, 153.45223
```

To move or reshape the area, use `--lat` / `--lon` (shoreline anchor) and
`--shore-bearing`, or edit `ALONGSHORE_RANGE_M` / `OFFSHORE_RANGE_M` in
[agent.py](agent.py).

## receiver.py

A local test receiver: a small HTTP server that accepts the agent's POST,
stores the image under `received/` and logs the GPS. It is scaffolding for
testing on your own machine, not part of the product - once the real backend
exists, point `--url` at that instead.
