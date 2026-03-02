from __future__ import annotations

import json
import os
from pathlib import Path

from flask import Flask, abort, render_template, send_from_directory

from app.site_config import load_site_config


def create_app() -> Flask:
    app = Flask(__name__, template_folder="/app/templates", static_folder="/app/static")

    web_images = Path(os.getenv("WEB_IMAGES_DIR", "/data/web/images"))
    web_sharpy = Path(os.getenv("WEB_SHARPY_DIR", "/data/web/sharpy"))
    manifest_path = Path(os.getenv("MANIFEST_PATH", "/data/web/manifest.json"))

    @app.get("/")
    def index():
        items = []
        site = load_site_config()
        if manifest_path.exists():
            try:
                payload = json.loads(manifest_path.read_text())
                items = payload.get("items", [])
                if isinstance(payload.get("site"), dict):
                    site.update(payload["site"])
            except Exception:
                items = []

        latest = items[0] if items else None
        rest = items[1:] if len(items) > 1 else []
        return render_template("index.html", latest=latest, items=rest, total=len(items), site=site)

    @app.get("/images/<path:filename>")
    def images(filename: str):
        full = web_images / filename
        if not full.exists():
            abort(404)
        return send_from_directory(web_images, filename)

    @app.get("/sharpy/<path:filename>")
    def sharpy(filename: str):
        full = web_sharpy / filename
        if not full.exists():
            abort(404)
        return send_from_directory(web_sharpy, filename, as_attachment=True)

    return app
