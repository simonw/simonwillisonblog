from django.db import models
from django.utils.safestring import mark_safe
from markdown import markdown


class Newsletter(models.Model):
    subject = models.CharField(max_length=255)
    body = models.TextField()
    sent_at = models.DateTimeField()

    class Meta:
        ordering = ["-sent_at"]
        get_latest_by = "sent_at"

    def __str__(self):
        return f"{self.subject} ({self.sent_at:%Y-%m-%d})"

    @property
    def body_html(self):
        return mark_safe(markdown(self.body))
