FROM apify/actor-python:3.13
USER root
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /models && chown myuser:myuser /models
USER myuser
COPY --chown=myuser:myuser requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# Bake both Whisper models into the image so runs start fast and never hit the model hub.
RUN python -c "from faster_whisper import download_model as d; d('base', output_dir='/models/base'); d('small', output_dir='/models/small')"
ENV WHISPER_MODEL_DIR=/models HF_HUB_OFFLINE=1
COPY --chown=myuser:myuser . ./
RUN python -m compileall -q src/
CMD ["python3", "-m", "src"]
