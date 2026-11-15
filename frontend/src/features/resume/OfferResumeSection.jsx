import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Download } from "lucide-react";

import { exportFileBase } from "../../lib/downloadText";
import { logLlmTokenUsage } from "../../lib/llmTokenLog";
import {
  DEFAULT_LLM_MODEL,
  llmRequestTimeoutMs,
  resumeTailorGenerateTimeoutMs,
} from "../../lib/llmModels";
import {
  authFetch,
  authFetchWithTimeout,
  fetchProfileFromServer,
  getProfilePayload,
  getProfileText,
  getToken,
  parseApiResponse,
  profileJobTailoredDraftHtmlUrl,
  profileHasResume,
} from "../../lib/jobseekerProfile";
import TailoredCvDraftEditor from "./TailoredCvDraftEditor";

export default function OfferResumeSection({
  analysis,
  onAnalysisChange,
  jdText,
  jobId,
  companyName = "",
  onPersist,
  onSaveHint,
  initialUseCabinetProfile = true,
}) {
  const [tailoredResume, setTailoredResume] = useState("");
  const [llmModel] = useState(DEFAULT_LLM_MODEL);

  const [resumePdfBusy, setResumePdfBusy] = useState(false);

  const [safeTailorBusy, setSafeTailorBusy] = useState(false);
  const [safeTailorErr, setSafeTailorErr] = useState("");
  const [safeTailorPhase, setSafeTailorPhase] = useState("");
  const [tailoringAnalysis, setTailoringAnalysis] = useState(null);
  const [askUserItems, setAskUserItems] = useState([]);
  const [selectedFactIds, setSelectedFactIds] = useState([]);
  const [tailoredStructured, setTailoredStructured] = useState(null);
  const [tailoredYaml, setTailoredYaml] = useState("");
  const [cvHtmlPreviewKey, setCvHtmlPreviewKey] = useState(0);
  const [cvPreviewHint, setCvPreviewHint] = useState("");
  const [previewBusy, setPreviewBusy] = useState(false);

  const fileBase = exportFileBase(analysis, companyName);
  const skipAnalysisSyncRef = useRef(false);
  const profileHydratedRef = useRef(false);

  useEffect(() => {
    profileHydratedRef.current = false;
    skipAnalysisSyncRef.current = false;
  }, [jobId, jdText]);

  useEffect(() => {
    const cabinet = getProfileText().trim();

    if (skipAnalysisSyncRef.current) {
      skipAnalysisSyncRef.current = false;
      return;
    }

    const rt = analysis?.resume_tailoring;
    if (rt && typeof rt === "object") {
      if (rt.analysis) setTailoringAnalysis(rt.analysis);
      if (Array.isArray(rt.ask_user)) setAskUserItems(rt.ask_user);
      if (Array.isArray(rt.selected_ids)) setSelectedFactIds(rt.selected_ids);
      if (rt.phase) setSafeTailorPhase(rt.phase);
      if (rt.tailored_structured) setTailoredStructured(rt.tailored_structured);
      if (typeof rt.tailored_yaml === "string" && rt.tailored_yaml.trim()) {
        setTailoredYaml(rt.tailored_yaml.trim());
      }
    }

    const savedTailored = analysis?.tailored_resume_text?.trim() || "";
    if (savedTailored) {
      setTailoredResume(savedTailored);
      profileHydratedRef.current = true;
      return;
    }

    if (!profileHydratedRef.current) {
      if (initialUseCabinetProfile && cabinet) {
        setTailoredResume(cabinet);
      }
      profileHydratedRef.current = true;
    }
  }, [analysis?.tailored_resume_text, analysis?.resume_tailoring, initialUseCabinetProfile]);

  const persistAnalysis = useCallback(
    async (nextAnalysis, extra = {}) => {
      onAnalysisChange?.(nextAnalysis);
      await onPersist?.({ analysis: nextAnalysis, ...extra });
    },
    [onAnalysisChange, onPersist],
  );

  const persistResumeTailoring = useCallback(
    async (patch) => {
      const nextRt = {
        ...(analysis?.resume_tailoring || {}),
        ...patch,
      };
      const nextAnalysis = { ...(analysis || {}), resume_tailoring: nextRt };
      await persistAnalysis(nextAnalysis, {});
    },
    [analysis, persistAnalysis],
  );

  /** Internal tailor prep (no separate UI button — score already did JobBERT/ATS). */
  const runSafeTailorAnalyze = useCallback(async () => {
    if (!jdText.trim()) return null;
    if (getToken()) await fetchProfileFromServer();
    const structured = getProfilePayload()?.structured;
    if (!structured || !Object.keys(structured).filter((k) => !k.startsWith("_")).length) {
      setSafeTailorErr("A structured profile is required from the chat wizard or a PDF (Harvard cv.yml).");
      return null;
    }
    // Never re-run JobBERT here — top "Calculate score" already did it
    const r = await authFetchWithTimeout("/analyze/resume-tailor/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        job_description: jdText.trim(),
        structured,
        model: llmModel,
        include_jobbert: false,
      }),
      timeoutMs: llmRequestTimeoutMs(llmModel),
    });
    const data = await parseApiResponse(r);
    if (!r.ok) {
      setSafeTailorErr(typeof data.detail === "string" ? data.detail : JSON.stringify(data));
      return null;
    }
    logLlmTokenUsage("Safe YAML analyze", data.token_usage);
    setTailoringAnalysis(data.analysis);
    setAskUserItems(Array.isArray(data.ask_user) ? data.ask_user : []);
    setSafeTailorPhase(data.phase || "");
    await persistResumeTailoring({
      phase: data.phase,
      analysis: data.analysis,
      ask_user: data.ask_user || [],
      jobbert_score_before: data.jobbert_score_before ?? analysis?.match_score,
    });
    return data;
  }, [analysis?.match_score, jdText, llmModel, persistResumeTailoring]);

  const applyPreviewResponse = useCallback(
    async (data, fallbackStructured) => {
      const structuredOut = data.tailored_structured || fallbackStructured;
      if (structuredOut) setTailoredStructured(structuredOut);
      const yamlOut = String(data.tailored_yaml || "").trim();
      if (yamlOut) setTailoredYaml(yamlOut);
      const plain = String(data.tailored_resume_text || "").trim();
      if (plain) setTailoredResume(plain);
      skipAnalysisSyncRef.current = true;
      await persistAnalysis(
        {
          ...(analysis || {}),
          ...(plain ? { tailored_resume_text: plain } : {}),
          resume_tailoring: {
            ...(analysis?.resume_tailoring || {}),
            ...(structuredOut ? { tailored_structured: structuredOut } : {}),
            ...(yamlOut ? { tailored_yaml: yamlOut } : {}),
          },
        },
        { ...(plain ? { tailored_resume_text: plain } : {}) },
      );
      setCvHtmlPreviewKey(Date.now());
      setCvPreviewHint("cv_tailored_draft.html preview updated (cabinet profile unchanged).");
    },
    [analysis, persistAnalysis],
  );

  const refreshTailoredPreview = useCallback(
    async (structuredOut) => {
      if (!structuredOut) return;
      setPreviewBusy(true);
      try {
        const r = await authFetchWithTimeout("/analyze/resume-tailor/preview", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tailored_structured: structuredOut }),
          timeoutMs: 60_000,
        });
        const data = await parseApiResponse(r);
        if (!r.ok) {
          setCvPreviewHint(typeof data.detail === "string" ? data.detail : "Preview failed");
          return;
        }
        await applyPreviewResponse(data, structuredOut);
      } catch (e) {
        setCvPreviewHint(String(e.message || e));
      } finally {
        setPreviewBusy(false);
      }
    },
    [applyPreviewResponse],
  );

  const refreshTailoredPreviewFromYaml = useCallback(
    async (yamlBody) => {
      if (!yamlBody.trim()) return;
      setPreviewBusy(true);
      try {
        const r = await authFetchWithTimeout("/analyze/resume-tailor/preview", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tailored_yaml: yamlBody }),
          timeoutMs: 60_000,
        });
        const data = await parseApiResponse(r);
        if (!r.ok) {
          setCvPreviewHint(typeof data.detail === "string" ? data.detail : "Preview failed");
          return;
        }
        await applyPreviewResponse(data, null);
      } catch (e) {
        setCvPreviewHint(String(e.message || e));
      } finally {
        setPreviewBusy(false);
      }
    },
    [applyPreviewResponse],
  );

  const saveTailoredPlainTextDraft = useCallback(
    async (text) => {
      const trimmed = String(text || "").trim();
      if (!trimmed) return;
      setPreviewBusy(true);
      try {
        setTailoredResume(trimmed);
        skipAnalysisSyncRef.current = true;
        await persistAnalysis(
          {
            ...(analysis || {}),
            tailored_resume_text: trimmed,
            resume_tailoring: {
              ...(analysis?.resume_tailoring || {}),
              tailored_structured: tailoredStructured || analysis?.resume_tailoring?.tailored_structured,
              ...(tailoredYaml ? { tailored_yaml: tailoredYaml } : {}),
            },
          },
          { tailored_resume_text: trimmed },
        );
        setCvPreviewHint("Draft text saved. For HTML/PDF, use YAML or By fields mode.");
        onSaveHint?.("Tailored text updated.");
      } catch (e) {
        setCvPreviewHint(String(e.message || e));
      } finally {
        setPreviewBusy(false);
      }
    },
    [analysis, onSaveHint, persistAnalysis, tailoredStructured, tailoredYaml],
  );

  const runSafeTailorGenerateAndSave = useCallback(async () => {
    if (!jdText.trim()) return;
    setSafeTailorErr("");
    setSafeTailorBusy(true);
    try {
      let analysisForGenerate = tailoringAnalysis;
      if (!analysisForGenerate) {
        setAskUserItems([]);
        setSelectedFactIds([]);
        setTailoredStructured(null);
        const prep = await runSafeTailorAnalyze();
        if (!prep?.analysis) return;
        analysisForGenerate = prep.analysis;
        if (prep.phase === "awaiting_confirmation") {
          onSaveHint?.("Check only truthful facts, then click Generate preview again.");
          return;
        }
      } else if (safeTailorPhase === "awaiting_confirmation" && askUserItems.length && selectedFactIds.length === 0) {
        onSaveHint?.("Check truthful facts (or clear extras) and run generate again.");
      }

      if (getToken()) {
        try {
          await fetchProfileFromServer();
        } catch {
          /* use cache */
        }
      }
      const structured = getProfilePayload()?.structured;
      if (!structured || !Object.keys(structured).filter((k) => !k.startsWith("_")).length) {
        setSafeTailorErr("A structured profile is required (chat or PDF in your cabinet).");
        return;
      }
      const r = await authFetchWithTimeout("/analyze/resume-tailor/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_description: jdText.trim(),
          analysis: analysisForGenerate,
          structured: structured || undefined,
          selected_ids: selectedFactIds,
          model: llmModel,
          include_jobbert: false,
        }),
        timeoutMs: resumeTailorGenerateTimeoutMs(),
      });
      const data = await parseApiResponse(r);
      if (!r.ok) {
        setSafeTailorErr(typeof data.detail === "string" ? data.detail : JSON.stringify(data));
        return;
      }
      logLlmTokenUsage("Safe YAML generate", data.token_usage);
      const plain = String(data.tailored_resume_text || "").trim();
      const structuredOut = data.tailored_structured;
      if (!plain || !structuredOut) {
        setSafeTailorErr("Server did not return cv_tailored.");
        return;
      }
      setTailoredStructured(structuredOut);
      setTailoredResume(plain);
      const yamlOut = String(data.tailored_yaml || "").trim();
      if (yamlOut) setTailoredYaml(yamlOut);
      setSafeTailorPhase("done");
      skipAnalysisSyncRef.current = true;
      const coverDraft = String(data.cover_letter || "").trim();
      const nextAnalysis = {
        ...(analysis || {}),
        tailored_resume_text: plain,
        ...(coverDraft
          ? {
              cover_letter_draft: coverDraft,
              cover_letter_source: "crew_l7",
            }
          : {}),
        resume_tailoring: {
          phase: "done",
          analysis: analysisForGenerate,
          ask_user: askUserItems,
          selected_ids: selectedFactIds,
          tailored_structured: structuredOut,
          ...(yamlOut ? { tailored_yaml: yamlOut } : {}),
          safety_check: data.safety_check,
          jobbert_score_after: data.jobbert_score_after,
          cover_letter: coverDraft,
        },
      };
      await persistAnalysis(nextAnalysis, {
        tailored_resume_text: plain,
        ...(coverDraft ? { cover_letter_text: coverDraft } : {}),
      });

      const bust = Date.now();
      setCvHtmlPreviewKey(bust);
      if (data.cv_preview?.cv_html) {
        setCvPreviewHint(
          `Preview: ${data.cv_preview.cv_html} (cabinet profile unchanged).`,
        );
      } else {
        setCvPreviewHint("Preview ready. Edit the draft if needed, then export PDF.");
      }
      if (data.target_job_title) {
        onSaveHint?.(`Job headline: “${data.target_job_title}”. Check the preview.`);
      } else {
        onSaveHint?.("Tailoring complete — check the preview and headline.");
      }
    } catch (e) {
      setSafeTailorErr(String(e.message || e));
    } finally {
      setSafeTailorBusy(false);
    }
  }, [
    analysis,
    askUserItems,
    jdText,
    llmModel,
    onSaveHint,
    persistAnalysis,
    runSafeTailorAnalyze,
    safeTailorPhase,
    selectedFactIds,
    tailoringAnalysis,
  ]);

  const toggleFactId = (id) => {
    const key = String(id || "").trim();
    if (!key) return;
    setSelectedFactIds((prev) =>
      prev.includes(key) ? prev.filter((x) => x !== key) : [...prev, key],
    );
  };

  const downloadTailoredPdf = async () => {
    if (!getToken()) {
      onSaveHint?.("Sign in to download PDF.");
      return;
    }
    const structured = tailoredStructured || analysis?.resume_tailoring?.tailored_structured;
    if (!structured) {
      onSaveHint?.("Generate cv_tailored first.");
      return;
    }
    setResumePdfBusy(true);
    try {
      const company =
        String(companyName || analysis?.company_name || "").trim() || fileBase;
      const r = await authFetch("/analyze/resume-tailor/pdf", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tailored_structured: structured,
          company_name: company,
        }),
      });
      if (!r.ok) {
        const data = await parseApiResponse(r);
        throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data));
      }
      const blob = await r.blob();
      const disp = r.headers.get("Content-Disposition") || "";
      const m = disp.match(/filename="([^"]+)"/i);
      const name = m?.[1] || `${fileBase}.pdf`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      onSaveHint?.(`PDF downloaded: ${name}`);
    } catch (e) {
      onSaveHint?.(String(e.message || e));
    } finally {
      setResumePdfBusy(false);
    }
  };

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <h3 className="text-xl font-black text-slate-950">Resume for this job</h3>
      <p className="mt-1 text-sm font-semibold text-slate-600">
        Tailor to JD → edit draft → preview cv_tailored_draft.html → PDF. Your cabinet profile is not overwritten.
      </p>

      {!profileHasResume() ? (
        <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm font-semibold text-amber-900">
          Profile is empty.{" "}
          <Link to="/resume/create" className="font-black underline">
            Chat wizard
          </Link>{" "}
          or{" "}
          <Link to="/profile" className="font-black underline">
            cabinet
          </Link>
          .
        </p>
      ) : null}

      <div className="mt-4 rounded-lg border border-indigo-200 bg-indigo-50/70 p-4">
        <div className="mt-1 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={safeTailorBusy || !jdText.trim() || !profileHasResume()}
            onClick={() => runSafeTailorGenerateAndSave()}
            className="rounded-md bg-indigo-700 px-4 py-2 text-xs font-black text-white hover:bg-indigo-800 disabled:opacity-60"
          >
            {safeTailorBusy
              ? safeTailorPhase === "done" || tailoringAnalysis
                ? "Generating…"
                : "Preparing…"
              : "Generate preview (cv_tailored_draft)"}
          </button>
          <button
            type="button"
            disabled={resumePdfBusy || !(tailoredStructured || analysis?.resume_tailoring?.tailored_structured)}
            onClick={() => downloadTailoredPdf()}
            className="inline-flex items-center gap-2 rounded-md border border-slate-300 bg-white px-4 py-2 text-xs font-black text-slate-800 hover:bg-slate-50 disabled:opacity-60"
          >
            <Download size={16} />
            PDF {fileBase !== "vacancy" ? fileBase : "cv_tailored"}
          </button>
        </div>
        {safeTailorPhase === "awaiting_confirmation" && askUserItems.length ? (
          <div className="mt-4 max-h-64 space-y-2 overflow-y-auto rounded border border-indigo-100 bg-white p-3">
            <p className="text-xs font-black uppercase tracking-wide text-indigo-900">
              Confirm only truthful facts ({askUserItems.length})
            </p>
            {askUserItems.map((item) => {
              const id = String(item.id || "").trim();
              return (
                <label key={id || item.proposed_fact} className="flex cursor-pointer gap-2 text-xs">
                  <input
                    type="checkbox"
                    className="mt-0.5 accent-indigo-700"
                    checked={selectedFactIds.includes(id)}
                    onChange={() => toggleFactId(id)}
                  />
                  <span>
                    <span className="font-semibold text-slate-900">{item.proposed_fact}</span>
                    {item.company ? (
                      <span className="ml-1 text-slate-500">· {item.company}</span>
                    ) : null}
                    {item.apply_to ? (
                      <span className="ml-1 text-indigo-700">→ {item.apply_to}</span>
                    ) : null}
                  </span>
                </label>
              );
            })}
          </div>
        ) : null}
        {safeTailorErr ? (
          <p className="mt-3 rounded border border-red-200 bg-red-50 p-2 text-xs font-semibold text-red-800">
            {safeTailorErr}
          </p>
        ) : null}
        {cvPreviewHint ? (
          <p className="mt-2 text-xs font-semibold text-teal-800">{cvPreviewHint}</p>
        ) : null}
        {safeTailorPhase === "done" && tailoredStructured ? (
          <div className="mt-4">
            <TailoredCvDraftEditor
              structured={tailoredStructured}
              plainText={tailoredResume}
              yamlText={tailoredYaml}
              busy={previewBusy}
              defaultMode="text"
              onApplyStructured={(next) => {
                setTailoredStructured(next);
                refreshTailoredPreview(next);
              }}
              onApplyPlainText={(text) => saveTailoredPlainTextDraft(text)}
              onApplyYaml={(yaml) => refreshTailoredPreviewFromYaml(yaml)}
            />
          </div>
        ) : null}
        {safeTailorPhase === "done" && cvHtmlPreviewKey && getToken() ? (
          <div className="mt-4 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-inner">
            <p className="border-b border-slate-100 bg-slate-50 px-3 py-2 text-xs font-black uppercase tracking-wide text-slate-600">
              cv_tailored_draft.html preview
            </p>
            <iframe
              key={cvHtmlPreviewKey}
              title="cv tailored draft preview"
              src={profileJobTailoredDraftHtmlUrl(cvHtmlPreviewKey)}
              className="h-[min(520px,70vh)] w-full border-0 bg-white"
            />
          </div>
        ) : null}
        {safeTailorPhase === "done" && cvHtmlPreviewKey && !getToken() ? (
          <p className="mt-3 text-xs font-semibold text-amber-800">
            For iframe preview{" "}
            <Link to="/login" className="font-black underline">
              sign in
            </Link>
            . Tailored text is saved in the job draft.
          </p>
        ) : null}
      </div>
    </div>
  );
}
