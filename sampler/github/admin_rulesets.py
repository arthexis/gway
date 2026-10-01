"""GitHub repository ruleset administration."""

from __future__ import annotations

from .base import BaseOperations


class RulesetAdminOperations(BaseOperations):
    """Repository ruleset inspection and complete-policy replacement."""

    def rulesets(self, repository):
        """List repository rulesets; requires repository administration authority."""
        return self._all(
            f"{self._repo(repository)}/rulesets",
            params={"per_page": 100},
        )

    def ruleset(self, repository, ruleset):
        """Return one repository ruleset by numeric ID."""
        return self._github().request(
            "GET",
            f"{self._repo(repository)}/rulesets/{int(ruleset)}",
        ).data

    @staticmethod
    def _ruleset_policy(policy):
        """Validate and copy a complete repository ruleset policy."""
        if not isinstance(policy, dict):
            raise TypeError("GitHub ruleset policy must be a mapping")
        required = {
            "name",
            "target",
            "enforcement",
            "bypass_actors",
            "conditions",
            "rules",
        }
        missing = required - set(policy)
        extra = set(policy) - required
        if missing:
            raise ValueError(
                "GitHub ruleset policy is missing required fields: "
                + ", ".join(sorted(missing))
            )
        if extra:
            raise ValueError(
                "GitHub ruleset policy contains unsupported fields: "
                + ", ".join(sorted(extra))
            )
        result = dict(policy)
        for name in ("name", "target", "enforcement"):
            if not str(result[name]).strip():
                raise ValueError(f"GitHub ruleset policy {name} is required")
            result[name] = str(result[name])
        if not isinstance(result["bypass_actors"], list):
            raise TypeError("GitHub ruleset bypass_actors must be a list")
        if not isinstance(result["conditions"], dict):
            raise TypeError("GitHub ruleset conditions must be a mapping")
        if not isinstance(result["rules"], list):
            raise TypeError("GitHub ruleset rules must be a list")
        result["bypass_actors"] = list(result["bypass_actors"])
        result["conditions"] = dict(result["conditions"])
        result["rules"] = list(result["rules"])
        return result

    def create_ruleset(self, repository, policy, mutate=True):
        """Create a repository ruleset from one complete explicit policy."""
        if not mutate:
            raise PermissionError("GitHub ruleset mutation is disabled")
        payload = self._ruleset_policy(policy)
        return self._github().request(
            "POST",
            f"{self._repo(repository)}/rulesets",
            json=payload,
        ).data

    def update_ruleset(self, repository, ruleset, policy, mutate=True):
        """Replace one repository ruleset with a complete explicit policy."""
        if not mutate:
            raise PermissionError("GitHub ruleset mutation is disabled")
        payload = self._ruleset_policy(policy)
        return self._github().request(
            "PUT",
            f"{self._repo(repository)}/rulesets/{int(ruleset)}",
            json=payload,
        ).data

    def delete_ruleset(self, repository, ruleset, mutate=True):
        """Delete one repository ruleset by explicit numeric ID."""
        if not mutate:
            raise PermissionError("GitHub ruleset mutation is disabled")
        ruleset = int(ruleset)
        self._github().request(
            "DELETE",
            f"{self._repo(repository)}/rulesets/{ruleset}",
        )
        return {
            "repository": str(repository),
            "ruleset": ruleset,
            "deleted": True,
        }
