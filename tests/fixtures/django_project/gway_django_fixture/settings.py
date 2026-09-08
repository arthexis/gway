SECRET_KEY = "gway-django-fixture"
DEBUG = False
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "gway_django_fixture.testapp",
]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
