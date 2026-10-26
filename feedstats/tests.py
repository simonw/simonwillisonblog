import datetime

import pytest

from .models import SubscriberCount


@pytest.mark.django_db
class TestFeedstats:
    @pytest.fixture(autouse=True)
    def setup(self, client):
        self.client = client

    def test_feedstats_records_subscriber_numbers(self):
        assert 0 == SubscriberCount.objects.count()
        # If no \d+ subscribers, we don't record anything
        self.client.get("/atom/everything/", HTTP_USER_AGENT="Blah")
        assert 0 == SubscriberCount.objects.count()
        self.client.get("/atom/everything/", HTTP_USER_AGENT="Blah (10 subscribers)")
        assert 1 == SubscriberCount.objects.count()
        row = SubscriberCount.objects.all()[0]
        assert "/atom/everything/" == row.path
        assert 10 == row.count
        assert datetime.date.today() == row.created.date()
        assert "Blah (X subscribers)" == row.user_agent
        # If we hit again with the same number, no new record is recorded
        self.client.get("/atom/everything/", HTTP_USER_AGENT="Blah (10 subscribers)")
        assert 1 == SubscriberCount.objects.count()
        # If we hit again with a different number, we record a new row
        self.client.get("/atom/everything/", HTTP_USER_AGENT="Blah (11 subscribers)")
        assert 2 == SubscriberCount.objects.count()
        row = SubscriberCount.objects.all()[1]
        assert 11 == row.count
        assert "Blah (X subscribers)" == row.user_agent
