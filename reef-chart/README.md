# Reef Chart

A Helm chart that runs the Reef server on Kubernetes. It installs a `Deployment`, a `ClusterIP`
`Service`, and a `ServiceAccount` — nothing else. Reef holds one immutable archive baked into its image, so there is no
volume, no config map, and no state to manage.

This page covers installing and configuring the chart. For the problem Reef solves start at the
[solution README](../README.md); for the server itself, see the [server README](../reef-server/README.md).

---

## The image is yours

The chart has **no default image**, and that is the whole point of it. Which DAGs are served, and which version they are,
is decided when *you* build an image on top of the Reef server:

```dockerfile
FROM reef-server:<version>

COPY dags.tar.gz /dags/dags.tar.gz
COPY dags_version.txt /dags/dags_version.txt

ENV DAGS_VERSION=1.2.0
```

The chart then points at that image. Both `image.repository` and `image.tag` are required: rendering fails immediately
with a message naming the missing value, rather than deploying a wrong image or a floating `:latest`.

See [Building an image with your DAGs](../reef-server/README.md#building-an-image-with-your-dags) for the full recipe.

---

## Installing

```bash
helm install dags ./reef-chart \
  --namespace airflow \
  --set image.repository=my-registry.example.com/my-dags \
  --set image.tag=1.2.0
```

Or with a values file:

```yaml
# my-values.yaml
image:
  repository: my-registry.example.com/my-dags
  tag: "1.2.0"

replicaCount: 2
```

```bash
helm install dags ./reef-chart --namespace airflow --values my-values.yaml
```

> **Quote the tag.** An unquoted `1.0` is a YAML float, and it reaches the cluster as `1`. Tags such as `1.2.0` parse as
> strings either way, but quoting every tag costs nothing and never surprises you.

---

## Configuration

### Basic

| Value | Default | Purpose |
|---|---|---|
| `image.repository` | — | Your image, built `FROM reef-server`. **Required** |
| `image.tag` | — | Tag of that image. **Required**; quote it |
| `image.pullPolicy` | `IfNotPresent` | Standard Kubernetes pull policy |
| `imagePullSecrets` | `[]` | Existing `docker-registry` secrets, for a private registry |
| `replicaCount` | `1` | How many pods serve the DAGs |
| `service.port` | `8080` | Port for the Service, the container, and the server's own `REEF_PORT` |
| `resources` | `50m`/`128Mi` requests, `500m`/`256Mi` limits | Sized for streaming a pre-built archive |

### DAGs

| Value | Default | Purpose |
|---|---|---|
| `dagsVersion` | `""` | Overrides the image's baked-in `DAGS_VERSION`. Normally left empty |
| `dagsDir` | `""` | Overrides `DAGS_DIR`. Empty means the server's own default, `/dags` |
| `extraEnv` | `[]` | Extra environment variables, in full Kubernetes `name`/`value` (or `valueFrom`) form |

Leaving `dagsVersion` empty is the recommended path: the version travels with the image that contains the DAGs, so the
two cannot drift apart. Set it only when you need to override what the image says.

### Scheduling and security

| Value | Default | Purpose |
|---|---|---|
| `livenessProbe`, `readinessProbe` | 5s delay, 10s period | Probe **timings**. The endpoints are fixed — see below |
| `podSecurityContext` | `runAsNonRoot: true`, `runAsUser: 1000` | Pod-level context — the two belong together, see below |
| `securityContext` | no privilege escalation, read-only root, all capabilities dropped | Container-level context |
| `serviceAccount.create` | `true` | Set `false` and give `serviceAccount.name` to bring your own |
| `nameOverride`, `fullnameOverride` | `""` | Override the generated resource names |
| `podAnnotations`, `podLabels` | `{}` | Added to the pod template |
| `nodeSelector`, `tolerations`, `affinity` | `{}` / `[]` | Standard scheduling controls |

`readOnlyRootFilesystem` is on by default because the server only ever reads from disk. If your own image needs to write,
set it to `false`.

`runAsNonRoot` and `runAsUser` are a pair, and this is the one place a change to your image can stop the chart dead.
Asked for `runAsNonRoot` on its own, the kubelet has to satisfy itself that the image's user is not root; it cannot do
that when the image names its user rather than numbering it, so it fails the container with
`CreateContainerConfigError`:

```
container has runAsNonRoot and image has non-numeric user (appuser), cannot verify user is non-root
```

---

## Reaching Reef

The `Service` is `ClusterIP`, and its type is deliberately **not** configurable — Reef hands out your DAGs, so it is
reachable from inside the cluster only. Nothing in this chart will expose it to the outside world.

In-cluster, which is what `ReefDagBundle` should point at:

```
http://<release>-reef-server.<namespace>.svc.cluster.local:8080
```

From your own machine, forward the port yourself:

```bash
kubectl --namespace airflow port-forward svc/dags-reef-server 8080:8080
curl -fsS localhost:8080/api/v1/information
```

`helm install` prints both of these, filled in with your release's actual names.

---

## Probes

The chart wires the probes to the endpoints the server already provides, and the paths are not configurable because they
are part of Reef's API rather than of a deployment:

| Probe | Endpoint | Effect |
|---|---|---|
| Liveness | `GET /api/v1/health` | `200` for as long as the process is alive |
| Readiness | `GET /api/v1/ready` | `503` until `dags.tar.gz` is present *and* the version is set |

That readiness behaviour is worth knowing when a rollout appears stuck: a pod whose image never got an archive, or that
is missing `DAGS_VERSION`, stays out of the Service instead of serving `500`s.
[Troubleshooting](../reef-server/README.md#troubleshooting) covers reading the response payload.

---

## Development

Helm 3 is the only requirement. From this directory:

```bash
helm lint . --values ci/minimal-values.yaml
helm template reef-server . --values ci/minimal-values.yaml
helm template reef-server . --values ci/full-values.yaml
helm package . --destination dist
```

`ci/minimal-values.yaml` is the smallest install that renders; `ci/full-values.yaml` sets every value, so a mistake in a
rarely-taken branch still shows up. Both are excluded from the packaged chart, and
[reef-chart-CI.yml](../.github/workflows/reef-chart-CI.yml) runs exactly these commands on every pull request that
touches this directory — along with a check that the chart still *refuses* to render with no image set.
