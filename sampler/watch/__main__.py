def __main__(scope=None, *, mutate=False):
    """Inspect the current node through bounded read-only observations."""


def __help__(topic=None):
    return {
        "summary": "Inspect the current node.",
        "description": (
            "Build a bounded structured snapshot from ordinary read-only Gway "
            "operations. Unsupported role-specific sections degrade independently."
        ),
        "examples": [
            "gway watch",
            "gway watch --scope operations-basic",
            "gway --json watch",
        ],
        "notes": [
            "The base watch snapshot is read-only.",
            "--scope can only reduce the caller's existing authority.",
            "Filtering and incremental observation are added in the next chunk.",
        ],
        "--scope": {
            "summary": "Narrow watch authority",
            "description": (
                "Intersect the caller's current authority with one visible named "
                "security scope. This can never add operation or environment grants."
            ),
            "examples": ["gway watch --scope operations-basic"],
        },
        "node": {
            "description": "Generic node role, project, and running Gway identity."
        },
        "health": {
            "description": (
                "Summary of observation-section states. Unavailable optional sections "
                "do not by themselves mark the snapshot degraded."
            )
        },
        "services": {
            "description": "Aggregate runtime state for installed managed services."
        },
        "deploy": {
            "description": "Watchtower-owned deployment observation when available."
        },
        "release": {
            "description": "Watchtower-owned release reconciliation observation."
        },
        "queue": {
            "description": "Watchtower coordinated repository queue observation."
        },
        "wire": {
            "description": "Wire readiness observation when the capability is available."
        },
        "errors": {
            "description": (
                "At most 20 recent ERROR or CRITICAL log records from managed sources."
            )
        },
    }
