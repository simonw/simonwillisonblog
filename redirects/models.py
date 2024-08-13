from django.db import models


class Redirect(models.Model):
    domain = models.CharField(max_length=128, blank=True)
    path = models.CharField(max_length=128, blank=True)
    target = models.CharField(max_length=256, blank=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["domain", "path"], name="unique_redirect")
        ]

    def __unicode__(self):
        return "%s/%s => %s" % (self.domain, self.path, self.target)
