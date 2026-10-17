from django.test import SimpleTestCase

from .services import normalize_phone_number


class PhoneNumberTests(SimpleTestCase):
    def test_local_number_is_normalized(self):
        self.assertEqual(
            normalize_phone_number("0917 123 4567"),
            "+639171234567",
        )

    def test_invalid_number_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_phone_number("12345")
