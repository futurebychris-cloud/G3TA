FROM python:3.11-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends wget ca-certificates libgomp1 \
 && rm -rf /var/lib/apt/lists/*

ARG PIPER_VER=2023.11.14-2
ARG TARGETARCH=arm64
RUN case "${TARGETARCH}" in \
      arm64) PIPER_ARCH=aarch64 ;; \
      amd64) PIPER_ARCH=x86_64 ;; \
      *) echo "Unsupported architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac \
 && wget -qO /tmp/piper.tar.gz \
      "https://github.com/rhasspy/piper/releases/download/${PIPER_VER}/piper_linux_${PIPER_ARCH}.tar.gz" \
 && tar -xzf /tmp/piper.tar.gz -C /opt \
 && rm /tmp/piper.tar.gz \
 && /opt/piper/piper --help >/dev/null 2>&1 || true

ARG HF=https://huggingface.co/rhasspy/piper-voices/resolve/main
RUN mkdir -p /models \
 && wget -qO /models/en_US-lessac-medium.onnx      "${HF}/en/en_US/lessac/medium/en_US-lessac-medium.onnx" \
 && wget -qO /models/en_US-lessac-medium.onnx.json "${HF}/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json" \
 && wget -qO /models/zh_CN-huayan-medium.onnx      "${HF}/zh/zh_CN/huayan/medium/zh_CN-huayan-medium.onnx" \
 && wget -qO /models/zh_CN-huayan-medium.onnx.json "${HF}/zh/zh_CN/huayan/medium/zh_CN-huayan-medium.onnx.json"

RUN pip install --no-cache-dir "flask>=3,<4"
RUN mkdir -p /cache

WORKDIR /app
COPY server.py /app/

ENV LD_LIBRARY_PATH=/opt/piper
EXPOSE 8080
CMD ["python", "server.py"]
