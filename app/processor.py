from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import sounderpy as spy
from metpy.calc import wind_components
from metpy.units import units

from app.site_config import load_site_config


WORK_DIR = Path(os.getenv("WORK_DIR", "/data/work"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "/data/output"))
WEB_IMAGES_DIR = Path(os.getenv("WEB_IMAGES_DIR", "/data/web/images"))
WEB_SHARPY_DIR = Path(os.getenv("WEB_SHARPY_DIR", "/data/web/sharpy"))
MANIFEST_PATH = Path(os.getenv("MANIFEST_PATH", "/data/web/manifest.json"))
SHARPY_NAME_RE = re.compile(r"SHARP+Y\.txt$", re.IGNORECASE)
SHARPY_FILE_META_RE = re.compile(
    r"^(?P<site>[A-Za-z0-9]+)_(?P<date>\d{8})_(?P<hour>\d{2})Z_.*SHARP+Y\.txt$",
    re.IGNORECASE,
)


@dataclass
class ProcessResult:
    source: Path
    image_name: str
    sharpy_name: str
    created: bool
    file_meta: dict


def _safe_name(relative_path: Path) -> str:
    stem = relative_path.name
    if stem.lower().endswith(".txt"):
        stem = stem[:-4]
    flattened = f"{relative_path.parent.as_posix()}__{stem}" if relative_path.parent.as_posix() != "." else stem
    flattened = re.sub(r"[^A-Za-z0-9_.-]+", "_", flattened)
    return flattened


def _file_meta(path: Path, site_cfg: dict) -> dict:
    match = SHARPY_FILE_META_RE.match(path.name)
    if not match:
        return {
            "site_code": site_cfg["site_code"],
            "launch_iso": None,
            "launch_label": "Unknown launch time",
            "launch_unix": None,
        }

    site_code = match.group("site").upper()
    launch_dt = datetime.strptime(
        f"{match.group('date')}{match.group('hour')}",
        "%Y%m%d%H",
    ).replace(tzinfo=timezone.utc)
    launch_label = launch_dt.strftime("%d %b %Y | %H00Z").upper()
    return {
        "site_code": site_code,
        "launch_iso": launch_dt.isoformat(),
        "launch_label": launch_label,
        "launch_unix": launch_dt.timestamp(),
    }


def _parse_sharpy(path: Path, site_cfg: dict, file_meta: dict) -> dict:
    lines = path.read_text(errors="ignore").splitlines()

    data_started = False
    rows: list[list[float]] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("%RAW%"):
            data_started = True
            continue
        if not data_started:
            continue
        if line.startswith("%END%"):
            break

        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 6:
            continue

        try:
            values = [float(parts[i]) for i in range(6)]
        except ValueError:
            continue

        if values[0] <= 0:
            continue
        rows.append(values)

    if len(rows) < 5:
        raise ValueError(f"Not enough valid sounding levels in {path}")

    arr = np.array(rows)
    pres = arr[:, 0] * units.hectopascal
    hght = arr[:, 1] * units.meter
    temp = arr[:, 2] * units.degC
    dwpt = arr[:, 3] * units.degC
    wdir = arr[:, 4] * units.degree
    wspd = arr[:, 5] * units.knots

    u_wind, v_wind = wind_components(wspd, wdir)

    clean_data = {
        "T": temp,
        "Td": dwpt,
        "z": hght,
        "p": pres,
        "u": u_wind,
        "v": v_wind,
        "site_info": {
            "site-id": file_meta["site_code"],
            "site-name": site_cfg["site_long_name"],
            "site-latlon": site_cfg["site_latlon"],
            "site-elv": float(hght.m[0]),
            "source": "SHARPY",
            "model": "FILE",
            "fcst-hour": "F000",
            "run-time": (
                datetime.fromisoformat(file_meta["launch_iso"]).strftime("%Y-%m-%d %H:%MZ")
                if file_meta["launch_iso"]
                else datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%MZ")
            ),
            "valid-time": (
                datetime.fromisoformat(file_meta["launch_iso"]).strftime("%Y-%m-%d %H:%MZ")
                if file_meta["launch_iso"]
                else datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%MZ")
            ),
            "box_area": "",
        },
        "titles": {
            "top_title": f"{site_cfg['site_long_name']} | {site_cfg['site_code']}",
            "left_title": file_meta["launch_label"],
            "right_title": (
                f"{site_cfg['site_location'].upper()} "
                f"[{site_cfg['site_latitude']:.2f}, {site_cfg['site_longitude']:.2f}]"
            ),
        },
    }

    return clean_data


