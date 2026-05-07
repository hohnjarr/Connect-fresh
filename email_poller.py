from __future__ import annotations

import email
import email.header
import email.utils
import imaplib
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_PROCESSED_FILE = "processed_uids.json"

# Image MIME types the Anthropic vision API accepts
_SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


def _load_processed_uids() -> set:
    path = Path(_PROCESSED_FILE)
    if path.exists():
        with open(path) as f:
            return set(json.load(f))
    return set()


def _save_processed_uids(uids: set) -> None:
    with open(_PROCESSED_FILE, "w") as f:
        json.dump(sorted(uids), f)


def _decode_header(raw: str) -> str:
    parts = email.header.decode_header(raw)
    out = []
    for part, charset in parts:
        if isinstance(part, bytes):
            out.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            out.append(str(part))
    return "".join(out)


def _sender_email(msg) -> Optional[str]:
    _, addr = email.utils.parseaddr(msg.get("From", ""))
    return addr.lower().strip() or None


def _extract_images(msg) -> list[tuple[bytes, str]]:
    """Return (raw_bytes, media_type) for each supported image part in the message."""
    images = []
    for part in msg.walk():
        ct = part.get_content_type().lower()
        if ct in _SUPPORTED_IMAGE_TYPES:
            payload = part.get_payload(decode=True)
            if payload:
                images.append((payload, ct))
    return images


def fetch_unprocessed_emails(
    host: str,
    port: int,
    username: str,
    password: str,
    mailbox: str,
    subject_filter: str,
) -> list[dict]:
    """
    Connect to the IMAP server and return emails whose subject contains
    subject_filter and have not been processed before.

    Each returned dict has:
        uid          – IMAP UID string
        sender_email – lower-cased sender address
        images       – list of (bytes, media_type) tuples

    UIDs are persisted to disk immediately after fetching so the poller
    never delivers the same email twice, even across restarts.
    """
    processed_uids = _load_processed_uids()
    results: list[dict] = []

    mail = imaplib.IMAP4_SSL(host, port)
    try:
        mail.login(username, password)
        mail.select(mailbox)

        status, uid_data = mail.uid("search", None, f'SUBJECT "{subject_filter}"')
        if status != "OK" or not uid_data or not uid_data[0]:
            return []

        raw_uids = uid_data[0].split()
        logger.info("IMAP search returned %d message(s) matching %r", len(raw_uids), subject_filter)

        for uid_bytes in raw_uids:
            uid = uid_bytes.decode()
            if uid in processed_uids:
                continue

            status, msg_data = mail.uid("fetch", uid_bytes, "(RFC822)")
            if status != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
                logger.warning("Could not fetch UID %s — skipping", uid)
                processed_uids.add(uid)
                _save_processed_uids(processed_uids)
                continue

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            sender = _sender_email(msg)
            images = _extract_images(msg)

            logger.info("UID %s | from=%s | images=%d", uid, sender or "?", len(images))

            # Record as processed before any downstream work
            processed_uids.add(uid)
            _save_processed_uids(processed_uids)

            if not sender:
                logger.warning("UID %s: cannot parse sender address — skipping", uid)
                continue

            results.append({"uid": uid, "sender_email": sender, "images": images})

    finally:
        try:
            mail.logout()
        except Exception:
            pass

    return results
