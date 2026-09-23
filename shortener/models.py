from django.db import models
from django.urls import reverse

from .fields import MAX_URL_LENGTH, LongURLField


class ShortURL(models.Model):
    url = LongURLField(max_length=MAX_URL_LENGTH)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.description or self.url

    @property
    def short_id(self):
        # Encode the integer itself in base 32, using digits 0-9 and a-v.
        value = 1010 + self.pk
        digits = "0123456789abcdefghijklmnopqrstuv"
        result = ""
        while value:
            value, remainder = divmod(value, 32)
            result = digits[remainder] + result
        return result

    def get_absolute_url(self):
        return reverse("shortener:redirect", kwargs={"short_id": self.short_id})
