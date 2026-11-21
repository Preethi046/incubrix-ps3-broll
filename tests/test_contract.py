from pathlib import Path
import yaml
from broll.api import create_app

def test_checked_in_openapi_matches_app(settings):
    contract=yaml.safe_load(Path("openapi.yaml").read_text(encoding="utf-8"))
    assert contract==create_app(settings).openapi()

def test_compose_is_parseable():
    compose=yaml.safe_load(Path("compose.yaml").read_text())
    assert set(compose["services"])=={"api","worker","minio","storage-init"}
    assert compose["services"]["api"]["environment"]["BROLL_STORAGE"]=="s3"
