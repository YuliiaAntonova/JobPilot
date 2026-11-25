import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Download, Mail, Sparkles } from "lucide-react";

import { PORTAL_CONTENT_CLASS } from "../portal/layout";
import LlmModelSelect from "../shared/components/LlmModelSelect";
import { downloadTextFile, exportFileBase } from "../lib/downloadText";
import { readOfferDraft } from "../lib/offerDraft";
import { hydrateOfferDraftFromServer, persistOfferDraft } from "../lib/offerDraftServer";
import { logLlmTokenUsage } from "../lib/llmTokenLog";
import { DEFAULT_LLM_MODEL, llmRequestTimeoutMs } from "../lib/llmModels";
import {
  authFetchWithTimeout,
  fetchProfileFromServer,
  getProfilePayload,
  getProfileText,
  getToken,
  parseApiResponse,
} from "../lib/jobseekerProfile";

export default function OfferReplyPage() {
  const [ready, setReady] = useState(false);
  const [jdText, setJdText] = useState("");
  const [analysis, setAnalysis] = useState(null);
  const [jobId, setJobId] = useState("");
  const [llmModel, setLlmModel] = useState(DEFAULT_LLM_MODEL);

  const [coverLetter, setCoverLetter] = useState("");
  const [coverLetterBusy, setCoverLetterBusy] = useState(false);
  const [coverLetterErr, setCoverLetterErr] = useState("");
  const [saveHint, setSaveHint] = useState("");

  useEffect(() => {
    async function boot() {
      const d = getToken() ? await hydrateOfferDraftFromServer() : readOfferDraft();
      if (!d?.jd_text?.trim()) {
        setReady(false);
        return;
      }
      setJdText(d.jd_text);
      setAnalysis(d.analysis ?? null);
      setJobId(d.job_id || "");
      setCoverLetter(d.cover_letter_text ?? d.analysis?.cover_letter_draft ?? "");
      if (d.model) setLlmModel(d.model);
      else {
        try {
          const cfgRes = await authFetchWithTimeout("/analyze/llm-config", { timeoutMs: 10_000 });
          if (cfgRes.ok) {
            const cfg = await cfgRes.json();
            if (cfg.default_model) setLlmModel(cfg.default_model);
          }
        } catch {
          /* keep default */
        }
      }
      setReady(true);
    }
    boot();
  }, []);

  const persistDraft = useCallback(
    async (patch) => {
      try {
        await persistOfferDraft({
          job_id: jobId || readOfferDraft()?.job_id || "",
          jd_text: jdText,
          analysis,
          model: llmModel,
          ...patch,
        });
      } catch {
        /* ignore */
      }
    },
    [analysis, jdText, jobId, llmModel],
  );

  useEffect(() => {
    if (!ready) return undefined;
    const t = window.setTimeout(() => persistDraft({ cover_letter_text: coverLetter }), 400);
    return () => window.clearTimeout(t);
  }, [coverLetter, ready, persistDraft]);

  const resumeTextForLetter = () => {
    const tailored = analysis?.tailored_resume_text?.trim();
    if (tailored) return tailored;
    return getProfileText().trim();
  };

  const generateCoverLetter = useCallback(async () => {
    if (!jdText.trim()) {
      setCoverLetterErr("No job description text — go back to step 1.");
      return;
    }
    const resumeText = resumeTextForLetter();
    if (resumeText.length < 80) {
      setCoverLetterErr(
        "Resume required (≥ 80 characters): tailor cv_tailored on step 1 or fill out your dashboard profile.",
      );
      return;
    }

    setCoverLetterErr("");
    setCoverLetterBusy(true);
    setSaveHint("Generating cover letter (Untitled.ipynb logic)…");

    try {
      if (getToken()) {
        try {
          await fetchProfileFromServer();
        } catch {
          /* use cache */
        }
      }

      const structured = getProfilePayload()?.structured;
      const body = {
        job_description: jdText.trim(),
        resume_text: resumeText,
        model: llmModel,
      };
      if (structured && Object.keys(structured).filter((k) => !k.startsWith("_")).length) {
        body.structured = structured;
      }

      const r = await authFetchWithTimeout("/analyze/cover-letter", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        timeoutMs: llmRequestTimeoutMs(llmModel),
      });
      const data = await parseApiResponse(r);
      if (!r.ok) {
        setCoverLetterErr(typeof data.detail === "string" ? data.detail : JSON.stringify(data));
        setSaveHint("");
        return;
      }

      logLlmTokenUsage("Cover letter", data.token_usage);
      const letter = String(data.cover_letter || "").trim();
      if (!letter) {
        setCoverLetterErr("Server returned an empty letter.");
        setSaveHint("");
        return;
      }

      setCoverLetter(letter);
      const nextAnalysis = {
        ...(analysis || {}),
        cover_letter_draft: letter,
        cover_letter_source: "llm_notebook",
        cover_letter_match_score: data.match_score,
        cover_letter_matched_skills: data.matched_skills,
      };
      setAnalysis(nextAnalysis);
      await persistDraft({ cover_letter_text: letter, analysis: nextAnalysis });
      setSaveHint("Cover letter ready — you can edit the text and download .txt");
    } catch (e) {
      setCoverLetterErr(String(e.message || e));
      setSaveHint("");
    } finally {
      setCoverLetterBusy(false);
    }
  }, [analysis, jdText, llmModel, persistDraft]);

  const fileBase = exportFileBase(analysis);

  const downloadCoverLetter = () => {
    if (!coverLetter.trim()) {
      setSaveHint("Generate or enter the letter text first.");
      return;
    }
    downloadTextFile(`${fileBase}_cover_letter`, coverLetter.trim());
    setSaveHint("Saved as .txt");
  };

  if (!ready) {
    return (
      <main className={`${PORTAL_CONTENT_CLASS} mt-12`}>
        <section className="rounded-xl border border-slate-200 bg-white p-8 shadow-md">
          <h1 className="text-2xl font-black text-slate-950">Cover letter</h1>
          <p className="mt-4 font-semibold text-slate-700">
            First open the job on{" "}
            <Link to="/new" className="font-black text-teal-800 underline">
              step 1
            </Link>{" "}
            and save the JD text.
          </p>
        </section>
      </main>
    );
  }

  const usingTailored = Boolean(analysis?.tailored_resume_text?.trim());

  return (
    <main className={`${PORTAL_CONTENT_CLASS} mt-12`}>
      <section className="rounded-xl border border-slate-200 bg-white p-8 shadow-md">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-start gap-4">
            <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full bg-slate-100 text-orange-600">
              <Mail size={32} />
            </div>
            <div>
              <p className="text-sm font-black uppercase tracking-wide text-teal-800">Step 2</p>
              <h1 className="mt-1 text-3xl font-extrabold text-slate-950">Cover letter</h1>
              <p className="mt-3 max-w-2xl text-sm font-semibold text-slate-600">
                Generated using the notebook{" "}
                <code className="rounded bg-slate-100 px-1 font-mono text-xs">Untitled.ipynb</code>: parse
                resume/JD → skill match → personalized 250–300 word letter.
              </p>
              {usingTailored ? (
                <p className="mt-2 text-sm font-semibold text-teal-800">
                  Using tailored resume (cv_tailored) from step 1.
                </p>
              ) : (
                <p className="mt-2 text-sm font-semibold text-amber-800">
                  cv_tailored not found — using dashboard profile text. We recommend tailoring the resume on step 1 first.
                </p>
              )}
            </div>
          </div>
          <Link
            to="/new"
            className="rounded-md border border-slate-300 px-4 py-2 text-sm font-black text-slate-800 hover:bg-slate-50"
          >
            ← Step 1
          </Link>
        </div>

        <div className="mt-6 max-w-md">
          <LlmModelSelect value={llmModel} onChange={setLlmModel} disabled={coverLetterBusy} />
        </div>

        {coverLetterErr ? (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm font-semibold text-red-800">
            {coverLetterErr}
          </div>
        ) : null}

        {saveHint ? <p className="mt-3 text-sm font-semibold text-teal-800">{saveHint}</p> : null}

        <div className="mt-6 flex flex-wrap gap-3">
          <button
            type="button"
            disabled={coverLetterBusy}
            onClick={() => generateCoverLetter()}
            className="inline-flex items-center gap-2 rounded-md bg-teal-700 px-5 py-3 text-base font-black text-white hover:bg-teal-800 disabled:opacity-60"
          >
            <Sparkles size={20} />
            {coverLetterBusy ? "Generating…" : "Generate cover letter"}
          </button>
          <button
            type="button"
            disabled={!coverLetter.trim()}
            onClick={downloadCoverLetter}
            className="inline-flex items-center gap-2 rounded-md border border-slate-300 px-5 py-3 text-base font-black text-slate-800 hover:bg-slate-50 disabled:opacity-50"
          >
            <Download size={20} />
            Download .txt
          </button>
        </div>

        <label className="mt-8 block text-sm font-black text-slate-700">Letter text</label>
        <textarea
          value={coverLetter}
          onChange={(e) => setCoverLetter(e.target.value)}
          className="mt-2 min-h-[320px] w-full resize-y rounded-lg border border-slate-300 p-4 text-sm leading-relaxed outline-none focus:border-teal-700"
          placeholder="Click Generate or paste your own text…"
        />
      </section>
    </main>
  );
}