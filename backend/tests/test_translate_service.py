import unittest
from unittest.mock import patch

from services import translate_service


class TranslateServiceTests(unittest.TestCase):
    @patch.object(translate_service, "chat_json")
    def test_translates_into_the_requested_target_language(self, chat_json):
        chat_json.return_value = {"translation": "我想去马德里"}

        result = translate_service.translate_text("Quiero visitar Madrid", "zh")

        self.assertEqual(result, "我想去马德里")
        prompt = chat_json.call_args.args[0]
        self.assertIn("Chinese", prompt)

    @patch.object(translate_service, "chat_json")
    def test_unknown_target_code_falls_back_to_english(self, chat_json):
        chat_json.return_value = {"translation": "I want to visit Madrid"}

        translate_service.translate_text("Quiero visitar Madrid", "fr")

        prompt = chat_json.call_args.args[0]
        self.assertIn("English", prompt)

    @patch.object(translate_service, "chat_json")
    def test_returns_original_text_when_the_model_call_fails(self, chat_json):
        chat_json.side_effect = RuntimeError("no api key")

        result = translate_service.translate_text("Quiero visitar Madrid", "zh")

        self.assertEqual(result, "Quiero visitar Madrid")

    @patch.object(translate_service, "chat_json")
    def test_returns_original_text_when_the_model_returns_no_translation(self, chat_json):
        chat_json.return_value = {}

        result = translate_service.translate_text("Quiero visitar Madrid", "zh")

        self.assertEqual(result, "Quiero visitar Madrid")


if __name__ == "__main__":
    unittest.main()
