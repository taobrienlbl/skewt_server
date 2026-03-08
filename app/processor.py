from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import sounderpy as spy
from metpy.calc import wind_components
from metpy.units import units

from app.globus_transfer import GlobusConfig, get_task_status, submit_delivery, transfer_enabled
from app.site_config import load_site_config


WORK_DIR = Path(os.getenv("WORK_DIR", "/data/work"))
INGEST_DIR = Path(os.getenv("INGEST_DIR", "/data/ingest"))
DELIVERY_DIR = Path(os.getenv("DELIVERY_DIR", "/data/deliveries"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "/data/output"))
WEB_IMAGES_DIR = Path(os.getenv("WEB_IMAGES_DIR", "/data/web/images"))
WEB_SHARPY_DIR = Path(os.getenv("WEB_SHARPY_DIR", "/data/web/sharpy"))
MANIFEST_PATH = Path(os.getenv("MANIFEST_PATH", "/data/web/manifest.json"))
STATE_PATH = Path(os.getenv("STATE_PATH", "/data/state/launches.json"))
UPLOAD_STABILITY_SECONDS = max(0, int(os.getenv("UPLOAD_STABILITY_SECONDS", "120")))
LAUNCH_DIR_MINUTE_OFFSET = int(os.getenv("LAUNCH_DIR_MINUTE_OFFSET", "0"))

GROUPED_FILE_RE = re.compile(
    r"^(?P<prefix>.+)_(?P<kind>SUMMARY|SHARPPY|TEMP|BUFR\d+)\.(?P<ext>txt|bufr)$",
    re.IGNORECASE,
)
SUMMARY_LAUNCHED_RE = re.compile(
    r"^Launched \(UTC\)\s*:\s*(?P<value>\d{1,2}/\d{1,2}/\d{4}\s+\d{2}:\d{2}:\d{2})\s*$",
    re.MULTILINE,
)
SUMMARY_STATION_RE = re.compile(r"^Station Name\s*:\s*(?P<value>\S+)\s*$", re.MULTILINE)


@dataclass
class LaunchFiles:
    prefix: str
    summary: Path
    sharppy: Path
    temp: Path
    bufr: list[Path]


@dataclass
class ProcessResult:
    image_name: str
    sharpy_name: str
    created: bool


def _load_state() -> dict:
    if not STATE_PATH.exists():
        return {"launches": {}}
    try:
        payload = json.loads(STATE_PATH.read_text())
    except Exception:
        return {"launches": {}}
    if not isinstance(payload, dict):
        return {"launches": {}}
    payload.setdefault("launches", {})
    return payload


def _write_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True))


def _discover_launch_groups() -> dict[str, dict[str, object]]:
    groups: dict[str, dict[str, object]] = {}
    for path in sorted(INGEST_DIR.iterdir()):
        if not path.is_file():
            continue
        match = GROUPED_FILE_RE.match(path.name)
        if not match:
            continue
        prefix = match.group("prefix")
        kind = match.group("kind").upper()
        group = groups.setdefault(prefix, {"summary": None, "sharppy": None, "temp": None, "bufr": []})
        if kind == "SUMMARY":
            group["summary"] = path
        elif kind == "SHARPPY":
            group["sharppy"] = path
        elif kind == "TEMP":
            group["temp"] = path
        else:
            group["bufr"].append(path)
    return groups


def _collect_launch_files(group_key: str, payload: dict[str, object]) -> tuple[LaunchFiles | None, str]:
    summary = payload.get("summary")
    sharppy = payload.get("sharppy")
    temp = payload.get("temp")
    bufr = sorted(payload.get("bufr", []))
    missing: list[str] = []
    if not isinstance(summary, Path):
        missing.append("SUMMARY")
    if not isinstance(sharppy, Path):
        missing.append("SHARPPY")
    if not isinstance(temp, Path):
        missing.append("TEMP")
    if len(bufr) < 4:
        missing.append(f"BUFR ({len(bufr)}/4)")
    if missing:
        return None, f"Waiting for files: {', '.join(missing)}"
    launch_files = LaunchFiles(
        prefix=group_key,
        summary=summary,
        sharppy=sharppy,
        temp=temp,
        bufr=bufr,
    )
    return launch_files, ""


