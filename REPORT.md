# Implementation report — initial foundation

## Decision and scope
A separate synchronous API process and leased background worker use SQLite WAL transactions. This is appropriate for a single-host prototype and deliberately avoids claiming a distributed production queue. Each accepted request is persisted before 202. Canonical request fingerprints plus a unique idempotency key guarantee concurrent matching submissions refer to one job; changed requests fail safely. A lease token makes stale worker commits fail. Data and storage are abstracted from media-provider calls.

## What is implemented
API, uploads, URL validation with pinned public-IP TLS download, structured safe errors, correlation logging, health/readiness, configurable local/S3 object adapters, CLI batch runner, persistent job progress, exact word-aligned scene-list input and cache-based scene swap. A real FFmpeg command adapter normalizes video and mixes narration, emits SRT and optionally burns captions. It preserves full source frames using dark padding. The local catalog rejects explicitly ineligible rights records, repeats and excluded tags. Selection uses tag overlap, NOT semantic matching.

Narration and word-timestamp transcription are replaceable adapters. The only shipped hosted adapter is disabled by default. Real API compatibility and model rights have not been verified, and no request was made to a paid provider. Fakes are defined in tests only and inject fake audio/video bytes solely to prove orchestration. Passing those tests does not establish that any real video works.

## Evidence and missing requirements
Initial test run evidence is in evidence/. Actual video turnaround, cold/warm performance, cost per minute, relevance, coverage >=3, drift, freeze/black frames, peak memory and render reliability are UNMEASURED, not zero. No Core/Advanced/Outstanding level is claimed. All eight assessment must-haves remain unverified or incomplete. Integration features are code/test evidence only until a real container/S3/media run and public live deployment are verified.

Not implemented: automatic semantic footage search, second-source outage fallback, model-driven safety detection, brand/person disambiguation, color normalization, robust multilingual segmentation/alignment, independent VLM scoring, HMAC callbacks (optional), public ingress rate limiting, retention policy, tenant isolation, ten real varied test videos and a recorded demonstration. Manifest includes models/settings/seed/warnings/rights but costs and exact tool versions still need measurement. A local catalogue field is not legal proof. MinIO licensing is disclosed separately in SOURCES.md.

## Next implementation sequence
Configure a no-cost/approved narration + transcription path, install/locate FFmpeg, supply a small audited commercially usable footage set, execute real tiny render tests, then fix timing/caption/codec defects before attempting the ten-case pack. Add actual footage-provider redundancy and measurable semantic retrieval. Run Compose/S3 integration and implement public auth/limits before deployment. Measure cold/warm one-minute outputs, scene coverage, human ratings and failure cases. Candidate must review, understand and be able to change all AI-assisted code; never claim authorship without disclosure.
