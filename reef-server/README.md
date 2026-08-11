# Reef Server

The Reef server is a lightweight FastAPI microservice that serves DAG files to Airflow over a REST API. It holds one
immutable `dags.tar.gz` archive, baked into its image at build time, and answers questions about it.

This page covers building, configuring, and operating the server. For the problem Reef solves and how the pieces fit
together, start at the [solution README](../README.md).

---

## Building an image with your DAGs

Everything that varies between deployments — which DAGs, which version — is decided when the image is built. Pack your
DAG files into `dags.tar.gz`, layer it on top of the base image, and tell Reef which version it is serving:

```dockerfile
FROM reef:<version>

COPY dags.tar.gz /dags/dags.tar.gz
# Optional but recommended — see "Signatures" below
COPY dags_version.txt /dags/dags_version.txt

ENV DAGS_DIR=/dags
ENV DAGS_VERSION=1.2.0
```

The base image already starts the server, so a child image does not need its own `CMD`. It carries its own
`REEF_SERVER_VERSION` as well, baked in when the release built it — leave that one alone.

---

## Signatures

`GET /api/v1/dags/metadata` hands back a `signature` — the value `ReefDagBundle` watches when deciding whether to
re-download. Reef resolves it once per process, preferring:

1. Whatever `dags_version.txt` holds, when that file sits next to the archive in `DAGS_DIR`.
2. Failing that, a SHA-256 of `dags.tar.gz` cut down to 12 hex characters. It does the job, but it costs a full read of
   the archive on the first request and emits a warning.

Writing `dags_version.txt` during the build is the cheaper route, and it puts you in control of what qualifies as a
change. Reef does not generate the file — write whatever your build already knows (a CI build number, a git SHA) and
`COPY` it in alongside the archive, as shown above.

Because the archive cannot change while the container lives, the resolved signature is cached for the life of the
process. A new set of DAGs means a new image, which means a new process.

---

## Configuration

Configuration is only needed for local runs. If you run Reef from a Docker image built as shown above, everything is
already set.

### Basic

| Variable | Default | Purpose |
|---|---|---|
| `REEF_HOST` | `0.0.0.0` | Address the server binds to |
| `REEF_PORT` | `8080` | Port the server listens on |

### Advanced

| Variable | Default | Purpose |
|---|---|---|
| `DAGS_DIR` | `/dags` | Directory holding `dags.tar.gz` (and optionally `dags_version.txt`) |
| `DAGS_VERSION` | — | Version of the DAGs being served. Required; endpoints return `500` when unset |
| `REEF_SERVER_VERSION` | — | Version of the Reef server itself, reported by `/api/v1/information`. Already set in released images |

---

## Running Locally

```bash
poetry install
DAGS_VERSION=1.0.0 DAGS_DIR=./dags poetry run reef-server
```

---

## Troubleshooting

### Confirming which image a pod is running

Reef prints its configuration as it boots:

```
[2026-01-01 12:00:00,000] INFO - Reef is starting up
[2026-01-01 12:00:00,000] INFO - Serving bundles out of: /dags
[2026-01-01 12:00:00,000] INFO - Bundle version: <DAGS_VERSION>
[2026-01-01 12:00:00,000] INFO - Reef version: <REEF_SERVER_VERSION>
```

```bash
kubectl logs -n <namespace> deploy/reef --tail=20
```

Check that `Bundle version` and `Reef version` line up with the image you believe is deployed.

### Confirming Reef is accessible and healthy

**Liveness** — answers `200 {"healthy": true}` for as long as the process is alive:

```bash
curl -s http://<reef-host>:8080/api/v1/health
# Expected: {"healthy":true}
```

**Readiness** — the complete check payload:

```bash
curl -s http://<reef-host>:8080/api/v1/ready
# Expected: {"healthy":true,"dags_exists":true,"dags_version_set":true}
```

When readiness answers `503`:

- `dags_exists: false` — there is no `dags.tar.gz` at `$DAGS_DIR/dags.tar.gz`. Make sure the archive made it into the
  image and that `DAGS_DIR` really points where you assume it does.
- `dags_version_set: false` — the deployment is missing the `DAGS_VERSION` environment variable.

### Confirming which content is being served

```bash
curl -s http://<reef-host>:8080/api/v1/dags/metadata
# Expected: {"version":"1.2.0","signature":"1205555-6"}
```

Since a changed `signature` is exactly what makes `ReefDagBundle` re-download, this endpoint is the fastest way to tell
whether a new image is serving different content than the one before it.

---

## Releasing

Releases are cut by [release-please](https://github.com/googleapis/release-please), driven by the commits that land on
`master`. Nobody edits a version by hand.

1. Land a change on `master` with a [Conventional Commits](https://www.conventionalcommits.org/) message. `fix:` earns a
   patch, `feat:` a minor, `feat!:` or a `BREAKING CHANGE:` footer a major. With squash merges the pull request title is
   what gets parsed, so that is the line to get right.
2. release-please opens a `chore(main): release reef-server X.Y.Z` pull request holding the bumped
   `reef-server/pyproject.toml` and the new `reef-server/CHANGELOG.md` entries. It keeps that pull request up to date as
   further commits land.
3. Merging it publishes the GitHub release, tags the commit `reef-server-vX.Y.Z`, and builds and smoke-tests
   `reef-server:X.Y.Z` with the version baked in. The image is discarded afterwards — nothing is pushed to a registry
   yet.

Only commits that touch `reef-server/` count towards the server's version, so `reef-bundle` can later be released on a
version line of its own.

---

## Further Reading

- [API Reference](../docs/api.md) — the full specification for every Reef REST endpoint, covering response shapes, error
  codes, and field descriptions.
- [Solution overview](../README.md) — the problem Reef solves and how the server and `ReefDagBundle` work together.
