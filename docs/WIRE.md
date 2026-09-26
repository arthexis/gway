# Wire migration compatibility map

This document records the public `gway-wire` surface that the maintained GWAY
Wire capability must preserve while the standalone project is retired.

Parent issue: #1130.

## Naming

Legacy project identity:

- canonical project: `wire`
- compatibility aliases: `wireguard`, `wg`
- Python namespace: `gway_wire`
- legacy Python compatibility namespace: `gway_wireguard`

The GWAY migration should keep `wire` as the canonical command family and
preserve `wireguard` / `wg` aliases where they remain unambiguous.

## Root surface

| Legacy command | Compatibility target | Notes |
| --- | --- | --- |
| `wire status` | preserve | Cheap configured topology snapshot; no reconciliation by default. |
| `wire status --server` | preserve | Restrict to configured server relationships. |
| `wire status --client` | preserve | Restrict to configured client relationships. |
| `wire status --debug` | preserve | Add live/diagnostic detail. |
| `wire sync` | preserve | Reconcile configured relationships. |
| `wire sync --domain DOMAIN` | preserve | Limit reconciliation to one domain across roles. |
| `wire check ...` | preserve if practical | Shorthand for server readiness checks without explicit `server` prefix. |

Top-level status returns role-keyed maps and must remain read-only. Top-level
sync is mutating/reconciling.

## Client surface

| Legacy command | Compatibility target | Notes |
| --- | --- | --- |
| `wire client status` | preserve | Persisted client state by default. |
| `wire client status --debug` | preserve | Adds live WireGuard detail. |
| `wire client sync` | preserve | Reconcile persisted client state with live protocol state. |
| `wire client enroll --device ID --token TOKEN` | preserve | One-time-token enrollment. |
| `wire client enroll --token-file PATH` | preserve | Preferred secret-safe CLI path. |
| `wire client enroll --url HOST_OR_URL` | preserve | Host shorthand expands to the enrollment path. |

Enrollment must continue to reuse an already persisted client identity and VPN
allocation when the relationship is already configured.

## Server surface

| Legacy command | Compatibility target | Notes |
| --- | --- | --- |
| `wire server status` | preserve | Static configured server snapshot. |
| `wire server check DOMAIN` | preserve | Read-only readiness/preflight. |
| `wire server deploy DOMAIN` | preserve semantically | Provision/reconcile server plus optional public readiness gate. |
| `wire server token --device ID` | preserve | Issue one-time enrollment token. |
| `wire server devices` | preserve | List registered devices. |
| `wire server revoke ID` | preserve | Revoke one device/peer without disturbing others. |
| `wire server hosts sync` | preserve | Reconcile private short-hostname state. |

The old `validate` spelling is an alias of `server check`; keep it only if it
remains cheap and unambiguous.

## DNS surface

| Legacy command | Compatibility target | Notes |
| --- | --- | --- |
| `wire server dns status` | preserve | Provider-neutral DNS status. |
| `wire server dns sync` | preserve | Reconcile operational and device records. |
| `wire server dns ensure DEVICE` | preserve | Ensure explicit device record. |
| `wire server dns delete DEVICE` | preserve | Remove explicit device record. |

DNS credentials stay server-side. DNS cleanup must never restore network access
for a revoked peer.

## Readiness/check vocabulary

Legacy server checks include independently selectable checks for:

- source/installability;
- static config;
- WireGuard interface/runtime;
- UDP listener;
- enrollment service;
- web/public exposure;
- DNS provider state;
- TLS;
- public reachability;
- managed peers.

No flags means run the complete applicable check set. Status remains cheaper
than check.

## State model to preserve during migration

Legacy state supports both:

- the original single-instance state under `/etc/gway-wireguard`;
- domain-scoped multi-relationship state under:
  - `/etc/gway-wireguard/servers/*.env`
  - `/etc/gway-wireguard/clients/<domain>/`

The new sampler may introduce a cleaner GWAY-owned durable representation, but
migration must be able to read or deliberately import the legacy layout before
the standalone project is retired.

## Behavioral invariants harvested from legacy tests

The migration must retain these behaviors:

1. Status does not run live subprocesses unless debug detail is requested.
2. Root status can aggregate multiple server/client domains and filter by role.
3. Root sync can limit reconciliation to one domain across both roles.
4. Enrollment fails closed when a local token cannot be validated safely.
5. A token created on the same client device is rejected for self-enrollment.
6. Existing/manual WireGuard peers are preserved; allocation works around them.
7. Revocation is peer-scoped and does not depend on successful DNS cleanup.
8. DNS/provider aliases must agree when multiple spellings are supplied.
9. Unsupported providers are rejected before mutation.
10. Server check can preflight a fresh domain without performing deployment.
11. Server deploy may enforce a production-domain/DNS readiness gate.
12. Private key/token material must not be logged or copied into public results.

## Ownership changes in the new GWAY implementation

The old project contains responsibilities that should now compose from existing
GWAY primitives instead of being copied wholesale:

- installation/package requirements -> recipe `require` / host package primitives;
- service lifecycle -> GWAY service operations;
- filesystem writes -> GWAY render/copy/link/remove with rollback where needed;
- public DNS -> existing provider-neutral GWAY DNS capability;
- public web/TLS exposure -> existing GWAY exposure primitives;
- logging -> GWAY logging;
- secrets/config -> semantic GWAY bindings;
- readiness aggregation -> sampler operations that compose component-owned checks.

Wire-specific code should remain limited to endpoint identity, key/peer state,
WireGuard configuration semantics, enrollment, topology reconciliation, and
Wire-owned status/check interpretation.

## Planned migration chunks

### W2 — local WireGuard provisioning

Create the maintained `sampler/wire` capability and preserve the root/client/
server command family with the smallest local-only implementation first.

### W3 — enrollment

Port token issuance, client enrollment, deterministic address allocation, and
client-config generation while preserving the public command spelling above.

### W4 — reconciliation and revocation

Port multi-peer reconciliation, topology status/sync, independent revocation,
and legacy-state import/read compatibility.

### W5 — DNS/public composition

Compose existing GWAY DNS and public exposure primitives rather than carrying
the old `gway-web` dependency forward.

### W6 — compatibility acceptance

Run representative legacy command workflows against the new sampler and keep
aliases/thin wrappers only where they materially reduce migration friction.

### W7 — archive standalone project

After acceptance, update #981/#1130, move any remaining owning defects to GWAY
or Arthexis, and mark `gway-wire` legacy/archival.
