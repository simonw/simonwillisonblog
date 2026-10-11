from functools import partial

import pytest
from django.conf import settings
from django.test import override_settings


@pytest.fixture(scope="session", autouse=True)
def fast_test_settings(django_test_environment):
    """Avoid production password and static-serving costs in application tests."""
    with override_settings(
        PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
        MIDDLEWARE=[
            middleware
            for middleware in settings.MIDDLEWARE
            if middleware != "whitenoise.middleware.WhiteNoiseMiddleware"
        ],
        STORAGES={
            **settings.STORAGES,
            "staticfiles": {
                "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
            },
        },
    ):
        yield


@pytest.fixture
def commit_callbacks(db, django_capture_on_commit_callbacks):
    """Emulate a commit after an explicit block without flushing the test database.

    Wrap writes whose on_commit side effects a test needs to observe. Callbacks
    discarded by a rolled-back atomic block are not executed.
    """
    return partial(django_capture_on_commit_callbacks, execute=True)
