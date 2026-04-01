import io
import os
import logging
from config import get_settings

settings = get_settings()
log = logging.getLogger(__name__)


def upload_to_sharepoint(file_bytes: bytes, relative_path: str):
    """
    Upload to SharePoint. Skips silently if SP credentials not configured
    (safe for prototype mode).
    """
    if not all([settings.sp_site_url, settings.sp_client_id, settings.sp_client_secret]):
        log.info(f"[SHAREPOINT SKIPPED — not configured] Would upload: {relative_path}")
        return

    from office365.runtime.auth.client_credential import ClientCredential
    from office365.sharepoint.client_context import ClientContext

    ctx = ClientContext(settings.sp_site_url).with_credentials(
        ClientCredential(settings.sp_client_id, settings.sp_client_secret)
    )

    parts       = relative_path.rsplit("/", 1)
    folder_path = parts[0]
    file_name   = parts[1]

    _ensure_folder(ctx, folder_path)
    target = ctx.web.get_folder_by_server_relative_url(folder_path)
    target.upload_file(file_name, io.BytesIO(file_bytes)).execute_query()
    log.info(f"Uploaded to SharePoint: {relative_path}")


def _ensure_folder(ctx, folder_path: str):
    parts   = folder_path.strip("/").split("/")
    current = ""
    for part in parts:
        current = f"{current}/{part}" if current else part
        try:
            folder = ctx.web.get_folder_by_server_relative_url(current)
            folder.get().execute_query()
        except Exception:
            parent = "/".join(current.split("/")[:-1]) or "/"
            ctx.web.get_folder_by_server_relative_url(parent).folders.add(part).execute_query()
