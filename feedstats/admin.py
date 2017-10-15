# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from django.contrib import admin
from .models import SubscriberCount

admin.site.register(
    SubscriberCount,
    list_display=('path', 'user_agent', 'count', 'created'),
)
