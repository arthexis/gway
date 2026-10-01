"""Canonical Gway-owned curated security scope definitions."""


_OPERATOR_READ_OPERATIONS = frozenset(
    {
        "survey",
        "help",
        "guide",
        "version",
        "log.sources",
        "log.read",
        "log.tail",
        "log.search",
        "security.whoami",
        "security.scope.current",
        "node",
        "products",
        "extensions",
        "builtins",
        "filter",
        "service.list",
        "service.status",
        "service.statuses",
        "wire.check",
        "sous.chef.list",
        "sous.chef.inspect",
    }
)

_OPERATOR_WRITE_OPERATIONS = frozenset(
    {
        "github.drive",
        "github.create_ruleset",
        "github.update_ruleset",
        "github.delete_ruleset",
        "github.update_branch_protection",
        "github.delete_branch_protection",
        "github.set_actions_permissions",
        "github.set_actions_workflow_permissions",
        "github.set_variable",
        "github.delete_variable",
        "github.set_secret",
        "github.delete_secret",
        "github.create_issue",
        "github.update_issue",
        "github.close_issue",
        "github.reopen_issue",
        "github.comment_issue",
        "github.create_pull",
        "github.update_pull",
        "github.close_pull",
        "github.reopen_pull",
        "github.reply_review_comment",
        "github.add_labels",
        "github.remove_label",
        "github.ready_pull",
        "github.draft_pull",
        "github.merge_pull",
        "github.dispatch_workflow",
        "github.dispatch_repository",
        "github.create_release",
        "github.update_release",
        "github.create_ref",
        "github.create_branch",
        "github.delete_ref",
        "github.delete_branch",
        "github.create_file",
        "github.update_file",
        "github.delete_file",
    }
)


CORE_SCOPE_DEFINITIONS = {
    "full-access": {
        "operations": frozenset({"__all__"}),
        "environment": frozenset({"__all__"}),
    },
    "logs-read": {
        "operations": frozenset(
            {
                "survey",
                "help",
                "guide",
                "version",
                "log.sources",
                "log.read",
                "log.tail",
                "log.search",
                "security.whoami",
                "security.scope.current",
            }
        ),
        "environment": frozenset(),
    },
    "source-read": {
        "operations": frozenset(
            {
                "survey",
                "source",
                "search.source",
                "node.deploy.status",
                "node.release.status",
                "node.queue.status",
            }
        ),
        "environment": frozenset(),
    },
    "source-admin": {
        "operations": frozenset(
            {
                "github.rulesets",
                "github.ruleset",
                "github.create_ruleset",
                "github.update_ruleset",
                "github.delete_ruleset",
                "github.branch_protection",
                "github.update_branch_protection",
                "github.delete_branch_protection",
                "github.collaborators",
                "github.collaborator_permission",
                "github.webhooks",
                "github.webhook",
                "github.actions_permissions",
                "github.actions_workflow_permissions",
                "github.set_actions_permissions",
                "github.set_actions_workflow_permissions",
            }
        ),
        "environment": frozenset(),
    },
    "operator-read": {
        "operations": _OPERATOR_READ_OPERATIONS,
        "environment": frozenset(),
    },
    "operator-write": {
        "operations": _OPERATOR_WRITE_OPERATIONS,
        "environment": frozenset(),
    },
}

CORE_SCOPE_NAMES = frozenset(CORE_SCOPE_DEFINITIONS)


def _definition_signature(scope):
    return (scope.owner, scope.operations, scope.environment)


def _replace_owned(connection, registry, name, definition, *, owner):
    """Replace one owned scope using an existing convergence transaction."""
    row = connection.execute(
        "SELECT id, owner FROM scopes WHERE name = ?",
        (name,),
    ).fetchone()
    if row is None:
        connection.execute(
            "INSERT INTO scopes (name, owner) VALUES (?, ?)",
            (name, owner),
        )
        row = connection.execute(
            "SELECT id, owner FROM scopes WHERE name = ?",
            (name,),
        ).fetchone()
    elif row["owner"] is None:
        connection.execute(
            "UPDATE scopes SET owner = ? WHERE id = ?",
            (owner, row["id"]),
        )
    elif row["owner"] != owner:
        raise ValueError(
            f"Security scope {name} is owned by {row['owner']}, not {owner}"
        )

    scope_id = row["id"]
    operations = registry._grants(definition.get("operations", ()), label="operation")
    environment = registry._grants(definition.get("environment", ()), label="environment")
    connection.execute("DELETE FROM scope_operations WHERE scope_id = ?", (scope_id,))
    connection.execute("DELETE FROM scope_environment WHERE scope_id = ?", (scope_id,))
    connection.executemany(
        "INSERT INTO scope_operations (scope_id, operation) VALUES (?, ?)",
        ((scope_id, operation) for operation in sorted(operations)),
    )
    connection.executemany(
        "INSERT INTO scope_environment (scope_id, variable_name) VALUES (?, ?)",
        ((scope_id, variable) for variable in sorted(environment)),
    )


def converge_scope_registry(
    registry,
    published=(),
    *,
    retire_missing=True,
    report=False,
):
    """Atomically converge only Gway-owned bundled scopes.

    Product/Django/Odoo ingestion exposes operations but no longer publishes
    authorization scopes. Existing generated project scopes are retired during
    writable convergence; user-managed scopes remain untouched.
    """
    del published
    desired = {
        name: ("gway", definition)
        for name, definition in CORE_SCOPE_DEFINITIONS.items()
    }

    with registry.state.connect() as connection:
        before_rows = connection.execute(
            "SELECT id, name, owner FROM scopes ORDER BY name"
        ).fetchall()
        before = {
            row["name"]: registry._row_scope(connection, row)
            for row in before_rows
        }

        for name, (owner, definition) in sorted(desired.items()):
            _replace_owned(connection, registry, name, definition, owner=owner)

        retired = []
        if retire_missing:
            rows = connection.execute(
                "SELECT name FROM scopes WHERE owner LIKE 'project:%'"
            ).fetchall()
            for row in rows:
                connection.execute("DELETE FROM scopes WHERE name = ?", (row["name"],))
                retired.append(row["name"])

        after_rows = connection.execute(
            "SELECT id, name, owner FROM scopes ORDER BY name"
        ).fetchall()
        after = {
            row["name"]: registry._row_scope(connection, row)
            for row in after_rows
        }

    if not report:
        return dict(CORE_SCOPE_DEFINITIONS)

    added = sorted(name for name in desired if name not in before and name in after)
    updated = sorted(
        name
        for name in desired
        if name in before
        and name in after
        and _definition_signature(before[name]) != _definition_signature(after[name])
    )
    unchanged = sorted(
        name
        for name in desired
        if name in before
        and name in after
        and _definition_signature(before[name]) == _definition_signature(after[name])
    )
    return {
        "added": added,
        "updated": updated,
        "retired": sorted(retired),
        "unchanged": unchanged,
        "scopes": sorted(desired),
    }
