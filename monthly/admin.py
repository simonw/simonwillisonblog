from django.contrib import admin

from .models import Newsletter


@admin.register(Newsletter)
class NewsletterAdmin(admin.ModelAdmin):
    list_display = ("subject", "sent_at")
    ordering = ("-sent_at",)
    fields = ("subject", "body", "sent_at")
