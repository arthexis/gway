"""Canonical Gway-owned security scope definitions."""


CORE_SCOPE_DEFINITIONS = {
    "full-access": {
        "operations": frozenset({"__all__"}),
        "environment": frozenset({"__all__"}),
    },
    "logs-read": {
        "operations": frozenset(
            {
                "watch",
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
                "watch",
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
        "operations": frozenset(
            {
                "watch",
                "node",
                "products",
                "extensions",
                "service.list",
                "service.status",
                "service.statuses",
                "wire.check",
                "sous.chef.list",
                "sous.chef.inspect",
            }
        ),
        "environment": frozenset(),
    },
}

CORE_SCOPE_NAMES = frozenset(CORE_SCOPE_DEFINITIONS)


def converge_scope_registry(registry, published=()):
    """Converge Gway-owned and product-published scopes into one registry."""
    definitions = dict(CORE_SCOPE_DEFINITIONS)
    for name, definition in dict(published).items():
        if name in CORE_SCOPE_NAMES:
            raise ValueError(f"Published security scope shadows Gway core scope: {name}")
        definitions[name] = {
            "operations": frozenset(definition.get("operations", ())),
            "environment": frozenset(definition.get("environment", ())),
        }

    for name, definition in definitions.items():
        registry.replace(
            name,
            operations=definition["operations"],
            environment=definition["environment"],
        )
    return definitions
