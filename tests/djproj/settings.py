# file: tests/djproj/settings.py
SECRET_KEY = "test"
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
]
DATABASES = {
    "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}
}
