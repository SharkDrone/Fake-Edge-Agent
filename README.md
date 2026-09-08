# Fake Edge-Agent (SharkDrone, steg 1)

Et Python-script som hvert 10. sekund sender et tilfeldig bilde fra `images/`
sammen med falsk GPS til en URL. Ingen AI, ingen tredjepartspakker - kun stdlib,
sa det kjorer med `python agent.py` rett ut av boksen.

## Kom i gang

```bash
python tools/make_sample_images.py          # lager 5 testbilder i images/ (krever Pillow)
python receiver.py --port 8000              # terminal 1: test-mottaker
python agent.py --url http://localhost:8000/ingest   # terminal 2: agenten
```

Agenten skriver en linje per vellykket sending:

```
sendt  #1  sample_01.jpg  59.894019,10.617978  14 kB  -> HTTP 200 {"status": "ok", ...}
```

Legg gjerne inn dine egne bilder i `images/` (jpg, jpeg, png, webp, bmp, gif).

## agent.py

| Flagg | Standard | Beskrivelse |
| --- | --- | --- |
| `--url` | `http://localhost:8000/ingest` | URL som bilde + GPS postes til |
| `--images-dir` | `./images` | Mappe med bilder |
| `--interval` | `10` | Sekunder mellom hver sending |
| `--count` | `0` | Antall sendinger, 0 = kjor til Ctrl+C |
| `--device-id` | `drone-001` | Id for denne "dronen" |
| `--lat` / `--lon` | Oslofjorden | Startposisjon for GPS-sporet |
| `--timeout` | `15` | HTTP-timeout i sekunder |

Exit-kode er 0 nar alt gikk gjennom, 2 hvis minst en sending feilet.

## Hva som sendes

En `POST` med `multipart/form-data`:

- `image` - selve bildefilen
- `device_id`, `captured_at` (UTC ISO-8601), `frame_id`
- `lat`, `lon`, `altitude_m`, `heading_deg`, `speed_mps`, `accuracy_m`
- `metadata` - de samme GPS-feltene samlet som JSON, for mottakere som vil ha det slik

GPS-en er en random walk: agenten starter i startposisjonen og driver videre med
liten kursendring for hvert steg, sa sporet ser ut som en drone i bevegelse
framfor tilfeldige punkter spredt utover kartet.

## receiver.py

Test-mottaker som lagrer innkommende bilder i `received/` og logger GPS-en.
Den er kun et stillas for lokal testing - nar den ekte backend-en finnes,
peker du `--url` dit i stedet.

## Neste steg

Steg 2 er a bytte test-mottakeren mot den ekte backend-en (og deretter legge
AI-en inn i pipelinen). Agenten selv trenger ingen endringer for det - bare en
ny `--url`.
