"""GitHub Actions workflow, run, job, check, variable, and secret operations."""

from __future__ import annotations

import base64

from .base import segment
from .github import GitHubError


class ActionsOperations:
    def runs(self, repository, workflow=None, branch=None, status=None):
        """List GitHub Actions runs, optionally filtered by workflow or branch."""
        root = self._repo(repository)
        path = f"{root}/actions/runs"
        if workflow is not None:
            path = f"{root}/actions/workflows/{segment(workflow)}/runs"
        params = {"per_page": 100}
        if branch is not None:
            params["branch"] = branch
        if status is not None:
            params["status"] = status
        return self._all_enveloped(path, "workflow_runs", params=params)

    def run(self, repository, run):
        """Return one GitHub Actions workflow run."""
        return self._github().request(
            "GET", f"{self._repo(repository)}/actions/runs/{int(run)}"
        ).data

    def jobs(self, repository, run):
        """List jobs belonging to a GitHub Actions workflow run."""
        return self._all_enveloped(
            f"{self._repo(repository)}/actions/runs/{int(run)}/jobs",
            "jobs",
            params={"per_page": 100},
        )

    def job(self, repository, job):
        """Return one GitHub Actions job."""
        return self._github().request(
            "GET", f"{self._repo(repository)}/actions/jobs/{int(job)}"
        ).data

    def checks(self, repository, ref):
        """List check runs for a commit or Git ref."""
        return self._all_enveloped(
            f"{self._repo(repository)}/commits/{segment(ref)}/check-runs",
            "check_runs",
            params={"per_page": 100},
        )

    def check(self, repository, check):
        """Return one check run."""
        return self._github().request(
            "GET", f"{self._repo(repository)}/check-runs/{int(check)}"
        ).data

    def check_annotations(self, repository, check):
        """List annotations emitted by one GitHub check run."""
        return self._all(
            f"{self._repo(repository)}/check-runs/{int(check)}/annotations",
            params={"per_page": 100},
        )

    def job_logs(self, repository, job):
        """Return the downloadable log response for one Actions job."""
        response = self._github().download_redirect(
            f"{self._repo(repository)}/actions/jobs/{int(job)}/logs"
        )
        return {
            "status": response.status,
            "content": response.data,
            "content_type": response.headers.get("content-type"),
        }

    def workflows(self, repository):
        """List GitHub Actions workflow definitions."""
        return self._all_enveloped(
            f"{self._repo(repository)}/actions/workflows",
            "workflows",
            params={"per_page": 100},
        )

    def workflow(self, repository, workflow):
        """Return one workflow definition by numeric ID or file name."""
        return self._github().request(
            "GET",
            f"{self._repo(repository)}/actions/workflows/{segment(workflow)}",
        ).data

    def dispatch_workflow(
        self, repository, workflow, ref, inputs=None, mutate=True
    ):
        """Dispatch a GitHub Actions workflow at an explicit ref."""
        if not mutate:
            raise PermissionError("GitHub workflow mutation is disabled")
        payload = {"ref": str(ref)}
        if inputs is not None:
            if not isinstance(inputs, dict):
                raise TypeError("workflow inputs must be a mapping")
            payload["inputs"] = dict(inputs)
        self._github().request(
            "POST",
            f"{self._repo(repository)}/actions/workflows/{segment(workflow)}/dispatches",
            json=payload,
        )
        return {
            "repository": str(repository),
            "workflow": str(workflow),
            "ref": str(ref),
            "dispatched": True,
        }

    def dispatch_repository(self, repository, event, payload=None, mutate=True):
        """Dispatch a repository event with an optional client payload."""
        if not mutate:
            raise PermissionError("GitHub repository mutation is disabled")
        if not str(event):
            raise ValueError("repository dispatch event is required")
        body = {"event_type": str(event)}
        if payload is not None:
            if not isinstance(payload, dict):
                raise TypeError("repository dispatch payload must be a mapping")
            body["client_payload"] = dict(payload)
        self._github().request(
            "POST", f"{self._repo(repository)}/dispatches", json=body
        )
        return {
            "repository": str(repository),
            "event": str(event),
            "dispatched": True,
        }

    def variables(self, repository):
        """List GitHub Actions repository variables and their visible values."""
        return self._all_enveloped(
            f"{self._repo(repository)}/actions/variables",
            "variables",
            params={"per_page": 100},
        )

    def variable(self, repository, name):
        """Return one GitHub Actions repository variable."""
        return self._github().request(
            "GET", f"{self._repo(repository)}/actions/variables/{segment(name)}"
        ).data

    def secrets(self, repository):
        """List Actions secret metadata; secret values are never available."""
        return self._all_enveloped(
            f"{self._repo(repository)}/actions/secrets",
            "secrets",
            params={"per_page": 100},
        )

    def secret(self, repository, name):
        """Return metadata for one Actions secret, never its value."""
        return self._github().request(
            "GET", f"{self._repo(repository)}/actions/secrets/{segment(name)}"
        ).data

    def set_variable(self, repository, name, value, mutate=True):
        """Converge a GitHub Actions repository variable to the requested value."""
        if not mutate:
            raise PermissionError("GitHub variable mutation is disabled")
        root = f"{self._repo(repository)}/actions/variables"
        path = f"{root}/{segment(name)}"
        payload = {"name": str(name), "value": str(value)}
        try:
            self._github().request("GET", path)
        except GitHubError as error:
            if error.status != 404:
                raise
            try:
                self._github().request("POST", root, json=payload)
                return {"name": str(name), "value": str(value), "created": True}
            except GitHubError as create_error:
                if create_error.status not in {409, 422}:
                    raise
                self._github().request("PATCH", path, json=payload)
                return {"name": str(name), "value": str(value), "created": False}
        try:
            self._github().request("PATCH", path, json=payload)
            return {"name": str(name), "value": str(value), "created": False}
        except GitHubError as update_error:
            if update_error.status != 404:
                raise
            self._github().request("POST", root, json=payload)
            return {"name": str(name), "value": str(value), "created": True}

    def delete_variable(self, repository, name, mutate=True):
        """Delete a GitHub Actions repository variable."""
        if not mutate:
            raise PermissionError("GitHub variable mutation is disabled")
        self._github().request(
            "DELETE", f"{self._repo(repository)}/actions/variables/{segment(name)}"
        )
        return {"name": str(name), "deleted": True}

    def secret_key(self, repository):
        """Return the Actions public key used to encrypt repository secrets."""
        return self._github().request(
            "GET", f"{self._repo(repository)}/actions/secrets/public-key"
        ).data

    @staticmethod
    def _encrypt_secret(public_key, value):
        try:
            from nacl import encoding, public
        except ImportError as error:
            raise RuntimeError("GitHub secret writes require PyNaCl") from error
        key = public.PublicKey(str(public_key), encoding.Base64Encoder())
        box = public.SealedBox(key)
        encrypted = box.encrypt(str(value).encode("utf-8"))
        return base64.b64encode(encrypted).decode("ascii")

    def set_secret(self, repository, name, value, mutate=True):
        """Encrypt and set a GitHub Actions repository secret."""
        if not mutate:
            raise PermissionError("GitHub secret mutation is disabled")
        key = self.secret_key(repository)
        if not isinstance(key, dict) or not key.get("key") or not key.get("key_id"):
            raise ValueError("GitHub Actions secret public key response is incomplete")
        encrypted = self._encrypt_secret(key["key"], value)
        self._github().request(
            "PUT",
            f"{self._repo(repository)}/actions/secrets/{segment(name)}",
            json={"encrypted_value": encrypted, "key_id": key["key_id"]},
        )
        return {"name": str(name), "updated": True}

    def delete_secret(self, repository, name, mutate=True):
        """Delete a GitHub Actions repository secret."""
        if not mutate:
            raise PermissionError("GitHub secret mutation is disabled")
        self._github().request(
            "DELETE", f"{self._repo(repository)}/actions/secrets/{segment(name)}"
        )
        return {"name": str(name), "deleted": True}
