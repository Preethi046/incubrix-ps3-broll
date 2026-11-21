# Understand the foundation before submitting

This folder is not yet a finished video product. It is a working service skeleton with real processing code and offline tests. A passing fake-adapter test checks the plumbing; it does not mean a real video was made.

## Five ideas

1. An API is an HTTP interface. broll/api.py accepts a request, validates it and returns a tracking number (job_id), not a video immediately.
2. A background worker is a separate process. broll/worker.py repeatedly asks SQLite for a queued job and runs its pipeline. Closing the API does not erase the queue.
3. Idempotency means a retry with the same key and same request does not create another job. A changed request under the same key is rejected. broll/db.py uses a database uniqueness constraint and transaction so two simultaneous requests are safe.
4. An adapter wraps a replaceable provider. broll/providers.py defines narration, transcription and footage boundaries. The default narration/transcription providers deliberately report that they are not configured. Test-only fakes are in tests/, never in production configuration.
5. A timeline records what happens when. Speech recognition supplies actual word timestamps. broll/media.py groups sentence endings and fills narration-time gaps between scenes; it does not guess timing from reading speed. Footage retrieval is still a simple tag baseline and is NOT semantic understanding.

## Trace one output

POST body aspect_ratios enters JobInput validation -> canonical JSON is persisted by JobStore.submit -> Worker claims a lease -> Pipeline reads requested ratios -> MediaTools renders each cached scene at that ratio -> assembled files are copied to object storage -> GET job creates fresh download links. A scene swap creates another job, reuses unchanged scene files and encodes the changed scene; final files still need assembly. Actual speed savings remain unmeasured.

## Which files to read first

Start with tests/test_api.py, then broll/models.py, broll/api.py, broll/db.py, broll/worker.py, broll/pipeline.py, broll/providers.py and broll/media.py. Read test_pipeline.py carefully: it explicitly creates invalid test-only video bytes to test orchestration, not media quality. Then read REPORT.md for remaining work and SOURCES.md/AI_USE.md for rights and assistance disclosures.

## Safe next run

Use the local setup in README.md and run uv run pytest -q. Submitting examples/script.json with default settings should create a job and then fail clearly with PROVIDER_NOT_CONFIGURED. That failure is expected and honest. Do not mark the assessment's text/audio must-have as passed until you have configured and exercised real providers and saved actual output evidence.