def _parse_launch_meta(files: LaunchFiles, site_cfg: dict) -> dict:
    text = files.summary.read_text(errors="ignore")

    launched_match = SUMMARY_LAUNCHED_RE.search(text)
    if not launched_match:
        raise ValueError(f"Missing launch time in {files.summary.name}")

    station_match = SUMMARY_STATION_RE.search(text)
    launch_dt = datetime.strptime(launched_match.group("value"), "%m/%d/%Y %H:%M:%S").replace(
        tzinfo=timezone.utc
    )
    folder_dt = launch_dt + timedelta(minutes=LAUNCH_DIR_MINUTE_OFFSET)
    site_code = (station_match.group("value") if station_match else site_cfg["site_code"]).upper()
    launch_label = launch_dt.strftime("%d %b %Y | %H%MZ").upper()
    launch_folder = folder_dt.strftime("%Y%m%d_%H%M")
    relative_dir = Path(site_code) / launch_folder
    launch_id = f"{site_code}_{launch_folder}"

    return {
        "launch_id": launch_id,
        "site_code": site_code,
        "launch_iso": launch_dt.isoformat(),
        "launch_label": launch_label,
        "launch_unix": launch_dt.timestamp(),
        "delivery_relative_dir": relative_dir.as_posix(),
        "group_key": files.prefix,
    }


def _files_fingerprint(files: LaunchFiles) -> dict[str, dict[str, float | int]]:
    fingerprint: dict[str, dict[str, float | int]] = {}
    for path in [files.summary, files.sharppy, files.temp, *files.bufr]:
        stat = path.stat()
        fingerprint[path.name] = {"mtime": stat.st_mtime, "size": stat.st_size}
    return fingerprint


def _files_are_stable(files: LaunchFiles) -> bool:
    if UPLOAD_STABILITY_SECONDS <= 0:
        return True
    cutoff = datetime.now(timezone.utc).timestamp() - UPLOAD_STABILITY_SECONDS
    for path in [files.summary, files.sharppy, files.temp, *files.bufr]:
        if path.stat().st_mtime > cutoff:
            return False
    return True


def _package_delivery(files: LaunchFiles, meta: dict, record: dict) -> Path:
    delivery_dir = DELIVERY_DIR / meta["delivery_relative_dir"]
    delivery_dir.mkdir(parents=True, exist_ok=True)

    for source in [files.sharppy, files.temp, *files.bufr]:
        target = delivery_dir / source.name
        if not target.exists() or source.stat().st_mtime > target.stat().st_mtime:
            shutil.copy2(source, target)

    record["delivery_path"] = str(delivery_dir)
    record["delivery_relative_dir"] = meta["delivery_relative_dir"]
    record["source_summary"] = str(files.summary)
    record["source_sharppy"] = str(files.sharppy)
    record["source_temp"] = str(files.temp)
    record["source_bufr"] = [str(path) for path in files.bufr]
    record["last_seen_files"] = _files_fingerprint(files)
    return delivery_dir


def _normalize_transfer_status(record: dict, globus_cfg: GlobusConfig) -> None:
    if not transfer_enabled(globus_cfg):
        record["transfer_status"] = "disabled"
        record["transfer_detail"] = "Globus transfer disabled"
        return

    task_id = record.get("transfer_task_id")
    if not task_id:
        record["transfer_status"] = "ready_to_transfer"
        record["transfer_detail"] = "Launch files are ready"
        return

    status = get_task_status(globus_cfg, str(task_id))
    record["transfer_status"] = status.code
    record["transfer_detail"] = status.detail or ""
    if status.code == "succeeded":
        record["transfer_completed_at"] = datetime.now(timezone.utc).isoformat()
    elif status.code == "failed":
        record["transfer_error"] = status.detail or "Transfer failed"


