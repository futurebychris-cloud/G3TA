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
        })
        request = urlopen.call_args.args[0]
        self.assertIn("task=transcribe", request.full_url)
        self.assertIn(b'name="audio_file"', request.data)
        self.assertIn(b"recorded-audio", request.data)


if __name__ == "__main__":
    unittest.main()
