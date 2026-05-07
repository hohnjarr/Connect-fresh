from __future__ import annotations

import logging
import os
import time

import anthropic
from dotenv import load_dotenv

from email_poller import fetch_unprocessed_emails
from freshsales_client import FreshsalesClient
from schedule_analyzer import is_class_schedule

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


def _require_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return value


def process_emails(
    claude: anthropic.Anthropic,
    fs: FreshsalesClient,
    imap_cfg: dict,
    subject_filter: str,
    qualified_field: str,
) -> None:
    emails = fetch_unprocessed_emails(
        host=imap_cfg["host"],
        port=imap_cfg["port"],
        username=imap_cfg["username"],
        password=imap_cfg["password"],
        mailbox=imap_cfg["mailbox"],
        subject_filter=subject_filter,
    )

    if not emails:
        return

    logger.info("Processing %d new email(s)", len(emails))

    for msg in emails:
        uid = msg["uid"]
        sender = msg["sender_email"]
        images = msg["images"]

        if not images:
            logger.info("UID %s (%s): no images — skipping", uid, sender)
            continue

        schedule_found = False
        for image_bytes, media_type in images:
            detected, reason = is_class_schedule(claude, image_bytes, media_type)
            if detected:
                logger.info("UID %s: schedule detected — %s", uid, reason)
                schedule_found = True
                break
            else:
                logger.info("UID %s: not a schedule — %s", uid, reason)

        if not schedule_found:
            logger.info("UID %s (%s): no schedule image found", uid, sender)
            continue

        contact = fs.find_contact_by_email(sender)
        if not contact:
            logger.warning("UID %s: sender %s not found in Freshsales", uid, sender)
            continue

        contact_id = contact.get("id")
        fs.mark_qualified_student(contact_id, qualified_field)


def main() -> None:
    load_dotenv()

    imap_cfg = {
        "host": _require_env("IMAP_HOST"),
        "port": int(os.getenv("IMAP_PORT", "993")),
        "username": _require_env("IMAP_USERNAME"),
        "password": _require_env("IMAP_PASSWORD"),
        "mailbox": os.getenv("IMAP_MAILBOX", "INBOX"),
    }
    subject_filter = _require_env("SUBJECT_FILTER")
    poll_interval = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
    qualified_field = _require_env("FRESHSALES_QUALIFIED_FIELD")

    claude = anthropic.Anthropic(api_key=_require_env("ANTHROPIC_API_KEY"))
    fs = FreshsalesClient(
        domain=_require_env("FRESHSALES_DOMAIN"),
        api_key=_require_env("FRESHSALES_API_KEY"),
    )

    logger.info(
        "Starting poller — subject_filter=%r interval=%ds", subject_filter, poll_interval
    )

    while True:
        try:
            process_emails(claude, fs, imap_cfg, subject_filter, qualified_field)
        except Exception:
            logger.exception("Unexpected error during poll cycle")
        time.sleep(poll_interval)


if __name__ == "__main__":
    main()
