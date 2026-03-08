from __future__ import annotations

import os
from dataclasses import dataclass


TRANSFER_SCOPE = "urn:globus:auth:scope:transfer.api.globus.org:all"


@dataclass
class GlobusConfig:
    enabled: bool
    client_id: str
    client_secret: str
    source_collection_id: str
    destination_collection_id: str
    destination_base_path: str

    @classmethod
    def from_env(cls) -> "GlobusConfig":
        enabled = os.getenv("ENABLE_GLOBUS_TRANSFER", "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        return cls(
            enabled=enabled,
            client_id=os.getenv("GLOBUS_CLIENT_ID", "").strip(),
            client_secret=os.getenv("GLOBUS_CLIENT_SECRET", "").strip(),
            source_collection_id=os.getenv("GLOBUS_SOURCE_COLLECTION_ID", "").strip(),
            destination_collection_id=os.getenv("GLOBUS_DEST_COLLECTION_ID", "").strip(),
            destination_base_path=os.getenv("GLOBUS_DEST_BASE_PATH", "/").strip() or "/",
        )

    def missing_fields(self) -> list[str]:
        missing: list[str] = []
        if not self.client_id:
            missing.append("GLOBUS_CLIENT_ID")
        if not self.client_secret:
            missing.append("GLOBUS_CLIENT_SECRET")
        if not self.source_collection_id:
            missing.append("GLOBUS_SOURCE_COLLECTION_ID")
        if not self.destination_collection_id:
            missing.append("GLOBUS_DEST_COLLECTION_ID")
        return missing


@dataclass
class TransferSubmission:
    task_id: str


@dataclass
class TransferStatus:
    code: str
    detail: str | None = None


def transfer_enabled(config: GlobusConfig) -> bool:
    return config.enabled


def submit_delivery(config: GlobusConfig, relative_delivery_path: str, label: str) -> TransferSubmission:
    client = _build_transfer_client(config)
    source_path = _normalize_path(relative_delivery_path, trailing_slash=True)
    destination_path = _normalize_path(
        f"{config.destination_base_path.rstrip('/')}/{relative_delivery_path.strip('/')}",
        trailing_slash=True,
    )

    import globus_sdk

    transfer = globus_sdk.TransferData(
        client,
        config.source_collection_id,
        config.destination_collection_id,
        label=label,
        sync_level="checksum",
    )
    transfer.add_item(source_path, destination_path, recursive=True)
    response = client.submit_transfer(transfer)
    return TransferSubmission(task_id=str(response["task_id"]))


def get_task_status(config: GlobusConfig, task_id: str) -> TransferStatus:
    client = _build_transfer_client(config)
    task = client.get_task(task_id)
    status = str(task.get("status", "")).upper()
    if status == "SUCCEEDED":
        return TransferStatus(code="succeeded")
    if status in {"ACTIVE", "INACTIVE", "QUEUED"}:
        detail = task.get("nice_status_short_description") or task.get("status")
        return TransferStatus(code="in_progress", detail=str(detail) if detail else None)
    if status == "FAILED":
        detail = task.get("fatal_error") or task.get("nice_status_short_description") or "Transfer failed"
        return TransferStatus(code="failed", detail=str(detail))
    detail = task.get("nice_status_short_description") or task.get("status")
    return TransferStatus(code="in_progress", detail=str(detail) if detail else None)


def _build_transfer_client(config: GlobusConfig):
    if not config.enabled:
        raise RuntimeError("Globus transfer is disabled")

    missing = config.missing_fields()
    if missing:
        raise RuntimeError(f"Missing Globus configuration: {', '.join(missing)}")

    import globus_sdk

    auth_client = globus_sdk.ConfidentialAppAuthClient(config.client_id, config.client_secret)
    authorizer = globus_sdk.ClientCredentialsAuthorizer(auth_client, TRANSFER_SCOPE)
    return globus_sdk.TransferClient(authorizer=authorizer)


def _normalize_path(value: str, trailing_slash: bool = False) -> str:
    normalized = "/" + value.strip("/")
    if trailing_slash and not normalized.endswith("/"):
        normalized += "/"
    return normalized
