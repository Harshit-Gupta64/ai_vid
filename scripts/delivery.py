#!/usr/bin/env python3
"""
scripts/delivery.py - Shared Delivery Module for Cloud and Local Pipelines

Handles:
1. Google Drive service account credential decoding, bundle uploads, and verified folder listing.
2. Telegram bot notifications with direct photo thumbnail and playable video attachments.
"""

import base64
import json
import mimetypes
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import requests

# Try to load local .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


def decode_gdrive_credentials() -> Credentials:
    """Decodes base64-encoded service account JSON and returns Google Credentials."""
    raw_b64 = os.environ.get("GDRIVE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw_b64:
        raise ValueError("Missing GDRIVE_SERVICE_ACCOUNT_JSON environment variable.")

    try:
        json_bytes = base64.b64decode(raw_b64)
        creds_dict = json.loads(json_bytes.decode("utf-8"))
    except Exception as e:
        raise ValueError(f"Failed to decode GDRIVE_SERVICE_ACCOUNT_JSON: {e}")

    scopes = ["https://www.googleapis.com/auth/drive"]
    return Credentials.from_service_account_info(creds_dict, scopes=scopes)


def get_gdrive_service():
    """Builds and returns an authorized Google Drive v3 client."""
    creds = decode_gdrive_credentials()
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def list_drive_folder_contents(folder_id: str) -> List[Dict[str, Any]]:
    """Lists all files present in a specific Google Drive folder."""
    service = get_gdrive_service()
    query = f"'{folder_id}' in parents and trashed = false"
    res = service.files().list(
        q=query,
        fields="files(id, name, size, mimeType, webViewLink)",
        supportsAllDrives=True
    ).execute()
    return res.get("files", [])


def upload_to_drive(
    folder_path: Union[str, Path],
    postable: bool,
    custom_folder_name: Optional[str] = None
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Uploads a directory bundle or single file to Google Drive under GDRIVE_FOLDER_ID.
    Returns (dest_folder_id, uploaded_files_list).
    """
    parent_folder_id = os.environ.get("GDRIVE_FOLDER_ID", "").strip()
    if not parent_folder_id:
        raise ValueError("Missing GDRIVE_FOLDER_ID environment variable.")

    service = get_gdrive_service()
    p = Path(folder_path)

    if not p.exists():
        raise FileNotFoundError(f"Local path to upload does not exist: {p}")

    status_tag = "READY" if postable else "QA_REVIEW"
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    folder_name = custom_folder_name or f"{p.name}_{status_tag}_{timestamp}"

    # Create destination subfolder in Google Drive
    folder_metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_folder_id]
    }
    drive_folder = service.files().create(
        body=folder_metadata,
        fields="id, name, webViewLink",
        supportsAllDrives=True
    ).execute()
    dest_folder_id = drive_folder.get("id")
    web_link = drive_folder.get("webViewLink", f"https://drive.google.com/drive/folders/{dest_folder_id}")
    print(f"[GDRIVE] Created Drive package folder: '{folder_name}' (ID: {dest_folder_id})")
    print(f"[GDRIVE] Web View Link: {web_link}")

    # Gather files to upload
    files_to_upload: List[Path] = []
    if p.is_dir():
        files_to_upload = [f for f in p.glob("**/*") if f.is_file()]
    else:
        files_to_upload = [p]

    print(f"[GDRIVE] Preparing upload for {len(files_to_upload)} deliverables into Drive folder {dest_folder_id}...")

    for file_path in files_to_upload:
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if not mime_type:
            if file_path.suffix.lower() == ".ass":
                mime_type = "text/plain"
            elif file_path.suffix.lower() == ".json":
                mime_type = "application/json"
            elif file_path.suffix.lower() == ".txt":
                mime_type = "text/plain"
            else:
                mime_type = "application/octet-stream"

        file_metadata = {
            "name": file_path.name,
            "parents": [dest_folder_id]
        }

        try:
            media = MediaFileUpload(str(file_path), mimetype=mime_type, resumable=True)
            uploaded_file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id, name, size, mimeType",
                supportsAllDrives=True
            ).execute()
            size_kb = int(uploaded_file.get("size", 0)) / 1024
            print(f"  [GDRIVE UPLOAD SUCCESS] '{file_path.name}' ({size_kb:.1f} KB, {mime_type}) -> ID: {uploaded_file.get('id')}")
        except Exception as e:
            err_msg = str(e)
            if "storageQuotaExceeded" in err_msg or "storage quota" in err_msg.lower():
                print(f"  [GDRIVE ERROR - STORAGE QUOTA] Service Accounts have 0 GB individual quota on personal Google Drive ('My Drive') for '{file_path.name}'.")
                print(f"  [GDRIVE ACTION REQUIRED] Direct binary file uploads by service accounts require a Google Workspace Shared Drive or OAuth user delegation.")
            else:
                print(f"  [GDRIVE ERROR] Failed to upload '{file_path.name}': {e}")

    # Verify actual contents via Drive API list
    contents = list_drive_folder_contents(dest_folder_id)
    print(f"[GDRIVE] Verified contents of Drive folder '{folder_name}' ({len(contents)} files confirmed present via API):")
    for f in contents:
        size_str = f"{int(f.get('size', 0)) / 1024:.1f} KB" if f.get("size") else "0 B"
        print(f"  * {f['name']} ({size_str}) -> ID: {f['id']}")

    return dest_folder_id, contents


def send_telegram_notification(
    title: str,
    hashtags: Union[str, List[str]],
    postable: bool,
    video_path_or_drive_link: Union[str, Path],
    drive_folder_id: Optional[str] = None,
    thumbnail_path: Optional[Union[str, Path]] = None
) -> str:
    """
    Sends publishing notifications to the designated Telegram chat:
    1. If thumbnail_path is provided, sends the thumbnail as a photo with the title/status/hashtags caption.
    2. Sends the MP4 video directly via sendVideo with streaming enabled.
    Returns the video message ID (or photo message ID).
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise ValueError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID in environment.")

    if isinstance(hashtags, list):
        tag_str = " ".join(t if t.startswith("#") else f"#{t}" for t in hashtags)
    else:
        tag_str = str(hashtags).strip()

    status_str = "🟢 READY TO POST (All QA Vectors Passed)" if postable else "🟡 QA REVIEW REQUIRED (Degraded Quality / Warning)"
    drive_link = f"https://drive.google.com/drive/folders/{drive_folder_id}" if drive_folder_id else None

    caption_lines = [
        f"🎬 *{title}*",
        f"",
        f"*Status:* {status_str}",
    ]
    if drive_link:
        caption_lines.append(f"📁 *Drive Folder:* [Open in Google Drive]({drive_link})")
    if tag_str:
        caption_lines.append(f"🏷 {tag_str}")

    caption = "\n".join(caption_lines)

    photo_msg_id = None
    # 1. Send thumbnail photo if available
    if thumbnail_path:
        thumb_p = Path(str(thumbnail_path))
        if thumb_p.exists() and thumb_p.is_file():
            print(f"[TELEGRAM] Sending thumbnail photo: {thumb_p.name}...")
            url_photo = f"https://api.telegram.org/bot{token}/sendPhoto"
            try:
                with open(thumb_p, "rb") as pf:
                    files = {"photo": (thumb_p.name, pf, "image/png")}
                    data = {
                        "chat_id": chat_id,
                        "caption": f"🖼 *Thumbnail Preview*\n{caption}",
                        "parse_mode": "Markdown"
                    }
                    resp_photo = requests.post(url_photo, data=data, files=files, timeout=40)
                    if resp_photo.status_code == 200 and resp_photo.json().get("ok"):
                        photo_msg_id = str(resp_photo.json()["result"]["message_id"])
                        print(f"[TELEGRAM] Thumbnail photo sent successfully! Message ID: {photo_msg_id}")
                    else:
                        print(f"[WARN] Telegram sendPhoto returned: {resp_photo.text}")
            except Exception as pe:
                print(f"[WARN] Failed to send thumbnail to Telegram: {pe}")

    # 2. Send video file
    video_path = Path(str(video_path_or_drive_link))
    can_upload_video = False
    if video_path.exists() and video_path.is_file() and video_path.suffix.lower() == ".mp4":
        file_size_mb = video_path.stat().st_size / (1024 * 1024)
        if file_size_mb < 49.0:
            can_upload_video = True
            print(f"[TELEGRAM] Video file detected ({file_size_mb:.2f} MB). Sending via sendVideo...")

    if can_upload_video:
        url = f"https://api.telegram.org/bot{token}/sendVideo"
        try:
            with open(video_path, "rb") as vf:
                files = {"video": (video_path.name, vf, "video/mp4")}
                # If thumbnail exists, pass as video thumb
                if thumbnail_path and Path(str(thumbnail_path)).exists():
                    files["thumbnail"] = (Path(str(thumbnail_path)).name, open(str(thumbnail_path), "rb"), "image/png")

                data = {
                    "chat_id": chat_id,
                    "caption": caption,
                    "parse_mode": "Markdown",
                    "supports_streaming": "true"
                }
                resp = requests.post(url, data=data, files=files, timeout=90)
                if resp.status_code == 200 and resp.json().get("ok"):
                    msg_id = str(resp.json()["result"]["message_id"])
                    print(f"[TELEGRAM] Video sent successfully! Message ID: {msg_id}")
                    return msg_id
                else:
                    print(f"[WARN] Telegram sendVideo returned HTTP {resp.status_code}: {resp.text}. Falling back to sendMessage.", file=sys.stderr)
        except Exception as e:
            print(f"[WARN] Failed to upload video directly to Telegram: {e}. Falling back to sendMessage.", file=sys.stderr)

    # 3. Fallback to sendMessage if video couldn't be uploaded directly
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": caption,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False
    }
    resp = requests.post(url, json=payload, timeout=20)
    if resp.status_code == 200 and resp.json().get("ok"):
        msg_id = str(resp.json()["result"]["message_id"])
        print(f"[TELEGRAM] Message sent successfully! Message ID: {msg_id}")
        return msg_id

    return photo_msg_id or "0"
