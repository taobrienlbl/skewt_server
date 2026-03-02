from __future__ import annotations

import os
from pathlib import Path


SITE_CONFIG_PATH = Path(os.getenv("SITE_CONFIG_PATH", "/data/site-config.yml"))

DEFAULT_SITE_CONFIG = {
    "site_code": "USIUB",
    "site_location": "Bloomington, IN",
    "site_latitude": 39.1653,
    "site_longitude": -86.5264,
    "site_long_name": "Indiana University",
}


def _parse_minimal_yaml(text: str) -> dict:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_site_config() -> dict:
    config = dict(DEFAULT_SITE_CONFIG)

    if SITE_CONFIG_PATH.exists():
        text = SITE_CONFIG_PATH.read_text()
        loaded: dict = {}
        try:
            import yaml  # type: ignore

            parsed = yaml.safe_load(text)
            if isinstance(parsed, dict):
                loaded = parsed
        except Exception:
            loaded = _parse_minimal_yaml(text)

        for key in DEFAULT_SITE_CONFIG:
            if key in loaded and loaded[key] not in (None, ""):
                config[key] = loaded[key]

    config["site_latitude"] = float(config["site_latitude"])
    config["site_longitude"] = float(config["site_longitude"])
    config["site_latlon"] = [config["site_latitude"], config["site_longitude"]]
    return config
