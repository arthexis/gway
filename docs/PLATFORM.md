# GWAY Platform Boundary

GWAY is the platform adaptation and composition layer beneath applications such as Arthexis.

A useful ownership rule is:

> GWAY follows the platform. Applications follow the business.

GWAY should absorb changes driven by the host/runtime environment: Python packaging, operating-system behavior, systemd/service supervision, networking, WireGuard, displays and hardware adapters, provisioning, installation, recipes, execution context, and reusable operational safety mechanisms.

Application repositories should own durable domain concepts and workflows. For Arthexis, that includes chargers/connectors, charging sessions and meter values, RFID/account/vehicle attribution, customers/sites, authorization, reporting, fleet identity, and business-state reconciliation.

## What belongs in GWAY

Prefer GWAY when the capability is reusable across applications or exists primarily because the platform changes.

Examples include:

- semantic command dispatch and callable adaptation;
- recipes and sigil/context resolution;
- managed project installation;
- service supervision;
- filesystem/render transaction journals;
- platform/network adapters;
- reusable hardware/display/RFID adapters;
- machine-role composition built from ordinary GWAY primitives;
- recipe-scoped dependency environments.

Keep independently useful third-party or small adapter libraries separate when that is the cleaner boundary. GWAY can consume them rather than absorbing their implementation.

## What does not belong in GWAY

Do not move application-domain policy into GWAY merely because GWAY can execute it.

For Arthexis, GWAY should not own:

- customer/site/charger business identity;
- charging-session models;
- reporting rules;
- historical RFID/vehicle attribution;
- charger authorization policy;
- fleet ownership or replacement history;
- domain-specific reconciliation decisions.

GWAY may provide the operations and recipes that let Arthexis implement those workflows safely.

## Composition over bespoke provisioning

GWAY should use upstream operating-system tools rather than compete with them. In particular, host imaging and first OS boot belong to platform tooling such as Raspberry Pi Imager/Connect. GWAY provisioning begins once a supported host OS is usable.

Higher-level host roles should compose ordinary GWAY mechanisms rather than introduce a second hard-coded provisioning framework.

The intended direction for specialized hosts is conceptually:

~~~text
supported host OS
→ install GWAY
→ compose platform capabilities
→ install/configure application
→ application enrollment/domain identity
~~~

Role composition and application identity are deliberately separate concerns.

## Documentation ownership

The top-level README is an orientation and quick-start document.

This `docs/` directory owns user-facing behavioral guides and architectural boundaries.

`docs/RECIPES.md` is authoritative for the recipe language implemented on the active branch.

`AGENTS.md` is a maintainer/automation operating guide. It should record implementation invariants and validation rules, not become a second user manual or roadmap.

GitHub issues own planned work. Do not document roadmap syntax as implemented behavior before the parser/runtime and tests support it.

## Current roadmap connection

Current platform-direction issues include recipe-scoped dependency environments, machine-role composition, portable RFID procedure cards, and consolidation of older experimental platform repositories.

Those issues may change while they are implemented. This document intentionally records only the stable ownership boundary that should remain true across those changes.
