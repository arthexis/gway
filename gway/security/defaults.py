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


def converge_scope_registry(registry, published=(), *, retire_missing=True):
    """Converge Gway-owned and product-published scopes into one registry."""
    published = dict(published)
    for name, definition in CORE_SCOPE_DEFINITIONS.items():
        registry.replace_owned(
            name,
            owner="gway",
            operations=definition["operations"],
            environment=definition["environment"],
            allow_claim_unowned=True,
        )

    active_product_names = set()
    for name, definition in sorted(published.items()):
        if name in CORE_SCOPE_NAMES:
            raise ValueError(f"Published security scope shadows Gway core scope: {name}")
        source = str(definition.get("source") or "").strip()
        if not source:
            raise ValueError(f"Published security scope {name} has no publisher source")
        owner = f"project:{source}"
        registry.replace_owned(
            name,
            owner=owner,
            operations=definition.get("operations", ()),
            environment=definition.get("environment", ()),
            allow_claim_matching_unowned=True,
        )
        active_product_names.add(name)

    if retire_missing:
        registry.remove_owned_missing(
            owner_prefix="project:",
            active_names=active_product_names,
        )
    return {
        **CORE_SCOPE_DEFINITIONS,
        **published,
    }
