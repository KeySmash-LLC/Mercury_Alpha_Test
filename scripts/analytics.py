"""Shared analytics utilities — distinct_id resolution and persistence."""
import os
import sys
import uuid
from pathlib import Path

_DEFAULT_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def get_or_create_distinct_id(env_path: Path | None = None) -> str:
    """Return POSTHOG_DISTINCT_ID from env, generating and persisting a UUID if absent.

    Checks os.environ first. If unset or empty, generates a UUID4, writes it to
    the .env file, sets os.environ["POSTHOG_DISTINCT_ID"], and returns it.

    If the .env file cannot be written (e.g. permission error), the ID is still
    returned and set in os.environ for the lifetime of the process — the next run
    will generate a new one.

    Args:
        env_path: Path to the .env file. Defaults to the project-root .env
                  (one directory above scripts/).

    Returns:
        A non-empty UUID string.
    """
    existing = os.environ.get("POSTHOG_DISTINCT_ID", "").strip()
    if existing:
        return existing

    new_id = str(uuid.uuid4())
    resolved = env_path if env_path is not None else _DEFAULT_ENV_PATH

    try:
        if resolved.exists():
            content = resolved.read_text()
            if "POSTHOG_DISTINCT_ID=" in content:
                lines = [
                    f"POSTHOG_DISTINCT_ID={new_id}" if l.startswith("POSTHOG_DISTINCT_ID=") else l
                    for l in content.splitlines()
                ]
                resolved.write_text("\n".join(lines) + "\n")
            else:
                resolved.write_text(content.rstrip("\n") + f"\nPOSTHOG_DISTINCT_ID={new_id}\n")
        else:
            resolved.write_text(f"POSTHOG_DISTINCT_ID={new_id}\n")
        print(f"[analytics] Generated analytics ID: {new_id} (saved to {resolved})", file=sys.stderr)
    except OSError as e:
        print(f"[analytics] Warning: could not persist analytics ID: {e}", file=sys.stderr)

    os.environ["POSTHOG_DISTINCT_ID"] = new_id
    return new_id


def inject_pipeline_session_id(properties: dict) -> dict:
    """Add session_id from PIPELINE_SESSION_ID env var if not already present.

    When ph-track is invoked from inside a scripts/pipeline subprocess,
    PIPELINE_SESSION_ID is set in the environment so orchestrator events
    are linkable to the run that spawned them.

    Args:
        properties: Event properties dict (mutated in place and returned).

    Returns:
        The same properties dict, possibly with session_id added.
    """
    session_id = os.environ.get("PIPELINE_SESSION_ID", "").strip()
    if session_id and "session_id" not in properties:
        properties["session_id"] = session_id
    return properties


def compute_cost_per_app(total_cost_usd: float, submitted: int) -> float | None:
    """Compute cost per successfully submitted application.

    Args:
        total_cost_usd: Total Claude API spend for the run.
        submitted: Number of applications successfully submitted.

    Returns:
        Cost per app rounded to 4 decimal places, or None if submitted is 0.
    """
    if submitted <= 0:
        return None
    return round(total_cost_usd / submitted, 4)
