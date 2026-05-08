from __future__ import annotations

import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class FreshsalesClient:
    def __init__(self, domain: str, api_key: str) -> None:
        self._base = f"https://{domain}.myfreshworks.com/crm/sales/api"
        self._headers = {
            "Authorization": f"Token token={api_key}",
            "Content-Type": "application/json",
        }

    def find_contact_by_email(self, email: str) -> Optional[dict]:
        """Return the Freshworks CRM contact whose email matches exactly, or None."""
        url = f"{self._base}/filtered_search/contact"
        payload = {
            "filter_rule": [
                {
                    "attribute": "contact_email.email",
                    "operator": "is_in",
                    "value": email,
                }
            ]
        }

        try:
            resp = requests.post(url, headers=self._headers, json=payload, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Freshworks contact search failed: %s", exc)
            return None

        logger.debug(
            "Freshworks search response: status=%s body=%r", resp.status_code, resp.text
        )

        try:
            data = resp.json()
        except ValueError:
            logger.error(
                "Freshworks contact search returned non-JSON: status=%s body=%r",
                resp.status_code,
                resp.text,
            )
            return None

        contacts = data.get("contacts") or []

        if not contacts:
            logger.info("No Freshworks contact found for %s", email)
            return None

        return contacts[0]

    def mark_qualified_student(self, contact_id: int, field_name: str) -> bool:
        """Set field_name to True on the given contact. Returns True on success."""
        url = f"{self._base}/contacts/{contact_id}"
        payload = {"contact": {field_name: True}}

        try:
            resp = requests.put(url, headers=self._headers, json=payload, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Freshworks contact update failed for id=%s: %s", contact_id, exc)
            return False

        logger.info("Marked contact %s as qualified student (field=%s)", contact_id, field_name)
        return True
