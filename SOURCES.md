# Sources and dependency rights disclosure (initial, not a completed legal audit)

Original service foundation generated with disclosed AI assistance; no third-party application code copied. No stock media, datasets, voice models or sample voice recordings have been bundled. examples/catalog.example.json is a deliberately ineligible template, NOT rights evidence.

Runtime libraries: FastAPI (MIT), Starlette (BSD-3-Clause), Pydantic/Pydantic Settings (MIT), Uvicorn (BSD-3-Clause), HTTPX/HTTP Core (BSD-3-Clause), python-multipart (Apache-2.0), boto3/botocore/s3transfer (Apache-2.0), PyYAML (MIT). Transitive packages and resolved versions are recorded in uv.lock and requirements.lock.txt; perform a complete license inventory before submission. Test dependency pytest is MIT. Python is PSF licensed. SQLite is public domain.

Container base: official Python Debian image, with distribution dependencies under their respective licences. FFmpeg build in the container includes libx264; GPL obligations apply to redistribution of that binary (GPL is not AGPL). No FFmpeg binary is copied into this source tree. DejaVu fonts include their font licence. Docker image availability and exact package versions have not yet been tested here.

Storage: standalone MinIO and mc containers are AGPL-3.0 software. The brief explicitly permits MinIO; nevertheless its general preference to avoid AGPL must be clarified/handled before shipping. These are external development services, not imported into the Python service. Replace with another S3-compatible service if that obligation is unacceptable. This is a disclosed limitation, not a blanket commercial-compliance claim.

Optional OpenAI-compatible API adapter: disabled by default, opt-in account/API terms and model/output rights apply; neither commercial clearance nor runtime compatibility has been verified in this run. TTS voice label is a mapping only, not an independently verified accent/gender. No zero-cost claim is made.

Local footage catalogue: operator must supply commercially licensed, consented, safe, non-watermarked source clips and documentary rights links. Boolean flags and a licence name are not proof. Catalog selection cannot replace a rights/content audit.
