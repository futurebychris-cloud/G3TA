import json
import unittest
from unittest.mock import MagicMock, patch

from services import whisper_service


class WhisperServiceTests(unittest.TestCase):
    @patch.object(whisper_service.urllib.request, "urlopen")
    def test_transcribes_audio_and_labels_a_common_detected_language(self, urlopen):
        response = MagicMock()
        response.read.return_value = json.dumps({
            "text": "Quiero visitar Madrid",
            "language": "es",
        }).encode()
        urlopen.return_value.__enter__.return_value = response

        result = whisper_service.transcribe_speech(b"recorded-audio", "audio/webm")

        self.assertEqual(result, {
            "text": "Quiero visitar Madrid",
            "language": "es",
            "language_name": "Spanish",
            "translated": False,
        })
        request = urlopen.call_args.args[0]
        self.assertIn("task=transcribe", request.full_url)
        self.assertIn(b'name="audio_file"', request.data)
        self.assertIn(b"recorded-audio", request.data)

    @patch.object(whisper_service.urllib.request, "urlopen")
    def test_translate_task_returns_english_text_and_flags_the_source_language(self, urlopen):
        response = MagicMock()
        response.read.return_value = json.dumps({
            "text": "I want to visit Madrid",
            "language": "es",
        }).encode()
        urlopen.return_value.__enter__.return_value = response

        result = whisper_service.transcribe_speech(b"recorded-audio", "audio/webm", task="translate")

        self.assertEqual(result, {
            "text": "I want to visit Madrid",
            "language": "es",
            "language_name": "Spanish",
            "translated": True,
        })
        request = urlopen.call_args.args[0]
        self.assertIn("task=translate", request.full_url)

    @patch.object(whisper_service.urllib.request, "urlopen")
    def test_translate_task_is_not_flagged_when_source_is_already_english(self, urlopen):
        response = MagicMock()
        response.read.return_value = json.dumps({
            "text": "I want to visit Madrid",
            "language": "en",
        }).encode()
        urlopen.return_value.__enter__.return_value = response

        result = whisper_service.transcribe_speech(b"recorded-audio", "audio/webm", task="translate")

        self.assertFalse(result["translated"])


if __name__ == "__main__":
    unittest.main()
