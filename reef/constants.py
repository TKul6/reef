"""Values shared across the Reef server modules."""

# --- Bundle layout on disk ---

DEFAULT_BUNDLE_DIR = "/dags"
ARCHIVE_FILENAME = "dags.tar.gz"
SIGNATURE_FILENAME = "dags_version.txt"

# --- Signature resolution ---

# Signatures are truncated to this many hex characters, in the spirit of a short git SHA.
SIGNATURE_HEX_LENGTH = 12

# How much of the archive is read per iteration when hashing it.
CHECKSUM_CHUNK_BYTES = 8192

# --- Server ---

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = "8080"

# --- Logging ---

# Reef configures this logger rather than the root one, so a host process that has already
# set up root logging cannot silently swallow our lines, and third-party loggers stay quiet.
LOGGER_NAME = "reef"
LOG_FORMAT = "[%(asctime)s] %(levelname)s - %(message)s"
