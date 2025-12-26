"""Telemetry setup hook (no-op for local development)."""


def setup_telemetry() -> None:
    """Initialize telemetry when configured.

    Local runs may not configure telemetry, so this is intentionally a no-op.
    """
    return None
