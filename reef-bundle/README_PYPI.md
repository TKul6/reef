# Reef DAG Bundle

`ReefDagBundle` is the Airflow half of **Reef**.

Reef lets you swap in new DAG files on a Kubernetes-hosted Airflow without restarting anything.
DAGs are baked into a versioned Reef server image rather than synced onto a shared volume; this
bundle polls that server on every refresh and re-downloads the archive only when its content has
actually changed. Point Airflow at a new Reef image and the next refresh picks it up — no Airflow
restart, no DAG-sync sidecar, no shared filesystem to keep consistent.

`ReefDagBundle` is built on Airflow 3's
[DAG bundle](https://airflow.apache.org/docs/apache-airflow/stable/administration-and-deployment/dag-bundles.html)
interface (`BaseDagBundle`), which Airflow 2 does not have. **Airflow 3.1 or newer is required.**

```bash
pip install reef-bundle
```

Full documentation — configuring `dag_bundle_config_list`, retry/backoff tuning for riding out a
Reef rollout, and the endpoints it calls:
[github.com/TKul6/reef/tree/HEAD/reef-bundle](https://github.com/TKul6/reef/tree/HEAD/reef-bundle)

For more info regarding reef [click here](https://github.com/TKul6/reef)
