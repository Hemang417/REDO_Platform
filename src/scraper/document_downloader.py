"""
Downloads MAHARERA project documents to disk and prepares DB records for them.

Mechanism confirmed via live authenticated discovery (2026-07-02):
    1. POST getUploadedDocuments {"projectId": id} -> list of
       {documentDmsRefNo, documentFileName, documentTypeId, documentDetails,
        documentDescription, uploadDate, isActive}
    2. POST downloadDocumentForPublicView {"fileName": ..., "documentId": documentDmsRefNo}
       -> raw PDF bytes (Content-Type: application/pdf)

Single responsibility: fetch the document list for a project, download bytes,
write to disk (atomic, skip if sha256 unchanged), return DocumentRecord objects
for the caller to upsert into Postgres.
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from src.database.repository import DocumentRecord
from src.scraper.maharera_api_client import MahareraApiClient, MahareraApiError

logger = logging.getLogger(__name__)


class DocumentDownloader:
    """Downloads all uploaded documents for a project into output/documents/<registration_number>/."""

    def __init__(self, api_client: MahareraApiClient, output_dir: str = "output/documents") -> None:
        self._api = api_client
        self._output_dir = Path(output_dir)

    def download_for_project(
        self, project_db_id: int, project_id: str, registration_number: str
    ) -> list[DocumentRecord]:
        """Fetch and download every uploaded document for one project.

        Returns DocumentRecord objects ready for upsert_documents(). Skips
        re-downloading (but still returns a record) if a file with the same
        sha256 already exists on disk — never re-writes an unchanged document.
        """
        try:
            docs = self._api.get_uploaded_documents(project_id)
        except MahareraApiError:
            raise
        except Exception as exc:
            logger.warning("Failed to list documents for project_id=%s: %s", project_id, exc)
            return []

        records: list[DocumentRecord] = []
        project_dir = self._output_dir / registration_number
        project_dir.mkdir(parents=True, exist_ok=True)

        for doc in docs:
            source_ref = doc.get("documentDmsRefNo")
            file_name = doc.get("documentFileName")
            if not source_ref or not file_name:
                continue

            try:
                content = self._api.download_document(file_name, source_ref)
            except MahareraApiError:
                raise
            except Exception as exc:
                logger.warning(
                    "Failed to download document %s (%s) for project_id=%s: %s",
                    source_ref, file_name, project_id, exc,
                )
                continue

            if not content:
                logger.warning("Empty content for document %s (%s)", source_ref, file_name)
                continue

            sha256 = hashlib.sha256(content).hexdigest()
            local_path = project_dir / f"{source_ref}_{file_name}"

            if not (local_path.exists() and self._sha256_of_file(local_path) == sha256):
                tmp_path = local_path.with_suffix(local_path.suffix + ".tmp")
                tmp_path.write_bytes(content)
                os.replace(tmp_path, local_path)
                logger.info("Downloaded document %s -> %s", file_name, local_path)
            else:
                logger.debug("Document %s unchanged (sha256 match), skipped re-write", file_name)

            records.append(
                DocumentRecord(
                    project_id=project_db_id,
                    registration_number=registration_number,
                    source_ref=source_ref,
                    file_name=file_name,
                    sha256=sha256,
                    local_path=str(local_path),
                    downloaded_at=datetime.now(timezone.utc),
                    document_type_id=doc.get("documentTypeId"),
                    doc_type=doc.get("documentDetails") or doc.get("documentDescription") or "Unknown",
                    uploaded_at=doc.get("uploadDate"),
                )
            )

        return records

    @staticmethod
    def _sha256_of_file(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
