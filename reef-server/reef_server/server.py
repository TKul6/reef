from __future__ import annotations

import os

import uvicorn

from reef_server.constants import DEFAULT_HOST, DEFAULT_PORT


def main():
    host = os.getenv("REEF_HOST", DEFAULT_HOST)
    port = int(os.getenv("REEF_PORT", DEFAULT_PORT))
    uvicorn.run("reef_server.app:app", host=host, port=port)


if __name__ == "__main__":
    main()
