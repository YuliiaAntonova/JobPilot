"""Fold CrewAI usage_metrics into pack_token_usage call rows + notebook-style prints."""

from __future__ import annotations

from typing import Any


def _as_metrics_dict(usage_metrics: Any) -> dict[str, Any]:
    if not usage_metrics:
        return {}
    if isinstance(usage_metrics, dict):
        return usage_metrics
    return {
        "prompt_tokens": getattr(usage_metrics, "prompt_tokens", 0),
        "completion_tokens": getattr(usage_metrics, "completion_tokens", 0),
        "total_tokens": getattr(usage_metrics, "total_tokens", 0),
        "successful_requests": getattr(usage_metrics, "successful_requests", 1),
    }


def crew_usage_to_calls(
    usage_metrics: dict[str, Any] | None,
    *,
    label: str = "crew_l7",
) -> list[dict[str, Any]]:
    usage_metrics = _as_metrics_dict(usage_metrics)
    if not usage_metrics:
        return []
    inp = int(usage_metrics.get("prompt_tokens") or usage_metrics.get("input_tokens") or 0)
    out = int(usage_metrics.get("completion_tokens") or usage_metrics.get("output_tokens") or 0)
    total = int(usage_metrics.get("total_tokens") or (inp + out))
    return [
        {
            "step": label,
            "prompt_tokens": inp,
            "completion_tokens": out,
            "total_tokens": total,
            "successful_requests": int(
                usage_metrics.get("successful_requests") or usage_metrics.get("calls") or 1
            ),
        }
    ]


def format_crew_usage_summary(
    usage_metrics: Any,
    *,
    label: str = "job_application_crew",
    extra_calls: list[dict[str, Any]] | None = None,
) -> str:
    usage = _as_metrics_dict(usage_metrics)
    inp = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    out = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    total = int(usage.get("total_tokens") or (inp + out))
    calls = int(usage.get("successful_requests") or usage.get("calls") or (1 if total else 0))

    lines = [
        "=== Usage (this run) ===",
        "LLM (CrewAI usage_metrics; OpenAI API usage when available):",
        f"  label:         {label}",
        f"  calls:         {calls}",
        f"  input tokens:  {inp:,}",
        f"  output tokens: {out:,}",
        f"  total tokens:  {total:,}",
    ]
    if extra_calls:
        lines.extend(["", "Additional LLM calls:"])
        for row in extra_calls:
            step = row.get("step") or "call"
            lines.append(
                f"  - {step}: "
                f"in={int(row.get('prompt_tokens') or 0):,} "
                f"out={int(row.get('completion_tokens') or 0):,} "
                f"total={int(row.get('total_tokens') or 0):,}"
            )
            if row.get("model"):
                lines.append(f"    model={row['model']}")
    return "\n".join(lines)


def print_crew_usage_summary(
    usage_metrics: Any,
    *,
    label: str = "job_application_crew",
    extra_calls: list[dict[str, Any]] | None = None,
) -> None:
    print(
        format_crew_usage_summary(usage_metrics, label=label, extra_calls=extra_calls),
        flush=True,
    )
