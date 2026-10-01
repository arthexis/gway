"""GitHub branch-protection administration."""

from __future__ import annotations

from .base import BaseOperations, segment


class BranchProtectionAdminOperations(BaseOperations):
    """Branch-protection inspection and complete-policy replacement."""

    def branch_protection(self, repository, branch):
        """Return protection policy for one repository branch."""
        return self._github().request(
            "GET",
            f"{self._repo(repository)}/branches/{segment(branch)}/protection",
        ).data

    @staticmethod
    def _branch_protection_policy(policy):
        """Validate and copy one complete branch-protection policy."""
        if not isinstance(policy, dict):
            raise TypeError("GitHub branch protection policy must be a mapping")
        required = {
            "required_status_checks",
            "enforce_admins",
            "required_pull_request_reviews",
            "restrictions",
            "required_linear_history",
            "allow_force_pushes",
            "allow_deletions",
            "block_creations",
            "required_conversation_resolution",
            "lock_branch",
            "allow_fork_syncing",
        }
        missing = required - set(policy)
        extra = set(policy) - required
        if missing:
            raise ValueError(
                "GitHub branch protection policy is missing required fields: "
                + ", ".join(sorted(missing))
            )
        if extra:
            raise ValueError(
                "GitHub branch protection policy contains unsupported fields: "
                + ", ".join(sorted(extra))
            )
        result = dict(policy)
        nested_policies = {
            "required_status_checks": {"strict", "contexts"},
            "required_pull_request_reviews": {
                "dismiss_stale_reviews",
                "require_code_owner_reviews",
                "required_approving_review_count",
                "require_last_push_approval",
            },
            "restrictions": {"users", "teams", "apps"},
        }
        for name, fields in nested_policies.items():
            value = result[name]
            if value is None:
                continue
            if not isinstance(value, dict):
                raise TypeError(
                    f"GitHub branch protection {name} must be a mapping or null"
                )
            missing_nested = fields - set(value)
            extra_nested = set(value) - fields
            if missing_nested:
                raise ValueError(
                    f"GitHub branch protection {name} is missing required fields: "
                    + ", ".join(sorted(missing_nested))
                )
            if extra_nested:
                raise ValueError(
                    f"GitHub branch protection {name} contains unsupported fields: "
                    + ", ".join(sorted(extra_nested))
                )
            result[name] = dict(value)

        status_checks = result["required_status_checks"]
        if status_checks is not None:
            if not isinstance(status_checks["strict"], bool):
                raise TypeError(
                    "GitHub branch protection required_status_checks strict "
                    "must be boolean"
                )
            if not isinstance(status_checks["contexts"], list) or not all(
                isinstance(context, str) for context in status_checks["contexts"]
            ):
                raise TypeError(
                    "GitHub branch protection required_status_checks contexts "
                    "must be a list of strings"
                )
            status_checks["contexts"] = list(status_checks["contexts"])

        reviews = result["required_pull_request_reviews"]
        if reviews is not None:
            for name in (
                "dismiss_stale_reviews",
                "require_code_owner_reviews",
                "require_last_push_approval",
            ):
                if not isinstance(reviews[name], bool):
                    raise TypeError(
                        "GitHub branch protection required_pull_request_reviews "
                        f"{name} must be boolean"
                    )
            count = reviews["required_approving_review_count"]
            if not isinstance(count, int) or isinstance(count, bool):
                raise TypeError(
                    "GitHub branch protection required_pull_request_reviews "
                    "required_approving_review_count must be an integer"
                )

        restrictions = result["restrictions"]
        if restrictions is not None:
            for name in ("users", "teams", "apps"):
                value = restrictions[name]
                if not isinstance(value, list) or not all(
                    isinstance(item, str) for item in value
                ):
                    raise TypeError(
                        f"GitHub branch protection restrictions {name} "
                        "must be a list of strings"
                    )
                restrictions[name] = list(value)
        if not isinstance(result["enforce_admins"], bool):
            raise TypeError("GitHub branch protection enforce_admins must be boolean")
        for name in (
            "required_linear_history",
            "allow_force_pushes",
            "allow_deletions",
            "block_creations",
            "required_conversation_resolution",
            "lock_branch",
            "allow_fork_syncing",
        ):
            if not isinstance(result[name], bool):
                raise TypeError(f"GitHub branch protection {name} must be boolean")
        return result

    def update_branch_protection(self, repository, branch, policy, mutate=True):
        """Replace protection for one explicit branch using a complete policy."""
        if not mutate:
            raise PermissionError("GitHub branch protection mutation is disabled")
        branch = str(branch)
        if not branch:
            raise ValueError("GitHub branch is required")
        payload = self._branch_protection_policy(policy)
        return self._github().request(
            "PUT",
            f"{self._repo(repository)}/branches/{segment(branch)}/protection",
            json=payload,
        ).data

    def delete_branch_protection(self, repository, branch, mutate=True):
        """Delete protection for one explicit branch."""
        if not mutate:
            raise PermissionError("GitHub branch protection mutation is disabled")
        branch = str(branch)
        if not branch:
            raise ValueError("GitHub branch is required")
        self._github().request(
            "DELETE",
            f"{self._repo(repository)}/branches/{segment(branch)}/protection",
        )
        return {
            "repository": str(repository),
            "branch": branch,
            "deleted": True,
        }
