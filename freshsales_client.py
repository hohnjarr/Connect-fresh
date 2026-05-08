from __future__ import annotations

import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class FreshsalesClient:
    def __init__(self, domain: str, api_key: str) -> None:
        self._base = f"https://{domain}.myfreshworks.com/api"
        self._headers = {
            "Authorization": f"Token token={api_key}",
            "Content-Type": "application/json",
        }

    def find_contact_by_email(self, email: str) -> Optional[dict]:
        """Return the first Freshsales contact whose email matches exactly, or None."""
        url = f"{self._base}/contacts/search"
        params = {"q": email, "include": "contact"}

        try:
            resp = requests.get(url, headers=self._headers, params=params, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Freshsales contact search failed: %s", exc)
            return None

        data = resp.json()
        contacts = data.get("contacts") or []

        if not contacts:
            logger.info("No Freshsales contact found for %s", email)
            return None

        # Prefer an exact email match; fall back to the first result with a warning.
        for contact in contacts:
            if (contact.get("email") or "").lower() == email.lower():
                return contact

        logger.warning(
            "Freshsales search for %s returned %d result(s) but none matched exactly — using first",
            email,
            len(contacts),
        )
        return contacts[0]

    def mark_qualified_student(self, contact_id: int, field_name: str) -> bool:
        """Set field_name to True on the given contact. Returns True on success."""
        url = f"{self._base}/contacts/{contact_id}"
        payload = {"contact": {field_name: True}}

        try:
            resp = requests.put(url, headers=self._headers, json=payload, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Freshsales contact update failed for id=%s: %s", contact_id, exc)
            return False

        logger.info("Marked contact %s as qualified student (field=%s)", contact_id, field_name)
        return True
