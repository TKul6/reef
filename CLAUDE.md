# CLAUDE.md

Instructions for Claude Code (claude.ai/code) when working on this repository.

## Commands

The server is its own Poetry project under `reef-server/`; run every command below from that directory.

### Install & Build
```bash
poetry install                 # Install every dependency, dev ones included
docker build -f Dockerfile .   # Build the Docker image
```

### Test
```bash
poetry run pytest                     # Run the whole suite
poetry run pytest tests/test_file.py  # Run one test file
```

### Lint & Format
```bash
ruff format   # Format code
ruff check    # Lint code
```

### Run Dev Server
```bash
DAGS_VERSION=1.0.0 DAGS_DIR=./dags poetry run reef-server
# Or: python -m reef_server.server
```

Env vars that matter:
- `REEF_HOST` — host the server binds to (default: `0.0.0.0`)
- `REEF_PORT` — port the server listens on (default: `8080`)
- `DAGS_DIR` — directory that contains the DAGs archive (default: `/dags`)
- `DAGS_VERSION` — version of the DAGs being served (mandatory; without it the endpoints answer 500)
- `REEF_SERVER_VERSION` — server version that `/api/v1/information` reports

## Purpose

This project lets companies running Airflow on Kubernetes swap in new DAG files without restarting the Airflow
environment. It builds on the bundle feature introduced in Airflow 3.

## Architecture

Reef is a **FastAPI microservice** that hands out versioned Airflow DAG bundles as compressed `tar.gz` archives. It
ships as a Docker container and offers REST endpoints for distributing DAGs plus health and readiness probes.

Because the archive is baked into the image at build time and stays fixed at runtime, the content signature is computed
a single time and cached for as long as the process lives.

### Key files
- `reef-server/reef_server/app.py` — the FastAPI app; feeds env vars into the service and defines all 5 REST endpoints
- `reef-server/reef_server/service.py` — `ReefService`, where the logic lives; the endpoints only wrap it
- `reef-server/reef_server/errors.py` — `ReefServiceError`, which carries the HTTP status to respond with
- `reef-server/reef_server/constants.py` — filenames, defaults, and the log format reused by the other modules
- `reef-server/reef_server/server.py` — the Uvicorn entry point; picks up `REEF_HOST`/`REEF_PORT`
- `reef-server/tests/` — the suite; a sibling of the package, as in `reef-bundle/`
- `reef-server/pyproject.toml` — Poetry setup, dependencies, and Ruff rules (150-char lines, double quotes)
- `reef-server/Dockerfile` — assembles the image and exposes port 8080; built with `reef-server/` as its context

### API Endpoints
| Endpoint | Handler | Purpose |
|---|---|---|
| `GET /api/v1/health` | `liveness` | Liveness check |
| `GET /api/v1/information` | `service_info` | Server + DAGs version info |
| `GET /api/v1/dags/metadata` | `bundle_metadata` | DAGs version and content signature |
| `GET /api/v1/dags/download` | `download_bundle` | Stream the DAGs as `dags.tar.gz` |
| `GET /api/v1/ready` | `readiness_probe` | Readiness probe — checks the archive exists and the version is set |

### DAGs directory layout (at runtime)
```
$DAGS_DIR/
  dags.tar.gz        # the archive that /dags/download serves
  dags_version.txt   # optional; whatever it contains becomes the signature
```

## Conventions

- A single class per file, named after the class in snake_case.
- Private helpers sit at the top of a class, ahead of the public methods.
- Constants belong in `reef/constants.py` — never repeat a literal in two places.
- Every signature carries type hints written in modern syntax (`str | None`, `list[str]`).
- Tests are integration-style: run the real code path and mock only the parts that cannot execute locally.
