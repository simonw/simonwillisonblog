from django.test import TestCase
from .models import SubscriberCount
import datetime


class FeedstatsTests(TestCase):
    def test_feedstats_records_subscriber_numbers(self):
        self.assertEqual(0, SubscriberCount.objects.count())
        # If no \d+ subscribers, we don't record anything
        self.client.get("/atom/everything/", HTTP_USER_AGENT="Blah")
        self.assertEqual(0, SubscriberCount.objects.count())
        self.client.get("/atom/everything/", HTTP_USER_AGENT="Blah (10 subscribers)")
        self.assertEqual(1, SubscriberCount.objects.count())
        row = SubscriberCount.objects.all()[0]
        self.assertEqual("/atom/everything/", row.path)
        self.assertEqual(10, row.count)
        self.assertEqual(datetime.date.today(), row.created.date())
        self.assertEqual("Blah (X subscribers)", row.user_agent)
        # If we hit again with the same number, no new record is recorded
        self.client.get("/atom/everything/", HTTP_USER_AGENT="Blah (10 subscribers)")
        self.assertEqual(1, SubscriberCount.objects.count())
        # If we hit again with a different number, we record a new row
        self.client.get("/atom/everything/", HTTP_USER_AGENT="Blah (11 subscribers)")
        self.assertEqual(2, SubscriberCount.objects.count())
        row = SubscriberCount.objects.all()[1]
        self.assertEqual(11, row.count)
        self.assertEqual("Blah (X subscribers)", row.user_agent)
