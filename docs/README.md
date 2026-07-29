# Reef — Airflow DAGs Server

Reef is a lightweight FastAPI microservice that serves DAG files to airflow using REST API.

## Why
When running airflow on Kubernetes, updating the dags can be pretty complecated:
- Adding the dags to the docker image require replacing the image on every build, which result in downtime.
- Using PVC might be a little tricky, especially if you are not woring in a single AZ in Kuebrentes.

## The solution - Reef!
Reef suggests a new way to hot swap dags with no Downtime! No more restarting the whole environment — which cuts down how often production has to be restarted.

Reef will pack your dags and serves them via Rest api!
On the airflow side, a special Bundle (Called `ReefDagBundle`) will communicate with the Reef server.

---

## Prerequisites

**Airflow 3.1 or newer.** Reef is built on Airflow 3's
[DAG Bundle](https://airflow.apache.org/docs/apache-airflow/stable/administration-and-deployment/dag-bundles.html)
interface (`BaseDagBundle`), so Airflow 2 is not supported.

---

## How It Works

TBD

### Building an image with your DAGs

TBD

### Signatures

Since usually dags do not change on every cycle (30 seconds), reef will store a signature to compare on every cycle, if the signature hasn't changed, the bundle will not download the dags again.

>Note: The signature is provided on build time, you can provide your own signature. When packing the dags, reef will add the signature to the 

`GET /api/v1/dags/metadata` hands back a `signature` — the value `ReefDagBundle` watches when deciding whether to
re-download. Reef works it out once per process, preferring:

1. Whatever `dags_version.txt` holds, when that file sits next to the archive.
2. Failing that, a SHA-256 of `dags.tar.gz` cut down to 12 hex characters. It does the job, but it costs a full read of
   the archive on the first request and emits a warning.

Writing `dags_version.txt` during the build is the cheaper route, and it puts you in control of what qualifies as a
change.

---

## Configuration

The configuration is required only for local runs, If you run reef from a docker image, everything is already configured!

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
| `REEF_SERVER_VERSION` | — | Version of the Reef server itself, reported by `/api/v1/information` |

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
# Expected: {"version":"1.2.0","signature":"a3f9c1d2e4b5"}
```

Since a changed `signature` is exactly what makes `ReefDagBundle` re-download, this endpoint is the fastest way to tell
whether a new image is serving different content than the one before it.

---

## Further Reading

- [API Reference](api.md) — the full specification for every Reef REST endpoint, covering response shapes, error codes,
  and field descriptions.
