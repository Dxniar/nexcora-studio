import unittest

from orderbot.validation import clean_name, normalize_phone


class ValidationTests(unittest.TestCase):
    def test_valid_phone(self):
        self.assertEqual(normalize_phone("+7 (700) 123-45-67"), "+77001234567")

    def test_invalid_phone(self):
        self.assertIsNone(normalize_phone("123"))
        self.assertIsNone(normalize_phone("+7 abc 700 123 45 67"))

    def test_name(self):
        self.assertEqual(clean_name("  Айша   С.  "), "Айша С.")
        self.assertIsNone(clean_name("A"))
