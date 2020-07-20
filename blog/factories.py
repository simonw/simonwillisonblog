import factory
import factory.django
import factory.fuzzy
from django.utils.timezone import utc


class BaseFactory(factory.django.DjangoModelFactory):
    slug = factory.Sequence(lambda n: "slug%d" % n)
    created = factory.Faker("past_datetime", tzinfo=utc)


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