def _plot_to_png(clean_data: dict, out_png: Path) -> None:
    out_png.parent.mkdir(parents=True, exist_ok=True)

    plot = spy.build_sounding(clean_data, color_blind=True, dark_mode=False, save=False)
    if hasattr(plot, "savefig"):
        plot.savefig(out_png, dpi=160, bbox_inches="tight")
        try:
            import matplotlib.pyplot as plt

            plt.close("all")
        except Exception:
            pass
        return

    # Fallback for APIs that only save by base filename.
    base = out_png.with_suffix("")
    spy.build_sounding(clean_data, color_blind=True, dark_mode=False, save=True, filename=str(base))


def _manifest_entry(source: Path, image_name: str, sharpy_name: str, file_meta: dict) -> dict:
    image_path = WEB_IMAGES_DIR / image_name
    mtime = image_path.stat().st_mtime if image_path.exists() else source.stat().st_mtime
    return {
        "id": image_name.removesuffix(".png"),
        "image": f"images/{image_name}",
        "sharpy": f"sharpy/{sharpy_name}",
        "source": str(source),
        "site_code": file_meta["site_code"],
        "launch_iso": file_meta["launch_iso"],
        "launch_label": file_meta["launch_label"],
        "launch_unix": file_meta["launch_unix"],
        "updated_unix": mtime,
        "updated_iso": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(),
    }


def process_one(source: Path, site_cfg: dict) -> ProcessResult:
    rel = source.relative_to(WORK_DIR)
    name = _safe_name(rel)
    image_name = f"{name}.png"
    sharpy_name = f"{name}.txt"
    file_meta = _file_meta(source, site_cfg)

    out_png = OUTPUT_DIR / image_name
    web_png = WEB_IMAGES_DIR / image_name
    web_txt = WEB_SHARPY_DIR / sharpy_name

    created = False
    if not out_png.exists():
        clean_data = _parse_sharpy(source, site_cfg, file_meta)
        _plot_to_png(clean_data, out_png)
        created = True

    web_png.parent.mkdir(parents=True, exist_ok=True)
    web_txt.parent.mkdir(parents=True, exist_ok=True)

    if not web_png.exists() or out_png.stat().st_mtime > web_png.stat().st_mtime:
        shutil.copy2(out_png, web_png)
    if not web_txt.exists() or source.stat().st_mtime > web_txt.stat().st_mtime:
        shutil.copy2(source, web_txt)

    return ProcessResult(
        source=source,
        image_name=image_name,
        sharpy_name=sharpy_name,
        created=created,
        file_meta=file_meta,
    )


def write_manifest(entries: list[dict], site_cfg: dict) -> None:
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(entries),
        "site": {
            "site_code": site_cfg["site_code"],
            "site_long_name": site_cfg["site_long_name"],
            "site_location": site_cfg["site_location"],
            "site_latitude": site_cfg["site_latitude"],
            "site_longitude": site_cfg["site_longitude"],
        },
        "items": sorted(
            entries,
            key=lambda x: (
                x["launch_unix"] is not None,
                x["launch_unix"] if x["launch_unix"] is not None else x["updated_unix"],
            ),
            reverse=True,
        ),
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(payload, indent=2))


def run() -> int:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    WEB_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    WEB_SHARPY_DIR.mkdir(parents=True, exist_ok=True)
    site_cfg = load_site_config()

    files = sorted(
        p for p in WORK_DIR.rglob("*.txt") if p.is_file() and SHARPY_NAME_RE.search(p.name)
    )
    entries: list[dict] = []

    for src in files:
        if not src.is_file():
            continue
        try:
            result = process_one(src, site_cfg)
            entries.append(
                _manifest_entry(
                    result.source,
                    result.image_name,
                    result.sharpy_name,
                    result.file_meta,
                )
            )
            state = "created" if result.created else "skipped"
            print(f"[{state}] {src}")
        except Exception as exc:
            print(f"[error] {src}: {exc}")

    write_manifest(entries, site_cfg)
    print(f"Processed {len(files)} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
