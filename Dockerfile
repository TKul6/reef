FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir poetry && \
    poetry config virtualenvs.create false

# Install deps in two steps for better layer caching:
# 1. Install dependencies (cached unless pyproject.toml or poetry.lock changes)
COPY pyproject.toml ./
COPY poetry.lock ./
RUN poetry install --no-root

# 2. Copy source and install the package itself
COPY reef ./reef/


# Create a non-root user
RUN adduser --disabled-password --gecos '' appuser && \
    chown -R appuser:appuser /app
USER appuser

# Baked in by the release build, so an image reports its own version with nothing set in the
# deployment. Declared last on purpose: a new version must not invalidate the poetry install layer.
# Left with no default deliberately — an unset ARG makes this the empty string, and /information
# keeps answering 500 rather than reporting a made-up version.
ARG REEF_SERVER_VERSION
ENV REEF_SERVER_VERSION=${REEF_SERVER_VERSION}

EXPOSE 8080

# CMD so child images that don't override it still start the server
CMD ["python3",  "-m", "reef.server"]
