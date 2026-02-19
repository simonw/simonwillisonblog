import itertools
from datetime import timedelta, timezone

import factory
import factory.django
import factory.fuzzy
from django.utils import timezone as django_timezone

_global_slug_counter = itertools.count()


class BaseFactory(factory.django.DjangoModelFactory):
    slug = factory.LazyFunction(lambda: "slug%d" % next(_global_slug_counter))
    created = factory.Faker("past_datetime", tzinfo=timezone.utc)


class EntryFactory(BaseFactory):
    class Meta:
        model = "blog.Entry"

    title = factory.Faker("sentence")


class BlogmarkFactory(BaseFactory):
    class Meta:
        model = "blog.Blogmark"

    link_url = factory.Faker("uri")
    link_title = factory.Faker("sentence")
    commentary = factory.Faker("sentence")


class QuotationFactory(BaseFactory):
    class Meta:
        model = "blog.Quotation"


class NoteFactory(BaseFactory):
    class Meta:
        model = "blog.Note"


class BeatFactory(BaseFactory):
    class Meta:
        model = "blog.Beat"

    beat_type = "release"
    title = factory.Faker("sentence")
    url = factory.Faker("uri")


class GuideFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "blog.Guide"

    title = factory.Faker("sentence")
    slug = factory.LazyFunction(lambda: "slug%d" % next(_global_slug_counter))
    description = factory.Faker("paragraph")


class ChapterFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "blog.Chapter"

    guide = factory.SubFactory(GuideFactory)
    title = factory.Faker("sentence")
    slug = factory.LazyFunction(lambda: "slug%d" % next(_global_slug_counter))
    body = factory.Faker("paragraph")
    order = factory.Sequence(lambda n: n)


class SponsorMessageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "blog.SponsorMessage"

    name = factory.Faker("company")
    message = factory.Faker("sentence")
    learn_more_url = factory.Faker("uri")
    display_from = factory.LazyFunction(
        lambda: django_timezone.now() - timedelta(days=1)
    )
    display_until = factory.LazyFunction(
        lambda: django_timezone.now() + timedelta(days=30)
    )
    is_active = True
    color_scheme = factory.fuzzy.FuzzyChoice(
        ["warm", "lavender", "sage", "slate", "gold", "rose",
         "ocean", "copper", "plum", "mint", "sky", "moss"]
    )
