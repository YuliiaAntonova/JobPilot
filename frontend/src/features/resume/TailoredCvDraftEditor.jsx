import { useEffect, useState } from "react";

import {
  experienceDraftRows,
  mergeDraftFormIntoStructured,
  skillsToCommaText,
} from "../../lib/tailoredCvDraft";

const MODES = [
  { id: "text", label: "Full text" },
  { id: "yaml", label: "Full (YAML)" },
  { id: "fields", label: "By fields" },
];

/**
 * Edit job-specific cv draft before PDF (does not touch cabinet profile).
 */
export default function TailoredCvDraftEditor({
  structured,
  plainText = "",
  yamlText = "",
  busy = false,
  onApplyStructured,
  onApplyPlainText,
  onApplyYaml,
  defaultMode = "text",
}) {
  const [mode, setMode] = useState(defaultMode);
  const [headline, setHeadline] = useState("");
  const [summary, setSummary] = useState("");
  const [skillsText, setSkillsText] = useState("");
  const [experienceRows, setExperienceRows] = useState([]);
  const [fullText, setFullText] = useState("");
  const [fullYaml, setFullYaml] = useState("");

  useEffect(() => {
    if (!structured) return;
    setHeadline(String(structured?.basics?.headline || "").trim());
    setSummary(String(structured?.basics?.summary || "").trim());
    setSkillsText(skillsToCommaText(structured));
    setExperienceRows(experienceDraftRows(structured));
  }, [structured]);

  useEffect(() => {
    setFullText(String(plainText || "").trim());
  }, [plainText]);

  useEffect(() => {
    setFullYaml(String(yamlText || "").trim());
  }, [yamlText]);

  if (!structured) return null;

  const applyFields = () => {
    const next = mergeDraftFormIntoStructured(structured, {
      headline,
      summary,
      skillsText,
      experienceRows,
    });
    onApplyStructured?.(next);
  };

  const applyText = () => {
    onApplyPlainText?.(fullText.trim());
  };

  const applyYaml = () => {
    onApplyYaml?.(fullYaml.trim());
  };

  return (
    <div className="space-y-4 rounded-lg border border-slate-200 bg-slate-50 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-black uppercase tracking-wide text-slate-600">
          Edit draft (this job only)
        </p>
        <div className="flex flex-wrap gap-1 rounded-md border border-slate-200 bg-white p-0.5">
          {MODES.map((m) => (
            <button
              key={m.id}
              type="button"
              onClick={() => setMode(m.id)}
              className={`rounded px-2.5 py-1 text-xs font-black ${
                mode === m.id ? "bg-indigo-700 text-white" : "text-slate-700 hover:bg-slate-100"
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      {mode === "text" ? (
        <>
          <p className="text-xs font-semibold text-slate-600">
            Single text block like the previous version: easy to tweak wording and recalculate score. HTML/PDF update
            from YAML or By fields mode.
          </p>
          <label className="block text-xs font-black text-slate-700">
            Tailored resume text
            <textarea
              value={fullText}
              onChange={(e) => setFullText(e.target.value)}
              rows={16}
              className="mt-1 w-full resize-y rounded-md border border-slate-300 px-3 py-2 font-mono text-sm leading-relaxed"
            />
          </label>
          <button
            type="button"
            disabled={busy || !fullText.trim()}
            onClick={applyText}
            className="rounded-md bg-indigo-700 px-4 py-2 text-xs font-black text-white hover:bg-indigo-800 disabled:opacity-60"
          >
            {busy ? "Saving…" : "Save draft text"}
          </button>
        </>
      ) : null}

      {mode === "yaml" ? (
        <>
          <p className="text-xs font-semibold text-slate-600">
            Entire cv_tailored.yml in one field — after Apply, HTML preview and PDF will refresh.
          </p>
          <label className="block text-xs font-black text-slate-700">
            cv_tailored (YAML)
            <textarea
              value={fullYaml}
              onChange={(e) => setFullYaml(e.target.value)}
              rows={18}
              spellCheck={false}
              className="mt-1 w-full resize-y rounded-md border border-slate-300 px-3 py-2 font-mono text-xs leading-relaxed"
            />
          </label>
          <button
            type="button"
            disabled={busy || !fullYaml.trim()}
            onClick={applyYaml}
            className="rounded-md bg-indigo-700 px-4 py-2 text-xs font-black text-white hover:bg-indigo-800 disabled:opacity-60"
          >
            {busy ? "Updating…" : "Apply YAML and refresh preview"}
          </button>
        </>
      ) : null}

      {mode === "fields" ? (
        <>
          <label className="block text-xs font-black text-slate-700">
            Headline
            <input
              type="text"
              value={headline}
              onChange={(e) => setHeadline(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm font-semibold"
            />
          </label>

          <label className="block text-xs font-black text-slate-700">
            Summary
            <textarea
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              rows={4}
              className="mt-1 w-full resize-y rounded-md border border-slate-300 px-3 py-2 text-sm leading-relaxed"
            />
          </label>

          <label className="block text-xs font-black text-slate-700">
            Skills (comma-separated)
            <textarea
              value={skillsText}
              onChange={(e) => setSkillsText(e.target.value)}
              rows={3}
              className="mt-1 w-full resize-y rounded-md border border-slate-300 px-3 py-2 text-sm leading-relaxed"
            />
          </label>

          {experienceRows.map((row, i) => (
            <div key={row.idx} className="rounded-md border border-slate-200 bg-white p-3">
              <p className="text-xs font-black text-indigo-900">Experience {i + 1}</p>
              <div className="mt-2 grid gap-2 md:grid-cols-2">
                <input
                  type="text"
                  value={row.company}
                  placeholder="Company"
                  onChange={(e) => {
                    const copy = [...experienceRows];
                    copy[i] = { ...copy[i], company: e.target.value };
                    setExperienceRows(copy);
                  }}
                  className="rounded-md border border-slate-300 px-2 py-1.5 text-sm"
                />
                <input
                  type="text"
                  value={row.title}
                  placeholder="Title"
                  onChange={(e) => {
                    const copy = [...experienceRows];
                    copy[i] = { ...copy[i], title: e.target.value };
                    setExperienceRows(copy);
                  }}
                  className="rounded-md border border-slate-300 px-2 py-1.5 text-sm"
                />
                <input
                  type="text"
                  value={row.period}
                  placeholder="Period"
                  onChange={(e) => {
                    const copy = [...experienceRows];
                    copy[i] = { ...copy[i], period: e.target.value };
                    setExperienceRows(copy);
                  }}
                  className="rounded-md border border-slate-300 px-2 py-1.5 text-sm md:col-span-2"
                />
              </div>
              <label className="mt-2 block text-xs font-semibold text-slate-600">
                Bullets (one per line)
                <textarea
                  value={row.bulletsText}
                  onChange={(e) => {
                    const copy = [...experienceRows];
                    copy[i] = { ...copy[i], bulletsText: e.target.value };
                    setExperienceRows(copy);
                  }}
                  rows={4}
                  className="mt-1 w-full resize-y rounded-md border border-slate-300 px-2 py-1.5 text-sm leading-relaxed"
                />
              </label>
            </div>
          ))}

          <button
            type="button"
            disabled={busy}
            onClick={applyFields}
            className="rounded-md bg-indigo-700 px-4 py-2 text-xs font-black text-white hover:bg-indigo-800 disabled:opacity-60"
          >
            {busy ? "Updating…" : "Apply edits and refresh preview"}
          </button>
        </>
      ) : null}
    </div>
  );
}