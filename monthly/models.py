from django.db import models


class Newsletter(models.Model):
    subject = models.CharField(max_length=255)
    body = models.TextField()
    sent_at = models.DateTimeField()

    class Meta:
        ordering = ["-sent_at"]
        get_latest_by = "sent_at"

    def __str__(self):
        return f"{self.subject} ({self.sent_at:%Y-%m-%d})"
