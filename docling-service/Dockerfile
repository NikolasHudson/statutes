# Docling extraction microservice — its own App Platform component so the
# PyTorch + model-weight footprint stays out of the Django API image.
# Digest-pinned (#23) so the base can't drift under us between builds; the tag is
# kept in the comment for readability. Resolved 2026-06-02 (multi-arch index
# digest). To bump: re-resolve the python:3.12-slim manifest-list digest and
# update both the digest and the comment.
FROM python:3.12-slim@sha256:090ba77e2958f6af52a5341f788b50b032dd4ca28377d2893dcf1ecbdfdfe203

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

# docling's PDF backend needs a couple of native libs (image/graphics) that
# aren't in the slim base.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
# --require-hashes: requirements.txt is a fully-pinned, hashed lock compiled
# from requirements.in (pip-compile --generate-hashes). A hash mismatch or any
# unpinned/extra package fails the build instead of silently installing an
# untested version. Regenerate the lock with pip-compile, never hand-edit it.
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

# Unprivileged runtime user (#24/#7/#23): a parsing bug in docling's PDF/PyTorch
# stack processes untrusted uploads, so an in-process RCE must not land as root.
# Created before the model download so the weights are owned by (and readable by)
# the runtime user without a later chown of the multi-GB tree.
RUN useradd -m -u 10001 app

# Bake the model weights into the image at build time so the running container
# never has to fetch them on a cold start (and so it works without outbound
# network). The converter is pointed here via DOCLING_ARTIFACTS_PATH. Owned by
# the unprivileged user so it can read them at runtime.
ENV DOCLING_ARTIFACTS_PATH=/opt/docling-models
RUN mkdir -p "$DOCLING_ARTIFACTS_PATH" && chown -R app:app "$DOCLING_ARTIFACTS_PATH"
USER app
RUN docling-tools models download -o "$DOCLING_ARTIFACTS_PATH"

COPY --chown=app:app app.py ./

# App Platform convention: bind 8080. This component is internal-only (see
# .do/app.yaml internal_ports), so the port is reachable on the app LAN, not
# the public internet. Single worker — the model is memory-heavy, so scale by
# instance_count rather than packing workers into one container. OCR stays off
# (DOCLING_OCR unset) to keep the parser attack surface and footprint minimal.
EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
