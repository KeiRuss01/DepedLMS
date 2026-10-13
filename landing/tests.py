from django.test import TestCase
from django.urls import reverse


class AppEntryTests(TestCase):
    def test_normal_browser_root_keeps_public_website(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "home.html")
        self.assertContains(response, "navbar-toggler")
        self.assertContains(response, "site-footer")

    def test_app_entry_shows_splash_and_enables_clean_login(self):
        splash_response = self.client.get(reverse("app_entry"))
        self.assertEqual(splash_response.status_code, 200)
        self.assertTemplateUsed(splash_response, "app_splash.html")
        self.assertContains(splash_response, "Preparing your classroom")

        login_response = self.client.get(reverse("accounts:login") + "?app=1")
        self.assertEqual(login_response.status_code, 200)
        self.assertNotContains(login_response, "navbar-toggler")
        self.assertNotContains(login_response, "site-footer")
        self.assertContains(login_response, "Classroom Portal")

    def test_normal_browser_login_keeps_public_navigation_and_footer(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "navbar-toggler")
        self.assertContains(response, "site-footer")

    def test_app_signup_uses_the_same_clean_application_shell(self):
        self.client.get(reverse("app_entry"))
        response = self.client.get(reverse("accounts:signup"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "navbar-toggler")
        self.assertNotContains(response, "site-footer")
        self.assertContains(response, "Create Account")
