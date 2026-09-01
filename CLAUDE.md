# CLAUDE.md

Instructions for Claude Code (claude.ai/code) when working on this repository.

## Commands

Three packages live side by side, each versioned and released on its own:

| Directory | What it is |
|---|---|
| `reef-server/` | The FastAPI service. A Poetry project; ships as a Docker image |
| `reef-bundle/` | `ReefDagBundle`, the Airflow half that polls the server. A Poetry project |
| `reef-chart/` | The Helm chart that runs the server on Kubernetes |

### Server

The server is its own Poetry project under `reef-server/`; run every command in this section from that directory.

#### Install & Build
```bash
poetry install                 # Install every dependency, dev ones included
docker build -f Dockerfile .   # Build the Docker image
```

#### Test
```bash
poetry run pytest                     # Run the whole suite
poetry run pytest tests/test_file.py  # Run one test file
```

#### Lint & Format
```bash
ruff format   # Format code
ruff check    # Lint code
```

#### Run Dev Server
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

### Chart

Helm 3 is the only requirement; run these from `reef-chart/`. They are exactly what `reef-chart-CI.yml` runs on every
pull request touching the chart, so a green run locally is a green run in CI.

```bash
helm lint . --values ci/minimal-values.yaml                    # Lint
helm template reef-server . --values ci/minimal-values.yaml    # Render the smallest install
helm template reef-server . --values ci/full-values.yaml       # Render with every value set
helm package . --destination dist                              # Package into dist/
helm template reef-server .                                    # Must FAIL — no default image
```

`ci/minimal-values.yaml` is the smallest install that renders: the two required image fields and nothing else, so it
also shows what the chart's defaults produce on their own. `ci/full-values.yaml` sets every value, so a mistake in a
rarely-taken branch still shows up. Both are `.helmignore`d out of the packaged chart, as is `dist/`.

That last command is a test, not a mistake: the chart must keep **refusing** to render with no image set, and CI fails
if it ever renders. Never give `image.repository` or `image.tag` a default.

### Release
Releases are cut by release-please off `master`; see the Releasing section of `reef-server/README.md`. Every package has
its own entry in `release-please-config.json`, its own changelog, and its own tag prefix:

| Package | Tag | Version lives in |
|---|---|---|
| `reef-server` | `reef-server-vX.Y.Z` | `reef-server/pyproject.toml` |
| `reef-bundle` | `reef-bundle-vX.Y.Z` | `reef-bundle/pyproject.toml` |
| `reef-chart` | `reef-chart-vX.Y.Z` | `reef-chart/Chart.yaml` — the `version` field |

Three rules follow from that:

- **Write Conventional Commits** (`fix:`, `feat:`, `feat!:`/`BREAKING CHANGE:`) — the commit messages are the input the
  version bump is computed from. Only commits touching a package's own directory count towards its version.
- **Never hand-edit a version or a changelog.** The version fields above, every `CHANGELOG.md`, and
  `.release-please-manifest.json` all belong to release-please. In that manifest, each key must be the package's
  directory and each value must match the version in the file it tracks — a mismatch silently releases the wrong
  number.
- **`appVersion` in `Chart.yaml` is the exception.** release-please leaves it alone. It records which `reef-server` the
  templates are written against — its endpoints, its env vars, its non-root user — so bump it by hand when the chart
  starts relying on a newer one. It is not the version of the chart.

`reef-chart-release.yml` fires on the `reef-chart-v*` tag: it packages the chart, renders the packaged archive as a
smoke test, and attaches the `.tgz` to the GitHub release. There is no chart repository, so that release asset is the
whole distribution story for now. Note the archive is named from `Chart.yaml`'s `name`, making it
`reef-server-X.Y.Z.tgz` rather than `reef-chart-*.tgz`.

## Purpose

This project lets companies running Airflow on Kubernetes swap in new DAG files without restarting the Airflow
environment. It builds on the bundle feature introduced in Airflow 3.

## Architecture

Reef is a **FastAPI microservice** that hands out versioned Airflow DAG bundles as compressed `tar.gz` archives. It
ships as a Docker container and offers REST endpoints for distributing DAGs plus health and readiness probes.

Because the archive is baked into the image at build time and stays fixed at runtime, the content signature is computed
a single time and cached for as long as the process lives.

`reef-chart/` is how that container reaches Kubernetes. It installs a `Deployment`, a `ClusterIP` `Service`, and a
`ServiceAccount` — and nothing else: with one immutable archive inside the image there is no volume, no config map and
no state to manage.

The chart has **no default image**, and that is the point of it. Which DAGs are served, and at what version, is decided
by the image *you* build `FROM reef-server` with your `dags.tar.gz` baked in; the chart only points at it. So
`image.repository` and `image.tag` are both required and rendering fails naming the missing one, rather than deploying a
wrong image or a floating `:latest`. The `Service` is `ClusterIP` and its type is deliberately not configurable — Reef
hands out your DAGs, so it stays reachable from inside the cluster only.

### Key files
- `reef-server/reef_server/app.py` — the FastAPI app; feeds env vars into the service and defines all 5 REST endpoints
- `reef-server/reef_server/service.py` — `ReefService`, where the logic lives; the endpoints only wrap it
- `reef-server/reef_server/errors.py` — `ReefServiceError`, which carries the HTTP status to respond with
- `reef-server/reef_server/constants.py` — filenames, defaults, and the log format reused by the other modules
- `reef-server/reef_server/server.py` — the Uvicorn entry point; picks up `REEF_HOST`/`REEF_PORT`
- `reef-server/tests/` — the suite; a sibling of the package, as in `reef-bundle/`
- `reef-server/pyproject.toml` — Poetry setup, dependencies, and Ruff rules (150-char lines, double quotes)
- `reef-server/Dockerfile` — assembles the image and exposes port 8080; built with `reef-server/` as its context
- `reef-chart/Chart.yaml` — the chart `version` (release-please's) and `appVersion` (hand-bumped; see Release)
- `reef-chart/values.yaml` — every knob, each default carrying a comment on why it is what it is
- `reef-chart/templates/` — `deployment.yaml`, `service.yaml`, `serviceaccount.yaml`, `_helpers.tpl`, `NOTES.txt`
- `reef-chart/ci/` — `minimal-values.yaml` and `full-values.yaml`, the two value sets CI renders

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
- Constants belong in `reef-server/reef_server/constants.py` — never repeat a literal in two places.
- Every signature carries type hints written in modern syntax (`str | None`, `list[str]`).
- Tests are integration-style: run the real code path and mock only the parts that cannot execute locally.

Chart-specific:

- No default may deploy the wrong thing: `image.repository` and `image.tag` stay required.
- Probe paths and the `Service` type are fixed, not configurable — they belong to Reef's API, not to a deployment. Only
  the probe *timings* are values.
- Always quote an image tag, in values and in examples. Unquoted, `1.0` is a YAML float and reaches the cluster as `1`.
- `service.port` is the one port value: it becomes the Service port, the container port, and the server's `REEF_PORT`,
  so moving it moves the whole chain rather than half of it.
- Comment the *why* on a value whose default is load-bearing. `podSecurityContext.runAsUser` being numeric, and
  `readOnlyRootFilesystem` being safe, are the existing examples.