def _submit_transfer(record: dict, globus_cfg: GlobusConfig) -> None:
    relative_dir = str(record["delivery_relative_dir"])
    submission = submit_delivery(
        globus_cfg,
        relative_dir,
        label=f"Radiosonde launch {record['launch_id']}",
    )
    record["transfer_status"] = "transfer_submitted"
    record["transfer_task_id"] = submission.task_id
    record["transfer_submitted_at"] = datetime.now(timezone.utc).isoformat()
    record["transfer_detail"] = f"Submitted task {submission.task_id}"
    record.pop("transfer_error", None)


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def _parse_sharpy(path: Path, site_cfg: dict, launch_meta: dict) -> dict:
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

        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 6:
            continue

        try:
            values = [float(parts[index]) for index in range(6)]
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

    launch_iso = launch_meta["launch_iso"]
    run_time = datetime.fromisoformat(launch_iso).strftime("%Y-%m-%d %H:%MZ")
    return {
        "T": temp,
        "Td": dwpt,
        "z": hght,
        "p": pres,
        "u": u_wind,
        "v": v_wind,
        "site_info": {
            "site-id": launch_meta["site_code"],
            "site-name": site_cfg["site_long_name"],
            "site-latlon": site_cfg["site_latlon"],
            "site-elv": float(hght.m[0]),
            "source": "SHARPY",
            "model": "FILE",
            "fcst-hour": "F000",
            "run-time": run_time,
            "valid-time": run_time,
            "box_area": "",
        },
        "titles": {
            "top_title": f"{site_cfg['site_long_name']} | {site_cfg['site_code']}",
            "left_title": launch_meta["launch_label"],
            "right_title": (
                f"{site_cfg['site_location'].upper()} "
                f"[{site_cfg['site_latitude']:.2f}, {site_cfg['site_longitude']:.2f}]"
            ),
        },
    }


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

    base = out_png.with_suffix("")
    spy.build_sounding(clean_data, color_blind=True, dark_mode=False, save=True, filename=str(base))


def process_one(sharppy_source: Path, launch_meta: dict, site_cfg: dict) -> ProcessResult:
    name = _safe_name(launch_meta["launch_id"])
    image_name = f"{name}.png"
    sharpy_name = f"{name}.txt"
    out_png = OUTPUT_DIR / image_name
    web_png = WEB_IMAGES_DIR / image_name
    web_txt = WEB_SHARPY_DIR / sharpy_name

    created = False
    if not out_png.exists() or sharppy_source.stat().st_mtime > out_png.stat().st_mtime:
        clean_data = _parse_sharpy(sharppy_source, site_cfg, launch_meta)
        _plot_to_png(clean_data, out_png)
        created = True

    web_png.parent.mkdir(parents=True, exist_ok=True)
    web_txt.parent.mkdir(parents=True, exist_ok=True)

    if not web_png.exists() or out_png.stat().st_mtime > web_png.stat().st_mtime:
        shutil.copy2(out_png, web_png)
    if not web_txt.exists() or sharppy_source.stat().st_mtime > web_txt.stat().st_mtime:
        shutil.copy2(sharppy_source, web_txt)

    return ProcessResult(image_name=image_name, sharpy_name=sharpy_name, created=created)


def _manifest_entry(record: dict) -> dict:
    image_name = record.get("image_name")
    sharpy_name = record.get("sharpy_name")
    updated_unix = record.get("launch_unix")
    if image_name:
        image_path = WEB_IMAGES_DIR / image_name
        if image_path.exists():
            updated_unix = image_path.stat().st_mtime

    updated_unix = float(updated_unix or datetime.now(timezone.utc).timestamp())
    return {
        "id": record["launch_id"],
        "image": f"images/{image_name}" if image_name else None,
        "sharpy": f"sharpy/{sharpy_name}" if sharpy_name else None,
        "source": record.get("source_sharppy"),
        "delivery_path": record.get("delivery_path"),
        "site_code": record["site_code"],
        "launch_iso": record["launch_iso"],
        "launch_label": record["launch_label"],
        "launch_unix": record["launch_unix"],
        "updated_unix": updated_unix,
        "updated_iso": datetime.fromtimestamp(updated_unix, tz=timezone.utc).isoformat(),
        "transfer_status": record.get("transfer_status", "waiting_for_files"),
        "transfer_detail": record.get("transfer_detail", ""),
        "transfer_task_id": record.get("transfer_task_id"),
        "transfer_error": record.get("transfer_error"),
        "render_status": record.get("render_status", "pending"),
    }


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
            key=lambda item: (item["launch_unix"] is not None, item["launch_unix"] or item["updated_unix"]),
            reverse=True,
        ),
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(payload, indent=2))


