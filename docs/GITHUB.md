# GitHub operations

GWAY exposes GitHub repository operations under the `github` topic. They use the
shared HTTPX transport and accept either a fine-grained personal access token or a
GitHub App installation access token through the configured GitHub client.

GitHub operations are also classified as `source read` or `source write`.
Inspection operations cover repository metadata, refs, files, pull requests, issues,
reviews, Actions runs/jobs/checks/logs, workflows, releases, variables, and secret
metadata. Mutation operations cover repository variables/secrets, issue and pull
request collaboration, workflow/repository dispatch, releases, refs/branches, and
repository files.

Authorization remains operation-specific: exposing read operations does not imply
write authority. Remote/MCP callers must be authorized for the concrete operation
they invoke. Global no-mutate execution rejects GitHub mutations before network
access.

## Mutation safety

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

The GitHub topic intentionally excludes repository and organization administration
such as collaborators, ownership/visibility, branch protection/rulesets, Actions
security policy, app permissions, webhooks, and authentication/token administration.
Those require a separate administrative capability rather than `source write`.
