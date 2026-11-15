"""Resume profile value object — structured JSON + cv.yml flat answers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ResumeProfile:
    """Structured resume + metadata. Built from cv.yml answers or LLM JSON."""

    structured: dict[str, Any]
    profile_text: str
    desired_role: str = ""
    source: str | None = None
    chat_answers: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_chat_answers(cls, answers: dict[str, str]) -> ResumeProfile:
        from job_application.resume.profile_service import profile_dict_from_chat_answers

        payload = profile_dict_from_chat_answers(answers)
        return cls.from_api_dict(payload)

    @classmethod
    def from_structured(
        cls,
        structured: dict[str, Any],
        *,
        profile_text: str = "",
        desired_role: str | None = None,
        source: str | None = None,
        chat_answers: dict[str, str] | None = None,
    ) -> ResumeProfile:
        from job_application.resume.profile_service import profile_dict_from_structured

        payload = profile_dict_from_structured(
            structured,
            profile_text=profile_text,
            desired_role=desired_role,
            source=source,
            chat_answers=chat_answers,
        )
        return cls.from_api_dict(payload)

    @classmethod
    def from_api_dict(cls, payload: dict[str, Any]) -> ResumeProfile:
        structured = payload.get("structured") if isinstance(payload.get("structured"), dict) else {}
        answers_raw = payload.get("chat_answers") if isinstance(payload.get("chat_answers"), dict) else {}
        answers = {k: str(v).strip() for k, v in answers_raw.items() if str(v).strip()}
        return cls(
            structured=dict(structured),
            profile_text=str(payload.get("profile_text") or "").strip(),
            desired_role=str(payload.get("desired_role") or "").strip(),
            source=payload.get("source"),
            chat_answers=answers,
        )

    def to_structured(self) -> dict[str, Any]:
        return dict(self.structured)

    def to_api_dict(self) -> dict[str, Any]:
        from datetime import datetime, timezone

        return {
            "structured": self.to_structured(),
            "profile_text": self.profile_text,
            "desired_role": self.desired_role,
            "source": self.source,
            "chat_answers": dict(self.chat_answers),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
