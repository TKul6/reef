# Building Your DAGs Docker Image

A guide to packaging your DAGs into a Docker image `FROM` a Reef server base image, and publishing it — for example,
to Docker Hub — so it can be deployed with the [Reef chart](../../../reef-chart/README.md).

The following guide will guide you in creating an image for the reef-server.

## 1. Package your DAGs into an archive

```bash
tar -czf dags.tar.gz -C dags .
```

This produces `dags.tar.gz` at the repository root.

## 2. Give this build a unique signature

Reef re-serves your DAGs under a **signature** that tells `ReefDagBundle` when to re-download — see
[reef-server/README.md#signatures](../../../reef-server/README.md#signatures). It reads that signature from a
`dags_version.txt` file sitting next to `dags.tar.gz`, so write one alongside the archive.

This repository ships a small composite action, [Add DAGs Version](action.yml), that does exactly that — writes
`dags_version.txt` with a value unique to the workflow run:

```yaml
# Pin @master to a specific commit SHA instead if you want a stable reference - this
# repository does not currently publish version tags for this action.
- name: Write a unique dags_version.txt
  uses: TKul6/reef/.github/actions/add-dags-version@v1
  with:
    dags_location: .   # the directory dags.tar.gz was written to in step 1
```

| Input | Required | Description |
|---|---|---|
| `dags_location` | Yes | Path to the directory your build will `COPY` into the image, relative to the repository root. Must already exist — checkout your repository before this step. |

**You don't have to use this action.** `dags_version.txt` is a plain text file with exactly one requirement: its
content must change whenever you want to signal a new signature. You can create the file yourself and place it in the dags folder.

## 3. Write the Dockerfile

```dockerfile
FROM <your-dockerhub-namespace>/reef-server:1.0.1

ARG DAGS_VERSION
ARG DAGS_FOLDER=/dags

COPY dags.tar.gz ${DAGS_FOLDER}/dags.tar.gz
COPY dags_version.txt ${DAGS_FOLDER}/dags_version.txt

ENV DAGS_DIR=${DAGS_FOLDER}
ENV DAGS_VERSION=${DAGS_VERSION}
```

`DAGS_FOLDER` defaults to `/dags`, matching `DAGS_DIR`'s own default, so it only needs overriding if you want the
archive somewhere else in the image. `DAGS_VERSION` has no default — it is the version *you* assign to this set of
DAGs (a release number, a date — whatever you use to say "what's deployed"), so pass it at build time:
`--build-arg DAGS_VERSION=1.2.0`. It is separate from the signature in `dags_version.txt`, which exists purely to
tell `ReefDagBundle` when to re-download.

## 4. Build and publish it with GitHub Actions

Putting the previous steps together into one workflow:

```yaml
name: Build and publish DAGs image

on:
  push:
    branches: [master]

env:
  IMAGE: <your-dockerhub-namespace>/my-dags
  DAGS_VERSION: "1.2.0"

jobs:
  build-and-push:
    runs-on: ubuntu-latest

    steps:
      - name: Check out the repository
        uses: actions/checkout@v4

      - name: Package the DAGs
        run: tar -czf dags.tar.gz -C dags .

      - name: Write a unique dags_version.txt
        uses: TKul6/reef/.github/actions/add-dags-version@master
        with:
          dags_location: /dags

      - name: Log in to Docker Hub
        uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}

      - name: Build the image
        run: docker build --build-arg DAGS_VERSION="$DAGS_VERSION" --tag "$IMAGE:$DAGS_VERSION" .

      - name: Push the image
        run: docker push "$IMAGE:$DAGS_VERSION"
```

`DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` are repository secrets holding a Docker Hub access token — not your
account password.