def _prepare_directories() -> None:
    for path in [WORK_DIR, INGEST_DIR, DELIVERY_DIR, OUTPUT_DIR, WEB_IMAGES_DIR, WEB_SHARPY_DIR, STATE_PATH.parent]:
        path.mkdir(parents=True, exist_ok=True)


def _upsert_record(state: dict, meta: dict) -> dict:
    launches = state.setdefault("launches", {})
    record = launches.setdefault(meta["launch_id"], {})
    record.update(
        {
            "launch_id": meta["launch_id"],
            "site_code": meta["site_code"],
            "launch_iso": meta["launch_iso"],
            "launch_label": meta["launch_label"],
            "launch_unix": meta["launch_unix"],
            "group_key": meta["group_key"],
            "delivery_relative_dir": meta["delivery_relative_dir"],
            "render_status": record.get("render_status", "pending"),
        }
    )
    return record


def run() -> int:
    _prepare_directories()
    site_cfg = load_site_config()
    globus_cfg = GlobusConfig.from_env()
    state = _load_state()

    groups = _discover_launch_groups()
    for group_key, group_payload in groups.items():
        files, wait_reason = _collect_launch_files(group_key, group_payload)
        if not files:
            state["launches"].setdefault(group_key, {"launch_id": group_key, "transfer_status": "waiting_for_files"})
            state["launches"][group_key]["transfer_detail"] = wait_reason
            continue

        try:
            meta = _parse_launch_meta(files, site_cfg)
        except Exception as exc:
            state["launches"][group_key] = {
                "launch_id": group_key,
                "transfer_status": "failed",
                "transfer_error": str(exc),
                "transfer_detail": f"Summary parse failed: {exc}",
            }
            print(f"[error] {group_key}: {exc}")
            continue

        record = _upsert_record(state, meta)
        if not _files_are_stable(files):
            record["transfer_status"] = "upload_in_progress"
            record["transfer_detail"] = (
                f"Waiting {UPLOAD_STABILITY_SECONDS}s for FTP uploads to become stable"
            )
            continue

        delivery_dir = _package_delivery(files, meta, record)
        _normalize_transfer_status(record, globus_cfg)

        if record.get("transfer_status") == "ready_to_transfer":
            try:
                _submit_transfer(record, globus_cfg)
            except Exception as exc:
                record["transfer_status"] = "failed"
                record["transfer_error"] = str(exc)
                record["transfer_detail"] = f"Transfer submission failed: {exc}"
                print(f"[error] {meta['launch_id']}: {exc}")

        if record.get("transfer_status") == "transfer_submitted":
            try:
                _normalize_transfer_status(record, globus_cfg)
            except Exception as exc:
                record["transfer_status"] = "failed"
                record["transfer_error"] = str(exc)
                record["transfer_detail"] = f"Transfer status check failed: {exc}"
                print(f"[error] {meta['launch_id']}: {exc}")

        if record.get("transfer_status") in {"disabled", "succeeded"}:
            sharppy_source = delivery_dir / files.sharppy.name
            work_target = WORK_DIR / f"{record['launch_id']}.txt"
            if not work_target.exists() or sharppy_source.stat().st_mtime > work_target.stat().st_mtime:
                shutil.copy2(sharppy_source, work_target)
            try:
                result = process_one(sharppy_source, record, site_cfg)
                record["image_name"] = result.image_name
                record["sharpy_name"] = result.sharpy_name
                record["render_status"] = "succeeded"
                print(f"[rendered] {record['launch_id']}")
            except Exception as exc:
                record["render_status"] = "failed"
                record["transfer_detail"] = record.get("transfer_detail", "")
                record["render_error"] = str(exc)
                print(f"[error] {record['launch_id']}: {exc}")
        else:
            record["render_status"] = "pending"
            print(f"[pending] {record['launch_id']} [{record.get('transfer_status')}]")

    entries = [
        _manifest_entry(record)
        for record in state.get("launches", {}).values()
        if isinstance(record, dict) and record.get("launch_iso")
    ]
    write_manifest(entries, site_cfg)
    _write_state(state)
    print(f"Tracked {len(entries)} launch(es)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
