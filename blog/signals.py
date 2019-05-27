from django.dispatch import receiver
from django.db.models.signals import post_save, m2m_changed
from django.db.models import Value, TextField
from django.contrib.postgres.search import SearchVector
from django.db import transaction
from blog.models import BaseModel, Tag
import operator
from functools import reduce


@receiver(post_save)
def on_save(sender, **kwargs):
    if not issubclass(sender, BaseModel):
        return
    transaction.on_commit(make_updater(kwargs["instance"]))


@receiver(m2m_changed)
def on_m2m_changed(sender, **kwargs):
    instance = kwargs["instance"]
    model = kwargs["model"]
    if model is Tag:
        transaction.on_commit(make_updater(instance))
    elif isinstance(instance, Tag):
        for obj in model.objects.filter(pk__in=kwargs["pk_set"]):
            transaction.on_commit(make_updater(obj))


def make_updater(instance):
    components = instance.index_components()
    pk = instance.pk

    def on_commit():
        search_vectors = []
        for weight, text in list(components.items()):
            search_vectors.append(
                SearchVector(Value(text, output_field=TextField()), weight=weight)
            )
        instance.__class__.objects.filter(pk=pk).update(
            search_document=reduce(operator.add, search_vectors)
        )

    return on_commit
