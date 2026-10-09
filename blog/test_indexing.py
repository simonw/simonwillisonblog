import pytest
from django.contrib.postgres.search import SearchQuery
from django.db import transaction

from .factories import EntryFactory
from .models import Entry


def test_indexing_waits_for_commit_callbacks(commit_callbacks):
    with commit_callbacks() as callbacks:
        entry = EntryFactory(title="Pangolin", body="<p>Capybara</p>")
        assert not Entry.objects.filter(
            search_document=SearchQuery("pangolin")
        ).exists()

    assert callbacks
    assert Entry.objects.get(search_document=SearchQuery("pangolin")) == entry


def test_rolled_back_writes_discard_index_callbacks(commit_callbacks):
    with commit_callbacks() as callbacks:
        with pytest.raises(ValueError, match="abort"):
            with transaction.atomic():
                EntryFactory(title="Pangolin")
                raise ValueError("abort")

    assert callbacks == []
    assert not Entry.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_indexing_runs_after_a_real_commit():
    with transaction.atomic():
        entry = EntryFactory(title="Pangolin")
        assert not Entry.objects.filter(
            search_document=SearchQuery("pangolin")
        ).exists()

    assert Entry.objects.get(search_document=SearchQuery("pangolin")) == entry
