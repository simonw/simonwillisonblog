from django.test import TestCase


class HerokuappHostRedirectTests(TestCase):
    def test_herokuapp_host_redirects_to_canonical_domain(self):
        response = self.client.get(
            "/search/?beat=til&tag=ai",
            HTTP_HOST="simonwillisonblog.herokuapp.com",
        )
        self.assertEqual(response.status_code, 301)
        self.assertEqual(
            response["Location"],
            "https://simonwillison.net/search/?beat=til&tag=ai",
        )

    def test_herokuapp_host_redirect_preserves_path_only(self):
        response = self.client.get(
            "/2024/Dec/9/llama-33-70b/",
            HTTP_HOST="simonwillisonblog.herokuapp.com",
        )
        self.assertEqual(response.status_code, 301)
        self.assertEqual(
            response["Location"],
            "https://simonwillison.net/2024/Dec/9/llama-33-70b/",
        )

    def test_canonical_host_does_not_redirect(self):
        response = self.client.get("/", HTTP_HOST="simonwillison.net")
        self.assertNotEqual(response.status_code, 301)


class NestedPercentEncodingTests(TestCase):
    def test_three_consecutive_percent25_returns_bare_404(self):
        # The middleware short-circuits with an empty-body 404; a normal
        # unmatched URL would go through Django's 404 handler and render
        # a template, producing a non-empty body.
        response = self.client.get("/tags/ai/%25%25%25/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.content, b"")

    def test_deeply_nested_recursive_encoding_returns_bare_404(self):
        # The real-world attack pattern: /tags/ai+openai/%25252525...
        # (a single % followed by many "25"s — recursive re-encoding of %).
        path = "/tags/ai+openai/%25" + "25" * 30 + "/"
        response = self.client.get(path)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.content, b"")

    def test_single_percent25_is_not_blocked(self):
        # One level of percent-encoding is legitimate (e.g. %20 = space).
        # A single %25 in the middle of a URL must NOT trigger the block.
        # We can't easily assert 200 here (the target may not exist), so
        # we check the response body is non-empty — a normal Django 404
        # renders a template, whereas our block returns an empty body.
        response = self.client.get("/this-does-not-exist-%25-oops/")
        self.assertEqual(response.status_code, 404)
        self.assertNotEqual(response.content, b"")

    def test_two_consecutive_percent25_is_not_blocked(self):
        # Two consecutive %25 is suspicious but below our threshold.
        response = self.client.get("/nowhere-%25%25-nope/")
        self.assertEqual(response.status_code, 404)
        self.assertNotEqual(response.content, b"")
