from django.contrib import admin
from .models import SubscriberCount

admin.site.register(
    SubscriberCount,
    list_display=("path", "user_agent", "count", "created"),
    list_filter=("path", "created"),
)
