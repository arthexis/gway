# file: tests/test_django_models.py
import os

import pytest

pytest.importorskip("django")


def setup_module():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.djproj.settings")
    import django

    django.setup()


def test_access_user_model():
    from gway import gw
    from django.contrib.auth.models import User

    model = gw.django.User
    assert model is User


def test_list_models():
    from gway import gw

    models = gw.django.list_models()
    assert "User" in models

