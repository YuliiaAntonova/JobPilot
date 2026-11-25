"""LlamaIndex LLM backed by the app's existing chat_completion_text stack."""

from __future__ import annotations

from typing import Any

from llama_index.core.base.llms.types import (
    CompletionResponse,
    CompletionResponseGen,
    LLMMetadata,
)
from llama_index.core.bridge.pydantic import Field, PrivateAttr
from llama_index.core.llms.custom import CustomLLM

from job_application.config import APP_LLM_MODEL
from job_application.resume.rag_prepare.run_usage import record_llm_completion
from job_application.shared.llm.client import chat_completion_text


class AppLLM(CustomLLM):
    """One-shot completions via Cursor / aisuite (APP_LLM_MODEL)."""

    model: str = Field(default_factory=lambda: APP_LLM_MODEL)
    system_prompt: str = (
        "You fill CV JSON templates from resume evidence. "
        "Return valid JSON only, with no markdown fences or commentary."
    )
    _call_label: str = PrivateAttr(default="rag_prepare_fill")

    @classmethod
    def class_name(cls) -> str:
        return "app_llm"

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(model_name=self.model, is_chat_model=False)

    def _complete_text(self, prompt: str) -> str:
        text = chat_completion_text(self.model, self.system_prompt, prompt)
        record_llm_completion(prompt, text, backend=self.model, label=self._call_label)
        return text

    def complete(self, prompt: str, formatted: bool = False, **kwargs: Any) -> CompletionResponse:
        del formatted, kwargs
        return CompletionResponse(text=self._complete_text(prompt))

    def stream_complete(
        self, prompt: str, formatted: bool = False, **kwargs: Any
    ) -> CompletionResponseGen:
        text = self.complete(prompt, formatted=formatted, **kwargs).text
        yield CompletionResponse(text=text, delta=text)


def get_llm(*, model: str | None = None) -> AppLLM:
    return AppLLM(model=(model or APP_LLM_MODEL).strip() or APP_LLM_MODEL)
