# G3TA Piper voice service

Build and run the local text-to-speech service:

```bash
docker build -t g3ta-piper:latest ./piper
docker run -d --restart unless-stopped --name g3ta-piper -p 8083:8080 g3ta-piper:latest
```

The G3TA backend defaults to `http://127.0.0.1:8083/synthesize`.
The image selects the correct native Piper binary for Apple Silicon (`arm64`)
or Intel (`amd64`) automatically.

## Authorized custom English voice

A Piper voice consists of both `voice.onnx` and `voice.onnx.json`. Mount a
folder containing those files and point `PIPER_CUSTOM_MODEL` at the model:

```bash
docker run -d --restart unless-stopped --name g3ta-piper -p 8083:8080 \
  -v /absolute/path/to/voice-folder:/custom:ro \
  -e PIPER_CUSTOM_MODEL=/custom/voice.onnx \
  g3ta-piper:latest
```

Only clone or install a voice you own or have explicit permission to use.
