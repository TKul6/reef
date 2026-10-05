# Reef DAG Bundle

`ReefDagBundle` is the Airflow half of Reef. It keeps your DAG files in sync with a Reef server, polling for a new
bundle on every refresh and re-downloading only when the content has actually changed.

For the server that answers those calls, see the [Reef server README](../reef/README.md).

---

## Requirements

**Airflow 3.1 or newer.** The bundle is built on Airflow 3's
[DAG bundle](https://airflow.apache.org/docs/apache-airflow/stable/administration-and-deployment/dag-bundles.html)
interface (`BaseDagBundle`), which Airflow 2 does not have.

`apache-airflow` is intentionally *not* declared as a dependency of this package — the environment you install into
already provides it.

---

## Install

Install the following package when creating your airflow image:

```bash

pip install reef-bundle

```
---

## Configure

Airflow reads its bundles from `dag_bundle_config_list`:

```ini
[dag_processor]
dag_bundle_config_list = [
    {
        "name": "reef",
        "classpath": "reef_bundle.bundle.ReefDagBundle",
        "kwargs": {
            "reef_url": "http://reef:8080",
            "timeout": 30
        }
    }
]
```

`name` is what the bundle is called in the Airflow UI.

### Parameters

| Parameter | Default | Purpose |
|---|---|---|
| `reef_url` | — | Where Reef is listening, e.g. `http://reef:8080`. Falls back to `REEF_URL` (ENV param); one of the two is required |
| `timeout` | `30` | Seconds to wait on a single request to Reef |
| `max_retries` | `3` | Attempts each request gets in total, first try included |
| `backoff_initial` | `5` | Seconds to wait before the first retry |
| `backoff_increment` | `5` | Extra seconds added to that wait on every further retry |

The wait between attempts grows linearly, so the defaults give up after roughly 15 seconds: try, wait 5, try, wait 10,
try. That is deliberately patient enough to ride out a Reef rollout — see
[Advanced configuration](#advanced-configuration--riding-out-a-reef-outage) for when it is not.

---

## Advanced configuration — riding out a Reef outage

`max_retries`, `backoff_initial`, and `backoff_increment` exist for one situation: Reef is temporarily not there. A
rolling deployment of a new DAGs image, a node drain, a maintenance window — during any of these, requests to Reef fail
for a stretch and then start working again. The retry loop is what turns that stretch into a delay instead of an error.

### Why it matters where it fails

Reef is not reachable at the same cost everywhere the bundle touches it:

| Moment | If every attempt fails |
|---|---|
| `initialize()` | The exception propagates and the bundle does not come up. This is the expensive one |
| `refresh()` | That refresh fails; the DAG files already on disk stay in place and the next interval tries again |
| `get_current_version()` | The error is swallowed and `None` is returned — Airflow just does not learn the version |

So the retry window is really sized for `initialize()`. An Airflow component starting up in the middle of a Reef
rollout is exactly the collision worth surviving, and it is the one moment where losing the race actually costs you
something.

### Sizing the window

Waits grow linearly, so the total time spent waiting across a fully failed call is:

```
total_wait = (max_retries - 1) * backoff_initial
           + backoff_increment * (max_retries - 1) * (max_retries - 2) / 2
```

| Settings | Waits between attempts | Total wait | Fits |
|---|---|---|---|
| `3` / `5` / `5` (defaults) | 5, 10 | 15s | A pod restart, a brief blip |
| `6` / `10` / `10` | 10, 20, 30, 40, 50 | 150s | A rolling deploy of a new DAGs image |
| `8` / `15` / `15` | 15, 30, 45, 60, 75, 90, 105 | 420s | An announced maintenance window |

Two things the formula leaves out:

- **`timeout` stacks on top.** A Reef that hangs rather than refusing burns up to `timeout` seconds per attempt, so the
  real worst case is `total_wait + max_retries * timeout`. With the defaults that is 15s of waiting but 105s in total.
  A pod that is being deleted usually refuses connections outright, which returns immediately — but a half-dead one may
  not.
- **The loop blocks its caller.** Retries happen in the calling thread, so a long window inside `refresh()` holds up the
  DAG processor for that long. Keep the worst case comfortably under your refresh interval, or widen the window only
  where it pays for itself.

```ini
[dag_processor]
dag_bundle_config_list = [
    {
        "name": "reef",
        "classpath": "reef_bundle.bundle.ReefDagBundle",
        "kwargs": {
            "reef_url": "http://reef:8080",
            "timeout": 15,
            "max_retries": 6,
            "backoff_initial": 10,
            "backoff_increment": 10
        }
    }
]
```

Note the lowered `timeout` alongside the wider retry window: more attempts spread further apart, but each one gives up
on a hung server sooner. That trade is usually the right one for an outage you expect to end on its own.

### What not to solve here

Retries cover Reef being *absent*. They do not help when Reef is up and answering wrongly — a missing `DAGS_VERSION` or
an absent `dags.tar.gz` makes Reef return `500`, and `raise_for_status()` treats that as a failure worth retrying even
though no amount of waiting will fix it. If your logs show a call exhausting every attempt against a Reef that is
plainly running, check `GET /api/v1/ready` on the server before touching these parameters.

---

## What a refresh does

1. `GET /api/v1/dags/metadata` — Reef reports the bundle version and its content signature.
2. The remote signature is compared against the one this bundle last extracted.
3. On a mismatch, `GET /api/v1/dags/download` streams the `dags.tar.gz` archive.
4. The bundle directory is emptied, the archive is extracted into it, and the new signature is held in memory.

When the signatures already agree, steps 3 and 4 are skipped and the refresh costs one small request.

### Why the signature on disk is consulted too

Before concluding that a download is needed, the bundle reads `dags_version.txt` from its own directory. An Airflow
worker can start with that directory already populated by an earlier extraction — a shared volume, for instance —
before this bundle has any in-memory signature of its own. A signature file sitting there describes what is genuinely
on disk, which makes it a better answer than assuming the directory is empty. A download only happens if the signature
is still out of date after that check.

The bundle never writes that file itself; it only reads it. For the check to save you a download, `dags_version.txt`
has to be **inside** `dags.tar.gz`, so that extracting the archive puts it in the bundle directory. Pack it into the
archive during your build, matching the value the server serves as its signature. Without it the recovery step simply
finds nothing and the bundle downloads — correct, just not free.

---

## Endpoints used

Three of the Reef server's five:

| Endpoint | Called |
|---|---|
| `GET /api/v1/health` | Once, during `initialize()`, to fail fast when Reef is unreachable |
| `GET /api/v1/dags/metadata` | Every refresh |
| `GET /api/v1/dags/download` | Only when the signature has changed |

`/api/v1/information` and `/api/v1/ready` are for operators and the kubelet; the bundle does not call them.

---

## Versioning

`supports_versioning` is `True`, which lets Airflow pin a DAG run to the version it was scheduled with:
`get_current_version()` returns a pinned version as-is, without a request to Reef, so a task reports the version it
started under rather than whatever is newest.

Note what this does *not* do: a Reef server serves exactly one archive, fixed for the life of its image, so there is no
endpoint to fetch a specific historical version from. Pinning records which version a run belongs to; it does not
retrieve old DAG code.

---

## Layout

| File | Holds |
|---|---|
| `reef_bundle/bundle.py` | `ReefDagBundle` — the Airflow-facing class and the only file that imports `airflow` |
| `reef_bundle/helper.py` | `ReefBundleHelper` — directory handling, extraction, signature bookkeeping |
| `reef_bundle/client.py` | `ReefClient` — HTTP calls to Reef, with retries |

---

## Tests

```bash
poetry install
poetry run pytest
```

The suite runs without Airflow installed. All the logic worth testing lives in `helper.py` and `client.py`, neither of
which imports `airflow` — the helper takes a `ReefClient` and a directory, so a mock client and a `tmp_path` exercise
every path, including the retry and signature-recovery branches.

```bash
ruff format   # format
ruff check    # lint
```

