# G3TA Piper voice service

Build and run the local text-to-speech service:

```bash
docker build -t g3ta-piper:latest ./piper
docker run -d --restart unless-stopped --name g3ta-piper -p 8083:8080 g3ta-piper:latest
```

The G3TA backend defaults to `http://127.0.0.1:8083/synthesize`.
The image selects the correct native Piper binary for Apple Silicon (`arm64`)
or Intel (`amd64`) automatically.

## Bundled voices

English uses `en_US-lessac-high` (the "high" quality tier, 22.05kHz) — noticeably
less of the synthetic vowel "shimmer" that makes "medium" tier TTS sound robotic,
at the cost of a slightly larger model and slower synthesis. Mandarin uses
`zh_CN-huayan-medium`, the best quality tier currently published for that voice.
Rebuild after changing the Dockerfile: `docker build -t g3ta-piper:latest ./piper`.

If you want to try a different voice character (not just a higher quality tier of
the same one), the community-ranked list at
[quick-tts.com/blog/piper-voices-ranked.html](https://quick-tts.com/blog/piper-voices-ranked.html)
and the official samples at
[rhasspy.github.io/piper-samples](https://rhasspy.github.io/piper-samples/) are
good starting points — listen before committing, since "high" tier and "sounds
natural" don't always line up. `en_US-libritts_r-medium` is frequently cited as
the most natural-sounding general-purpose English option, but it's a 904-speaker
model with no documented default speaker, so budget time to sample a few speaker
IDs (see `PIPER_EN_SPEAKER` below) before adopting it.

## Authorized custom English voice

A Piper voice consists of both `voice.onnx` and `voice.onnx.json`. Mount a
folder containing those files and point `PIPER_CUSTOM_MODEL` (or `PIPER_EN_MODEL` /
`PIPER_ZH_MODEL`) at the model:

```bash
docker run -d --restart unless-stopped --name g3ta-piper -p 8083:8080 \
  -v /absolute/path/to/voice-folder:/custom:ro \
  -e PIPER_CUSTOM_MODEL=/custom/voice.onnx \
  g3ta-piper:latest
```

For a multi-speaker model (like `libritts_r`), also set `PIPER_EN_SPEAKER` (or
`PIPER_ZH_SPEAKER`) to a speaker index from the voice's `speaker_id_map` —
without it, Piper silently uses speaker `0`, which is rarely the best-sounding one:

```bash
docker run -d --restart unless-stopped --name g3ta-piper -p 8083:8080 \
  -v /absolute/path/to/voice-folder:/custom:ro \
  -e PIPER_CUSTOM_MODEL=/custom/en_US-libritts_r-medium.onnx \
  -e PIPER_EN_SPEAKER=123 \
  g3ta-piper:latest
```

Check `GET /health` to confirm which model and speaker are actually active.

Only clone or install a voice you own or have explicit permission to use.
