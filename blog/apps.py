from django.apps import AppConfig
from django.db.models import signals


class BlogConfig(AppConfig):
    name = "blog"

    def ready(self):
        # import signal handlers
        from blog import signals
