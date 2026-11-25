/** LLM models for cover letter / resume tailoring (must match backend APP_LLM_MODEL prefixes). */

export const DEFAULT_LLM_MODEL = "cursor:composer-2.5";

export const LLM_MODEL_OPTIONS = [
  {
    id: "cursor:composer-2.5",
    label: "Cursor Composer 2.5 (recommended)",
    hint: "CURSOR_API_KEY in .env",
  },
  {
    id: "groq:llama-3.1-8b-instant",
    label: "Groq Llama 3.1 8B",
    hint: "GROQ_API_KEY in .env",
  },
  {
    id: "openai:gpt-4o-mini",
    label: "OpenAI GPT-4o mini",
    hint: "OPENAI_API_KEY in .env",
  },
];

export function llmRequestTimeoutMs(model) {
  const id = String(model || "").trim().toLowerCase();
  // L7 CrewAI kickoff (3 agents + MD→JSON) often takes several minutes.
  if (id.startsWith("cursor:")) return 600_000;
  if (id.startsWith("openai:")) return 600_000;
  return 300_000;
}

/** Timeout for resume-tailor generate (CrewAI); ignore UI model for duration. */
export function resumeTailorGenerateTimeoutMs() {
  return 600_000;
}

export function llmModelLabel(model) {
  const id = String(model || "").trim();
  const hit = LLM_MODEL_OPTIONS.find((o) => o.id === id);
  return hit?.label || id || DEFAULT_LLM_MODEL;
}
