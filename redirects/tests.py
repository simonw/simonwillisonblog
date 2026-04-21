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
