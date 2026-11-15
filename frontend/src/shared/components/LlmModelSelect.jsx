import { LLM_MODEL_OPTIONS } from "../../lib/llmModels";

export default function LlmModelSelect({ id = "llm-model", value, onChange, className = "" }) {
  return (
    <div className={className}>
      <label htmlFor={id} className="text-xs font-black uppercase text-slate-500">
        LLM model
      </label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-900"
      >
        {LLM_MODEL_OPTIONS.map((opt) => (
          <option key={opt.id} value={opt.id}>
            {opt.label}
          </option>
        ))}
      </select>
      <p className="mt-1 text-xs font-semibold text-slate-500">
        {LLM_MODEL_OPTIONS.find((o) => o.id === value)?.hint || "Provider API key in .env"}
      </p>
    </div>
  );
}
