# Pull request state

Pull request workflow state uses GitHub-native state rather than custom work-state labels.

- **Draft** means the change is still being worked on and is not eligible for merge.
- **Ready for review** means implementation is complete but merge has not been authorized.
- **Native auto-merge enabled** is the authorization signal. Enabling auto-merge means the PR may merge once repository protections, CI, freshness, and review requirements allow it.
- **`on-hold`** is the exceptional pause state. Adding it disables native auto-merge. Removing it does not silently restore authorization; auto-merge must be enabled again deliberately.
- **`in-progress`** remains available for Issues, where it represents active issue work. It is not a PR lifecycle state.
- **`approved`** is not used as a PR authorization state.

Branch updates do not claim PRs with a label. The branch-update workflow serializes updates at the repository level, rechecks the PR head, and uses GitHub's expected-head compare-and-swap when requesting an update.

Automated version-rollover PRs are authorized by enabling native auto-merge directly after creation.
