from __future__ import annotations

import base64
import json
import logging

import anthropic

logger = logging.getLogger(__name__)

_MODEL = "claude-opus-4-7"

_SYSTEM = (
    "You are an image classifier that specializes in identifying college class schedules. "
    "Examine the provided image and determine whether it shows a college or university class schedule. "
    "A class schedule typically lists courses, meeting times, days of the week, room numbers, "
    "and/or instructor names for an academic term. "
    "Respond ONLY with a JSON object in this exact format — no markdown, no explanation:\n"
    '{"is_schedule": true, "confidence": "high", "reason": "brief one-sentence reason"}\n'
    'Use false for is_schedule if it is not a class schedule. '
    'confidence must be "high", "medium", or "low".'
)


def is_class_schedule(
    client: anthropic.Anthropic,
    image_bytes: bytes,
    media_type: str,
) -> tuple[bool, str]:
    """
    Analyze an image and return (is_schedule, reason).

    Uses Claude vision to classify whether the image is a college class schedule.
    """
    b64 = base64.standard_b64encode(image_bytes).decode()

    response = client.messages.create(
        model=_MODEL,
        max_tokens=256,
        system=_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": "Is this a college class schedule? Respond with the JSON object only.",
                    },
                ],
            }
        ],
    )

    raw = response.content[0].text.strip()
    logger.debug("Claude raw response: %s", raw)

    try:
        parsed = json.loads(raw)
        is_schedule = bool(parsed.get("is_schedule", False))
        reason = str(parsed.get("reason", ""))
        confidence = parsed.get("confidence", "unknown")
        logger.info(
            "Classification: is_schedule=%s confidence=%s reason=%s",
            is_schedule,
            confidence,
            reason,
        )
        return is_schedule, reason
    except json.JSONDecodeError:
        logger.warning("Claude returned non-JSON response: %s", raw)
        return False, "Failed to parse classifier response"
