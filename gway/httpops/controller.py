"""Reusable HTTP operations backed by GWAY's core HTTP transport."""

from __future__ import annotations

import json as json_module

from ..http import request as transport_request
from ..mutation import MutationError


def _mapping(value, *, label):
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json_module.loads(value)
        except json_module.JSONDecodeError as error:
            raise ValueError(f"{label} must be a JSON object") from error
        if isinstance(parsed, dict):
            return parsed
    raise ValueError(f"{label} must be a mapping or JSON object")


def _json_value(value):
    if value is None or not isinstance(value, str):
        return value
    try:
        return json_module.loads(value)
    except json_module.JSONDecodeError:
        return value


class Controller:
    """Small recipe-friendly HTTP operation surface."""

    @staticmethod
    def _call(
        method,
        url,
        *,
        headers=None,
        params=None,
        json=None,
        data=None,
        timeout=30.0,
        follow_redirects=False,
    ):
        response = transport_request(
            method,
            url,
            headers=_mapping(headers, label="headers"),
            params=_mapping(params, label="params"),
            json=_json_value(json),
            data=data,
            timeout=float(timeout),
            follow_redirects=follow_redirects,
        )
        return response.result()

    def get(
        self,
        url,
        *,
        headers=None,
        params=None,
        timeout=30.0,
        follow_redirects=False,
        mutate=False,
    ):
        """Perform a non-mutating HTTP GET request."""
        del mutate
        return self._call(
            "GET",
            url,
            headers=headers,
            params=params,
            timeout=timeout,
            follow_redirects=follow_redirects,
        )

    def post(
        self,
        url,
        *,
        headers=None,
        params=None,
        json=None,
        data=None,
        timeout=30.0,
        follow_redirects=False,
        mutate=True,
    ):
        """Perform a mutating HTTP POST request."""
        if not mutate:
            raise MutationError("HTTP POST is disabled by non-mutating execution")
        return self._call(
            "POST", url, headers=headers, params=params, json=json, data=data,
            timeout=timeout, follow_redirects=follow_redirects,
        )

    def put(self, url, *, headers=None, params=None, json=None, data=None,
            timeout=30.0, follow_redirects=False, mutate=True):
        """Perform a mutating HTTP PUT request."""
        if not mutate:
            raise MutationError("HTTP PUT is disabled by non-mutating execution")
        return self._call(
            "PUT", url, headers=headers, params=params, json=json, data=data,
            timeout=timeout, follow_redirects=follow_redirects,
        )

    def patch(self, url, *, headers=None, params=None, json=None, data=None,
              timeout=30.0, follow_redirects=False, mutate=True):
        """Perform a mutating HTTP PATCH request."""
        if not mutate:
            raise MutationError("HTTP PATCH is disabled by non-mutating execution")
        return self._call(
            "PATCH", url, headers=headers, params=params, json=json, data=data,
            timeout=timeout, follow_redirects=follow_redirects,
        )

    def delete(self, url, *, headers=None, params=None, json=None, data=None,
               timeout=30.0, follow_redirects=False, mutate=True):
        """Perform a mutating HTTP DELETE request."""
        if not mutate:
            raise MutationError("HTTP DELETE is disabled by non-mutating execution")
        return self._call(
            "DELETE", url, headers=headers, params=params, json=json, data=data,
            timeout=timeout, follow_redirects=follow_redirects,
        )

    def request(
        self,
        url,
        *,
        method="GET",
        headers=None,
        params=None,
        json=None,
        data=None,
        timeout=30.0,
        follow_redirects=False,
        mutate=True,
    ):
        """Perform a generic HTTP request, conservatively classified as mutating."""
        if not mutate:
            raise MutationError("HTTP request is disabled by non-mutating execution")
        return self._call(
            method, url, headers=headers, params=params, json=json, data=data,
            timeout=timeout, follow_redirects=follow_redirects,
        )
