# Reef API Reference

Every endpoint listens on port `8080` unless configured otherwise, and none of them require authentication.

Endpoints are documented below in the order you are likely to care about them: the two DAG endpoints that do the actual
work, then the version metadata endpoint, then the two probes.

---

## `GET /api/v1/dags/metadata`

Reports the version and content signature of the DAG archive being served right now. This is the endpoint
`ReefDagBundle` polls when deciding whether a re-download is warranted.

**Response `200 OK`**
```json
{
  "version": "3.1.0",
  "signature": "a3f9c1d2e4b5"
}
```

| Field | Description |
|---|---|
| `version` | Whatever the `DAGS_VERSION` environment variable is set to |
| `signature` | The contents of `dags_version.txt` when that file exists; otherwise a SHA-256 of `dags.tar.gz` trimmed to 12 hex characters |

The `signature` gets resolved a single time per process and then cached, because the archive cannot change while the
container lives. `ReefDagBundle` holds this value against its own cached copy and pulls a new archive only when the two
disagree.

**Response `500 Internal Server Error`** when `DAGS_VERSION` has no value or `dags.tar.gz` is missing.

---

## `GET /api/v1/dags/download`

Streams the entire `dags.tar.gz` archive.

**Response `200 OK`**

- Content-Type: `application/gzip`
- Body: the binary `dags.tar.gz` archive

`ReefBundleHelper` unpacks the archive straight into Airflow's local bundle directory. What comes out are the DAG
Python files that Airflow goes on to scan.

**Response `500 Internal Server Error`** when `DAGS_VERSION` has no value or `dags.tar.gz` is missing.

---

## `GET /api/v1/information`

Hands back version metadata covering both the running Reef server and the DAGs it serves.

**Response `200 OK`**
```json
{
  "serverVersion": "1.0.2",
  "dagsVersion": "3.1.0"
}
```

| Field | Source |
|---|---|
| `serverVersion` | `REEF_SERVER_VERSION` environment variable |
| `dagsVersion` | `DAGS_VERSION` environment variable |

**Response `500 Internal Server Error`** when either `REEF_SERVER_VERSION` or `DAGS_VERSION` is unset:
```json
{"error": "Server version is not configured"}
```

---

## `GET /api/v1/ready`

Readiness probe — verifies that `dags.tar.gz` exists and that `DAGS_VERSION` has been configured. Wire this up as your
Kubernetes readiness probe.

**Response `200 OK`** — the server can serve DAGs:
```json
{
  "healthy": true,
  "dags_exists": true,
  "dags_version_set": true
}
```

**Response `503 Service Unavailable`** — the server is not ready:
```json
{
  "healthy": false,
  "dags_exists": false,
  "dags_version_set": false
}
```

What each check field means:

| Field | Description |
|---|---|
| `dags_exists` | `true` when `dags.tar.gz` is sitting at `$DAGS_DIR/dags.tar.gz` |
| `dags_version_set` | `true` when the `DAGS_VERSION` environment variable has a value |

Checks run in sequence and the response bails out at the first failure, so a `false` for `dags_exists` leaves
`dags_version_set` reported as `false` simply because it was never evaluated.

---

## `GET /api/v1/health`

Says whether the server process is alive. Use it as a liveness probe.

**Response `200 OK`**
```json
{"healthy": true}
```

As long as the process is up this endpoint answers `200`. It makes no claim about whether DAGs are actually available.
