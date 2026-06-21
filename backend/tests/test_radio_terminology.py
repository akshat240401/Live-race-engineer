from __future__ import annotations

import unittest

from app.radio.terminology import normalize_racing_transcript, normalized_message_key


class RacingTerminologyTests(unittest.TestCase):
    def test_common_f1_terms(self) -> None:
        text = normalize_racing_transcript(
            "Engine near, is dear ass available and how are my tires?"
        )
        self.assertIn("engineer", text.casefold())
        self.assertIn("DRS", text)
        self.assertIn("tyres", text)

    def test_duplicate_key_ignores_numbers(self) -> None:
        first = normalized_message_key("DRS available, gap 0.9 seconds")
        second = normalized_message_key("DRS available, gap 0.8 seconds")
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
