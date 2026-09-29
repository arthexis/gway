def __main__(scope=None, only=None, except_=None, since=None, errors_=False, changed=False, cursor=None, *, mutate=False):
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
            "gway watch --only node,services",
            "gway watch --except errors,wire",
            "gway watch --since \"10 minutes ago\"",
            "gway watch --errors",
            "gway watch --changed --cursor <cursor>",
            "gway --json watch",
        ],
        "notes": [
            "The base watch snapshot is read-only.",
            "--scope can only reduce the caller's existing authority.",
            "--only and --except reduce the visible section set after authorization.",
            "--since currently constrains time-aware observations such as recent errors.",
            "--errors keeps only problematic observations and non-empty recent-error logs.",
            "Every watch response includes an opaque cursor for later comparison.",
            "--changed requires --cursor and returns only currently visible changed sections.",
        ],
        "--scope": {
            "summary": "Narrow watch authority",
            "description": (
                "Intersect the caller's current authority with one visible named "
                "security scope. This can never add operation or environment grants."
            ),
            "examples": ["gway watch --scope operations-basic"],
        },
        "--only": {
            "summary": "Include selected watch sections",
            "description": (
                "Keep only the named observation sections after authorization and "
                "scope attenuation. Use a comma-separated section list."
            ),
            "examples": ["gway watch --only node,services"],
        },
        "--except": {
            "summary": "Exclude selected watch sections",
            "description": (
                "Remove the named observation sections after authorization and "
                "scope attenuation. Use a comma-separated section list."
            ),
            "examples": ["gway watch --except errors,wire"],
            "notes": ["--only and --except cannot be used together."],
        },
        "--since": {
            "summary": "Bound time-aware observations",
            "description": (
                "Pass a lower time bound to watch observations that support one. "
                "The base watch currently applies this to recent ERROR/CRITICAL logs."
            ),
            "examples": ["gway watch --since \"10 minutes ago\""],
        },
        "--errors": {
            "summary": "Show only problematic observations",
            "description": (
                "Keep sections whose observation status is error or blocked, plus the "
                "recent errors section when it contains records. Optional unavailable "
                "capabilities are not treated as errors."
            ),
            "examples": ["gway watch --errors"],
        },
        "--changed": {
            "summary": "Show only changed observations",
            "description": (
                "Compare the current visible watch surface with a prior opaque cursor "
                "and return only sections whose fingerprints changed."
            ),
            "examples": ["gway watch --changed --cursor <cursor>"],
            "notes": [
                "Sections no longer visible to the caller are never surfaced as removals."
            ],
        },
        "--cursor": {
            "summary": "Compare against a previous watch snapshot",
            "description": (
                "Opaque versioned watch cursor returned by an earlier invocation. "
                "It contains section fingerprints, not server-side watch state."
            ),
            "examples": ["gway watch --changed --cursor <cursor>"],
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
