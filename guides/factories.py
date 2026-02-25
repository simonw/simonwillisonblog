import factory
import factory.django
from blog.factories import BaseFactory, _global_slug_counter


class GuideFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "guides.Guide"

    title = factory.Faker("sentence")
    slug = factory.LazyFunction(lambda: "slug%d" % next(_global_slug_counter))
    description = factory.Faker("paragraph")


class GuideSectionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "guides.GuideSection"

    guide = factory.SubFactory(GuideFactory)
    title = factory.Faker("sentence")
    slug = factory.LazyFunction(lambda: "slug%d" % next(_global_slug_counter))
    order = factory.Sequence(lambda n: n)


class ChapterFactory(BaseFactory):
    class Meta:
        model = "guides.Chapter"

    guide = factory.SubFactory(GuideFactory)
    title = factory.Faker("sentence")
    body = factory.Faker("paragraph")
    order = factory.Sequence(lambda n: n)
