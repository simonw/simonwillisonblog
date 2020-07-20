from django.contrib import admin
from .models import Redirect

admin.site.register(Redirect, list_display=("domain", "path", "target"))
