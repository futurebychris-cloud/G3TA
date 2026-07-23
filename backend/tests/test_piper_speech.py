import unittest
from unittest.mock import patch

import main


class PiperSpeechEndpointTests(unittest.TestCase):
    @patch.object(main.piper_service, "synthesize_speech", return_value=b"RIFF" + b"\0" * 64)
    def test_speech_endpoint_returns_piper_wav(self, synthesize):
        response = main.speech_synthesize(main.SpeechRequest(
            text="Your trip is ready.",
            language="en-US",
            speed=0.9,
        ))

        self.assertEqual(response.media_type, "audio/wav")
        self.assertTrue(response.body.startswith(b"RIFF"))
        synthesize.assert_called_once_with(
            text="Your trip is ready.",
            language="en",
            speed=0.9,
        )

    @patch.object(main.piper_service, "synthesize_speech", side_effect=RuntimeError("Piper is offline"))
    def test_speech_endpoint_reports_piper_unavailable(self, _synthesize):
        with self.assertRaisesRegex(main.HTTPException, "Piper is offline") as raised:
            main.speech_synthesize(main.SpeechRequest(text="Hello"))
        self.assertEqual(raised.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
