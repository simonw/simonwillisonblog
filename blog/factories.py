import itertools

import factory
import factory.django
import factory.fuzzy
from datetime import timezone

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
