"""Optional web application sampler capability."""

from .adapter import HandlerNotFound, InMemoryAdapter, MethodNotAllowed, RouteNotFound
from .application import register
from .appspec import AppSpec, BindingSpec, RouteSpec, ViewSpec
from .exposure import ExposureSpec, LocalAppService
from .server import ApplicationHTTPAdapter, ApplicationRequest, build_app_server, build_server, serve_app

__all__ = [
    "AppSpec",
    "ApplicationHTTPAdapter",
    "ApplicationRequest",
    "BindingSpec",
    "ExposureSpec",
    "HandlerNotFound",
    "InMemoryAdapter",
    "LocalAppService",
    "MethodNotAllowed",
    "RouteNotFound",
    "RouteSpec",
    "ViewSpec",
    "build_app_server",
    "build_server",
    "register",
    "serve_app",
]
