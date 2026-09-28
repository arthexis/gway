# GitHub operations

GWAY exposes GitHub repository operations under the `github` topic. They use the
shared HTTPX transport and accept either a fine-grained personal access token or a
GitHub App installation access token through the configured GitHub client.

GitHub operations classify mutation and administration independently. Ordinary
inspection operations are `source read`; ordinary mutations are `source write`.
Repository-policy and security inspection additionally carries the `admin` topic and
is granted remotely through the separate `source-admin` scope. An admin inspection
is therefore still non-mutating even though it requires higher privilege.

The admin surface covers repository rulesets, branch protection, collaborator
permission metadata, webhook metadata, and repository Actions policy. Ruleset
create/update/delete and complete branch-protection replacement/removal are the
initial administrative mutations. The scopes are additive
rather than hierarchical: `source-admin` does not imply ordinary `source-write`,
and ordinary source access does not imply admin access.

Authorization remains operation-specific. Remote/MCP callers must be authorized for
the concrete operation they invoke. Global no-mutate execution rejects GitHub
mutations before network access, including future admin mutations.

## Mutation safety

Ruleset creation and replacement require one complete explicit policy mapping with
`name`, `target`, `enforcement`, `bypass_actors`, `conditions`, and `rules`.
GWAY rejects partial patch-shaped policies and unsupported fields rather than
silently preserving or weakening omitted policy. Ruleset deletion requires an
explicit numeric ruleset ID.

Branch protection replacement likewise requires the complete GitHub protection
policy, including status checks, admin enforcement, review requirements, restrictions,
linear-history/force-push/deletion/creation controls, conversation resolution, branch
locking, and fork-sync policy. This is intentionally replacement rather than implicit
merge behavior because GitHub replaces several nested arrays/settings on update.
Deleting branch protection requires an explicit branch name. All of these admin
mutations remain subject to the normal no-mutate ceiling.

GWAY does not make repository policy decisions for the caller. Pull-request merge
requires the expected head SHA. File update and delete require the expected blob SHA.
Ref creation requires an explicit target SHA, and the initial surface deliberately
does not provide force-update/reset of an existing ref.

Workflow dispatch requires an explicit ref. Release updates target an explicit
numeric release ID. File mutations use explicit commit messages and may target an
explicit branch.

## Secrets

GitHub never returns Actions secret values; GWAY exposes metadata only. Secret values
are encrypted locally with GitHub's repository public key and are never included in
the operation result.

Secret writes require the optional GitHub dependency:

```console
pip install "gway[github]"
```

This installs PyNaCl for sealed-box encryption without making it a core runtime
dependency.

## Actions job logs

GitHub may answer a job-log request with a redirect to a short-lived signed download
URL. GWAY performs the GitHub API request without following redirects, reads the
Location supplied by GitHub, and fetches that signed URL separately without the
GitHub Authorization header. Arbitrary caller-supplied cross-origin GitHub requests
remain rejected.

## Scope boundary

The `source-admin` surface now includes ruleset and branch-protection
administration in addition to repository-level policy/configuration inspection.
Actions policy writes remain separate follow-up work.

Identity and ownership administration remain excluded: token creation/revocation,
GitHub App permission management, organization administration, repository transfer,
ownership changes, visibility changes, and authentication administration require a
separate security design before they are exposed.
