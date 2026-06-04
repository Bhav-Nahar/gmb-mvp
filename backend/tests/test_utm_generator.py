import unittest
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.utm_generator import generate_utm_link, _clean_value

class UTMGeneratorTests(unittest.TestCase):
    def test_clean_value(self):
        self.assertEqual(_clean_value("  Hello World  "), "hello_world")
        self.assertEqual(_clean_value("Offer"), "offer")
        self.assertEqual(_clean_value("Multiple   Spaces"), "multiple___spaces")
        self.assertEqual(_clean_value(None), "")
        self.assertEqual(_clean_value(""), "")

    def test_generate_utm_link_basic(self):
        base_url = "https://example.com/product"
        url = generate_utm_link(base_url, "123", "offer")
        self.assertEqual(url, "https://example.com/product?utm_source=google&utm_medium=organic&utm_campaign=gbp_123&utm_content=offer")

    def test_generate_utm_link_preserve_existing(self):
        base_url = "https://example.com/product?id=123&category=books"
        url = generate_utm_link(base_url, "loc_1", "Event")
        self.assertIn("id=123", url)
        self.assertIn("category=books", url)
        self.assertIn("utm_source=google", url)
        self.assertIn("utm_campaign=gbp_loc_1", url)
        self.assertIn("utm_content=event", url)
        self.assertTrue(url.startswith("https://example.com/product?id=123&category=books&utm_source=google"))

    def test_generate_utm_link_overwrite_existing_utm(self):
        base_url = "https://example.com/product?utm_source=facebook&utm_campaign=old&utm_content=old&id=123"
        url = generate_utm_link(base_url, "456", "update")
        self.assertIn("id=123", url)
        self.assertIn("utm_source=google", url)
        self.assertIn("utm_campaign=gbp_456", url)
        self.assertIn("utm_content=update", url)
        self.assertNotIn("facebook", url)
        self.assertNotIn("old", url)

    def test_generate_utm_link_empty_url(self):
        self.assertIsNone(generate_utm_link("", "123", "cta"))
        self.assertIsNone(generate_utm_link(None, "123", "cta"))

if __name__ == "__main__":
    unittest.main()
