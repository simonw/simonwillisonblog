# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from django.db import models


class SubscriberCount(models.Model):
    path = models.CharField(max_length=128)
    count = models.IntegerField()
    created = models.DateTimeField(auto_now_add=True)
    user_agent = models.CharField(max_length=128, db_index=True)

    class Meta:
        index_together = [
            ['path', 'user_agent', 'count', 'created'],
        ]
