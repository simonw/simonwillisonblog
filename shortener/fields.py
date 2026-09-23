from django import forms
from django.core.validators import URLValidator
from django.db import models

MAX_URL_LENGTH = 100_000


class LongURLValidator(URLValidator):
    max_length = MAX_URL_LENGTH
    schemes = ["http", "https"]


class LongURLFormField(forms.URLField):
    default_validators = [LongURLValidator()]


class LongURLField(models.URLField):
    # URLField's default validator otherwise limits URLs to 2,048 characters,
    # independently of the database column's max_length.
    default_validators = [LongURLValidator()]

    def formfield(self, **kwargs):
        return super().formfield(**{"form_class": LongURLFormField, **kwargs})
