def __main__(scope=None, only=None, except_=None, since=None, problems=False, changed=False, cursor=None, *, mutate=False):
    """Survey the current node through bounded read-only observations."""


def __help__(topic=None):
    return {
        "summary": "Survey the current node.",
        "description": (
            "Build a bounded structured snapshot from ordinary read-only Gway "
            "operations. Unsupported role-specific sections degrade independently."
        ),
        "examples": [
            "gway survey",
            "gway survey --scope operations-basic",
            "gway survey --only node,services",
            "gway survey --except errors,wire",
            "gway survey --since \"10 minutes ago\"",
            "gway survey --problems",
            "gway survey --changed --cursor <cursor>",
            "gway --json survey",
        ],
        "notes": [
            "The base survey snapshot is read-only.",
            "--scope can only reduce the caller's existing authority.",
            "--only and --except reduce the visible section set after authorization.",
            "--since currently constrains time-aware observations such as recent errors.",
            "--problems keeps only problematic observations and non-empty recent-error logs.",
            "Every survey response includes an opaque cursor for later comparison.",
            "--changed requires --cursor and returns only currently visible changed sections.",
        ],
        "--scope": {
            "summary": "Narrow survey authority",
            "description": (
                "Intersect the caller's current authority with one visible named "
                "security scope. This can never add operation or environment grants."
            ),
            "examples": ["gway survey --scope operations-basic"],
        },
        "--only": {
            "summary": "Include selected survey sections",
            "description": (
                "Keep only the named observation sections after authorization and "
                "scope attenuation. Use a comma-separated section list."
            ),
            "examples": ["gway survey --only node,services"],
        },
        "--except": {
            "summary": "Exclude selected survey sections",
            "description": (
                "Remove the named observation sections after authorization and "
                "scope attenuation. Use a comma-separated section list."
            ),
            "examples": ["gway survey --except errors,wire"],
            "notes": ["--only and --except cannot be used together."],
        },
        "--since": {
            "summary": "Bound time-aware observations",
            "description": (
                "Pass a lower time bound to survey observations that support one. "
                "The base survey currently applies this to recent ERROR/CRITICAL logs."
            ),
            "examples": ["gway survey --since \"10 minutes ago\""],
        },
        "--problems": {
            "summary": "Show only problematic observations",
            "description": (
                "Keep sections whose observation status is error or blocked, plus the "
                "recent errors section when it contains records. Optional unavailable "
                "capabilities are not treated as errors."
            ),
            "examples": ["gway survey --problems"],
        },
        "--changed": {
            "summary": "Show only changed observations",
            "description": (
                "Compare the current visible survey surface with a prior opaque cursor "
                "and return only sections whose fingerprints changed."
            ),
            "examples": ["gway survey --changed --cursor <cursor>"],
            "notes": [
                "Sections no longer visible to the caller are never surfaced as removals."
            ],
        },
        "--cursor": {
            "summary": "Compare against a previous survey snapshot",
            "description": (
                "Opaque versioned survey cursor returned by an earlier invocation. "
                "It contains section fingerprints, not server-side survey state."
            ),
            "examples": ["gway survey --changed --cursor <cursor>"],
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
