# B-roll engine — tested service foundation, not a finished assessment

Current stage: real FastAPI API + separate persistent worker, storage/provider adapters and FFmpeg pipeline code. Runtime default providers intentionally fail with PROVIDER_NOT_CONFIGURED. No actual completed narration-to-B-roll video is claimed. See REPORT.md and evidence/ for exact evidence.

## How it fits together

```text / scene list / audio upload / public HTTPS URL -> API -> SQLite durable queue -> worker
worker -> narration adapter -> timestamped transcription -> phrase scene boundaries
worker -> reviewed local catalogue -> per-scene FFmpeg normalization/cache -> per-ratio assembly
worker -> S3 or local objects -> GET job -> fresh download links
```

The API never performs a render in the request. Worker leases and heartbeat recover interrupted work. A recovered attempt has its own cache directory; stale workers cannot overwrite completed job state. An interrupted external API request may be repeated after a crash: exactly-once external billing is not guaranteed. Job idempotency prevents duplicate queue entries, not all distributed side effects.

## Local quick start (PowerShell, Python 3.12 + uv)

1. uv sync
2. Copy-Item .env.example .env
3. uv run uvicorn broll.api:app --host 127.0.0.1 --port 8000 --no-access-log
4. In another terminal: uv run python -m broll.worker
5. Open http://localhost:8000/api/v1/docs
6. Tests (no keys/network/media downloads): uv run pytest -q
7. Batch: uv run python -m broll.batch examples run-results

Optional container start: copy .env.example to .env, replace local storage secrets, then docker compose up --build. Compose is authored but NOT yet executed; Docker is not available in this worker environment. Image pulls may be large. FFmpeg/ffprobe must be available for actual local media processing. Source catalog path inside compose must be /data/catalog.json and reviewed footage must be staged into the shared volume; there is no automatic stock-media downloader yet.

## API

All product routes are /api/v1. /health and /ready are explicit brief-required exceptions. OpenAPI 3.1 is at /api/v1/openapi.json; checked-in openapi.yaml is generated from the same app (uv run python -m scripts.export_openapi). /api/v1/docs uses the API schema.

POST /api/v1/uploads accepts multipart audio, checks bytes rather than filename and returns upload_id. POST /api/v1/broll/jobs accepts exactly one of audio_url, upload_id, script, scenes. Every POST requires Idempotency-Key; matching retry returns same result/job, changed payload returns 409. GET /api/v1/jobs/{job_id} returns queued/running/succeeded/failed, progress, attempts, safe error and output links. POST /api/v1/broll/jobs/{job_id}/scenes/{scene_id}/swap queues a new job with a replacement catalog clip_id. It reuses unchanged normalized scene files and reassembles the final files, but actual speed improvement is NOT measured.

Optional BROLL_API_TOKEN protects product routes. Blank is local-development-only. Never expose this service publicly without TLS, a nonempty token, an ingress body-size limit and a real per-user/IP rate limiter. Current queue cap provides load shedding, NOT a public-demo rate limit. Jobs are not multi-tenant isolated: a token grants access to all jobs. Local download URLs require the same bearer token; S3 links are time-limited and refreshed when polling status.

## Configuration

Every Settings field in broll/config.py has a BROLL_ environment variable listed in .env.example. Paths are relative to working directory unless absolute. Storage is local or s3. S3 credentials stay in environment. Catalog is an operator-reviewed JSON list (template in examples). TTS/STT default disabled; set each to openai_compatible only after arranging approved provider rights/billing and key. API key must never appear in logs. TTS/STT calls have not been live-tested. Provider model names are configuration, not evidence of successful model use.

Downloads require public HTTPS, no userinfo/non-443 ports, public DNS answers only, certificate verification, bounded streaming, and no redirects. The checked IP is pinned for the actual TLS connection to prevent DNS rebinding. Optional hostname allowlist is recommended. File size limits are enforced while streaming, but the ASGI multipart parser may spool before endpoint checks: enforce ingress body limits before a public deployment. Media duration is checked in the worker. Music-only/silent input is rejected only if transcriber returns no speech; no separate speech/music detector yet.

## Errors

JSON shape: {error:{code,message,retryable,details}}. Codes: VALIDATION_ERROR, HTTP_ERROR, INTERNAL_ERROR, UNAUTHORIZED, INVALID_IDEMPOTENCY_KEY, IDEMPOTENCY_CONFLICT, QUEUE_FULL, INPUT_LIMIT, JOB_NOT_FOUND, JOB_NOT_COMPLETE, SCENE_NOT_FOUND, UPLOAD_NOT_FOUND, INVALID_PATH, FILE_NOT_FOUND, FILE_TOO_LARGE, INVALID_MEDIA, UNSAFE_URL, DOWNLOAD_FAILED, NOT_READY, PROVIDER_NOT_CONFIGURED, AI_PROVIDER_FAILED, VOICE_UNSUPPORTED, NO_SPEECH, NO_AUDIO, AUDIO_DURATION, MEDIA_TOOL_MISSING, RENDER_TIMEOUT, OUTPUT_VALIDATION_FAILED, INVALID_TIMESTAMPS, SCENE_ALIGNMENT_FAILED, FOOTAGE_UNAVAILABLE, NO_RELEVANT_FOOTAGE, SWAP_SOURCE_MISSING, WORKER_INTERRUPTED. Errors deliberately omit submitted text, URLs, provider raw responses and internal paths.

## Important limitations

No live demo, real successful video evidence, semantic footage model, stock-provider fallback, content classifier, colour matching, human relevance scores, independent VLM, Hindi/Tamil verification, production measurements, complete rights audit or distributed object-cache store yet. Caption timing is real STT word timing when available, not guessed reading speed. Scene-list alignment is deliberately strict and errors when ASR text differs. Simple sentence punctuation segmentation is not a semantic model and may fail on ASR without punctuation. Source loops may freeze if catalog media is static; no automatic freeze/black detector exists yet. See SOURCES.md for disclosed dependency/licensing limitations and AI_USE.md for authorship assistance.
