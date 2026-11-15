import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Link, useNavigate } from "react-router-dom";
import {
  ChevronRight,
  ClipboardList,
  Globe,
  Lock,
  Mail,
  Sparkles,
  Star,
  UploadCloud,
} from "lucide-react";

import { PORTAL_CONTENT_CLASS } from "./layout";
import { mergeOfferDraft, readOfferDraft } from "../lib/offerDraft";
import {
  hydrateOfferDraftFromServer,
  persistJdDraftOnServer,
  persistOfferDraft,
} from "../lib/offerDraftServer";
import { authFetch, getProfileText, getSession, getToken } from "../lib/jobseekerProfile";
import OfferResumeSection from "../features/resume/OfferResumeSection";

function analysisScoreCalculated(analysis) {
  if (!analysis || typeof analysis !== "object") return false;
  if (analysis.scoring_skipped === true) return false;
  return analysis.match_score != null;
}

/** Manual company/title from UI — always win over JD heuristics. */
function withJobMeta(analysis, companyName, jobTitle) {
  const base = analysis && typeof analysis === "object" ? { ...analysis } : {};
  const company = String(companyName || "").trim();
  const title = String(jobTitle || "").trim();
  if (company) base.company_name = company;
  if (title) {
    base.job_title = title;
    base.target_job_title = title;
  }
  return Object.keys(base).length ? base : null;
}

function NewOfferOption({ icon: Icon, title, text, disabled, badge, onClick }) {
  return (
    <motion.button
      type="button"
      whileHover={!disabled ? { y: -3 } : {}}
      onClick={disabled ? undefined : onClick}
      className={`flex w-full items-center gap-7 rounded-lg border border-slate-200 bg-white p-5 text-left shadow-md transition ${
        disabled ? "cursor-not-allowed opacity-60" : "hover:shadow-xl"
      }`}
    >
      <div
        className={`flex h-24 w-24 shrink-0 items-center justify-center rounded-full shadow-inner ${
          disabled ? "bg-slate-100 text-slate-400" : "bg-slate-100 text-orange-600"
        }`}
      >
        <Icon size={46} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-2xl font-extrabold text-slate-950">{title}</h2>
          {badge ? (
            <span className="rounded-full bg-slate-100 px-3 py-1 text-sm font-black text-slate-500">{badge}</span>
          ) : null}
          {disabled ? <Lock size={18} className="text-slate-400" aria-hidden /> : null}
        </div>
        <p className="mt-3 text-lg font-bold leading-snug text-teal-700">{text}</p>
      </div>
      <ChevronRight size={34} className={`shrink-0 ${disabled ? "text-slate-300" : "text-slate-900"}`} />
    </motion.button>
  );
}

export default function NewOfferPage() {
  const navigate = useNavigate();
  const jdSectionRef = useRef(null);
  const fileInputRef = useRef(null);

  const [description, setDescription] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [resumePaste, setResumePaste] = useState("");
  const [useCabinetProfile, setUseCabinetProfile] = useState(
    () => Boolean(getSession()?.email && getProfileText())
  );
  const [analyzeBusy, setAnalyzeBusy] = useState(false);
  const [analyzeErr, setAnalyzeErr] = useState("");
  const [analysis, setAnalysis] = useState(null);
  const [meta, setMeta] = useState(null);
  const [jobId, setJobId] = useState("");
  const [saveHint, setSaveHint] = useState("");

  useEffect(() => {
    async function loadDraft() {
      const d = getToken() ? await hydrateOfferDraftFromServer() : readOfferDraft();
      if (!d) return;
      setDescription(d.jd_text);
      setAnalysis(d.analysis);
      setMeta({ job_description_text: d.jd_text });
      setJobId(d.job_id || "");
      const a = d.analysis && typeof d.analysis === "object" ? d.analysis : {};
      const tracker = a.tracker && typeof a.tracker === "object" ? a.tracker : {};
      setCompanyName(
        String(a.company_name || a.company || tracker.company_name || "").trim(),
      );
      setJobTitle(
        String(
          a.job_title || a.target_job_title || a.title || tracker.job_title || "",
        ).trim(),
      );
      if (d.resume_paste?.trim()) {
        setResumePaste(d.resume_paste);
        setUseCabinetProfile(false);
      }
    }
    loadDraft();
  }, []);

  const scrollToJd = () => jdSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });

  /** Explicit save only (no continuous autosave — that caused PUT spam). */
  const saveDraftNow = useCallback(async () => {
    if (!analysis) return null;
    const nextAnalysis = withJobMeta(analysis, companyName, jobTitle) || analysis;
    const jd = description.trim() || meta?.job_description_text || "";
    if (!jd) return null;
    if (
      nextAnalysis.company_name !== analysis.company_name ||
      nextAnalysis.job_title !== analysis.job_title
    ) {
      setAnalysis(nextAnalysis);
    }
    const patch = {
      jd_text: jd,
      analysis: nextAnalysis,
      resume_paste: resumePaste.trim(),
      job_id: jobId || readOfferDraft()?.job_id || "",
    };
    mergeOfferDraft(patch);
    if (!getToken()) return patch;
    const saved = await persistOfferDraft(patch);
    if (saved?.job_id && saved.job_id !== jobId) setJobId(saved.job_id);
    return saved;
  }, [analysis, companyName, jobTitle, description, meta, resumePaste, jobId]);

  useEffect(() => {
    function syncResumeFromCabinet() {
      const s = getSession();
      const t = getProfileText();
      if (useCabinetProfile && s?.email && t) {
        setResumePaste((prev) => (prev === t ? prev : t));
      }
    }
    syncResumeFromCabinet();
    window.addEventListener("jobseeker-profile-updated", syncResumeFromCabinet);
    window.addEventListener("jobseeker-session-changed", syncResumeFromCabinet);
    return () => {
      window.removeEventListener("jobseeker-profile-updated", syncResumeFromCabinet);
      window.removeEventListener("jobseeker-session-changed", syncResumeFromCabinet);
    };
  }, [useCabinetProfile]);

  const runAnalyze = useCallback(async () => {
    setAnalyzeErr("");
    setAnalyzeBusy(true);
    setAnalysis(null);
    setMeta(null);
    try {
      const fd = new FormData();
      if (description.trim()) fd.append("job_description", description.trim());
      if (!useCabinetProfile && resumePaste.trim()) fd.append("resume_text", resumePaste.trim());

      const r = await authFetch("/analyze/job-description", { method: "POST", body: fd });
      const data = await r.json();
      if (!r.ok) {
        setAnalyzeErr(typeof data.detail === "string" ? data.detail : JSON.stringify(data));
        return;
      }
      const nextAnalysis = withJobMeta(data.analysis, companyName, jobTitle) || data.analysis;
      // Prefill empty fields from any server-side hints
      if (!companyName.trim() && nextAnalysis?.company_name) {
        setCompanyName(String(nextAnalysis.company_name).trim());
      }
      if (!jobTitle.trim() && (nextAnalysis?.job_title || nextAnalysis?.target_job_title)) {
        setJobTitle(
          String(nextAnalysis.job_title || nextAnalysis.target_job_title || "").trim(),
        );
      }
      setAnalysis(nextAnalysis);
      setMeta({ job_description_text: data.job_description_text });
      if (!getToken()) {
        mergeOfferDraft({
          job_id: jobId || "",
          jd_text: data.job_description_text,
          analysis: nextAnalysis,
          resume_paste: resumePaste.trim(),
        });
        setSaveHint("Score calculated locally. Sign in to save the draft to PostgreSQL.");
        return;
      }
      const jdRes = await persistJdDraftOnServer(data.job_description_text, nextAnalysis);
      const nextJobId = jdRes?.ok ? jdRes.job_id || jobId || "" : jobId || "";
      if (nextJobId) setJobId(nextJobId);
      mergeOfferDraft({
        job_id: nextJobId,
        jd_text: data.job_description_text,
        analysis: nextAnalysis,
        resume_paste: resumePaste.trim(),
      });
      if (jdRes?.ok && nextJobId) {
        await persistOfferDraft({
          job_id: nextJobId,
          jd_text: data.job_description_text,
          analysis: nextAnalysis,
          resume_paste: resumePaste.trim(),
        });
        setSaveHint("Saved to the database (application draft)");
      } else {
        setSaveHint(
          jdRes?.reason === "api_error"
            ? `Could not save to the database: ${typeof jdRes.detail === "string" ? jdRes.detail : "server error"}`
            : "Could not save to the database. Check that you are signed in and restart the backend.",
        );
      }
    } catch (e) {
      setAnalyzeErr(String(e));
    } finally {
      setAnalyzeBusy(false);
    }
  }, [description, companyName, jobTitle, resumePaste, jobId, useCabinetProfile]);

  const handleResumePersist = useCallback(
    async (patch) => {
      const base = readOfferDraft();
      const rawAnalysis = patch.analysis ?? analysis ?? base?.analysis;
      const nextAnalysis = withJobMeta(rawAnalysis, companyName, jobTitle) || rawAnalysis;
      const merged = {
        job_id: jobId || base?.job_id || "",
        jd_text: description.trim() || meta?.job_description_text || base?.jd_text || "",
        resume_paste: patch.resume_paste ?? resumePaste.trim(),
        cover_letter_text: patch.cover_letter_text ?? base?.cover_letter_text ?? "",
        tailored_resume_text: patch.tailored_resume_text ?? base?.tailored_resume_text ?? "",
        model: patch.model ?? base?.model ?? "",
        ...patch,
        analysis: nextAnalysis,
      };
      if (!merged.jd_text || !merged.analysis) return null;
      mergeOfferDraft(merged);
      // Only push analysis into React state when the child actually changed it —
      // otherwise withJobMeta() creates a new object every time → autosave loop.
      if (Object.prototype.hasOwnProperty.call(patch, "analysis") && nextAnalysis) {
        setAnalysis(nextAnalysis);
      }
      if (getToken()) {
        const saved = await persistOfferDraft(merged);
        if (saved?.job_id && saved.job_id !== jobId) setJobId(saved.job_id);
      }
      return merged;
    },
    [analysis, companyName, jobTitle, description, jobId, meta, resumePaste],
  );

  const goReply = () => {
    if (!meta?.job_description_text || !analysis) return;
    const nextAnalysis = withJobMeta(analysis, companyName, jobTitle) || analysis;
    try {
      mergeOfferDraft({
        job_id: jobId || readOfferDraft()?.job_id || "",
        jd_text: meta.job_description_text,
        analysis: nextAnalysis,
        resume_paste: resumePaste.trim(),
        cover_letter_text: readOfferDraft()?.cover_letter_text ?? "",
      });
    } catch {
      /* ignore quota */
    }
    navigate("/new/reply");
  };

  const onDropFile = async (fileList) => {
    const f = fileList?.[0];
    if (!f) return;
    const name = f.name.toLowerCase();
    if (name.endsWith(".pdf") || name.endsWith(".html") || name.endsWith(".htm") || name.endsWith(".txt")) {
      setAnalyzeErr("");
      setAnalyzeBusy(true);
      setAnalysis(null);
      setMeta(null);
      try {
        const fd = new FormData();
        fd.append("jd_file", f);
        if (description.trim()) fd.append("job_description", description.trim());
        if (!useCabinetProfile && resumePaste.trim()) fd.append("resume_text", resumePaste.trim());
        const r = await authFetch("/analyze/job-description", { method: "POST", body: fd });
        const data = await r.json();
        if (!r.ok) {
          setAnalyzeErr(typeof data.detail === "string" ? data.detail : JSON.stringify(data));
          return;
        }
        setDescription(data.job_description_text || "");
        const nextAnalysis = withJobMeta(data.analysis, companyName, jobTitle) || data.analysis;
        if (!companyName.trim() && nextAnalysis?.company_name) {
          setCompanyName(String(nextAnalysis.company_name).trim());
        }
        if (!jobTitle.trim() && (nextAnalysis?.job_title || nextAnalysis?.target_job_title)) {
          setJobTitle(
            String(nextAnalysis.job_title || nextAnalysis.target_job_title || "").trim(),
          );
        }
        setAnalysis(nextAnalysis);
        setMeta({ job_description_text: data.job_description_text });
        if (!getToken()) {
          mergeOfferDraft({
            job_id: jobId || "",
            jd_text: data.job_description_text,
            analysis: nextAnalysis,
            resume_paste: resumePaste.trim(),
          });
          setSaveHint("Score calculated locally. Sign in to save the draft to PostgreSQL.");
          return;
        }
        const jdRes = await persistJdDraftOnServer(data.job_description_text, nextAnalysis);
        const nextJobId = jdRes?.ok ? jdRes.job_id || jobId || "" : jobId || "";
        if (nextJobId) setJobId(nextJobId);
        mergeOfferDraft({
          job_id: nextJobId,
          jd_text: data.job_description_text,
          analysis: nextAnalysis,
          resume_paste: resumePaste.trim(),
        });
        if (jdRes?.ok && nextJobId) {
          await persistOfferDraft({
            job_id: nextJobId,
            jd_text: data.job_description_text,
            analysis: nextAnalysis,
            resume_paste: resumePaste.trim(),
          });
          setSaveHint("Saved to the database (application draft)");
        } else {
          setSaveHint(
            jdRes?.reason === "api_error"
              ? `Could not save to the database: ${typeof jdRes.detail === "string" ? jdRes.detail : "server error"}`
              : "Could not save to the database. Check that you are signed in and restart the backend.",
          );
        }
      } catch (e) {
        setAnalyzeErr(String(e));
      } finally {
        setAnalyzeBusy(false);
      }
      return;
    }
    window.alert("PDF, HTML, or TXT are supported. For DOCX, paste the text manually for now.");
  };

  return (
    <main className={`${PORTAL_CONTENT_CLASS} mt-8`}>
      <div className="mb-6">
        <Link to="/" className="text-sm font-bold text-teal-700 hover:text-teal-900">
          ← Back to home
        </Link>
      </div>

      <h1 className="text-5xl font-black text-slate-950">New application</h1>
      <p className="mt-4 text-xl font-medium text-slate-800">
        Choose how to add a new job posting to the system.
      </p>

      <div className="mt-7 space-y-5">
        <NewOfferOption
          icon={Globe}
          title="Web job search"
          badge="Coming soon"
          disabled
          text="Search via LinkedIn, StepStone, Indeed, and company career pages. Not implemented yet."
        />

        <NewOfferOption
          icon={UploadCloud}
          title="Upload job description"
          text="Paste the job text or upload PDF/HTML — the system scores fit with your profile and suggests ATS phrasing."
          onClick={scrollToJd}
        />
      </div>

      <section
        ref={jdSectionRef}
        id="offer-jd-section"
        className="mt-10 scroll-mt-24 rounded-lg border border-slate-200 bg-white p-6 shadow-md"
      >
        <div className="mb-5 flex items-center gap-3">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-teal-700 text-white">
            <ClipboardList size={25} />
          </div>
          <div>
            <h2 className="text-2xl font-black text-slate-950">Job description</h2>
            <p className="font-semibold text-slate-600">Main flow for the current version.</p>
          </div>
        </div>

        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.html,.htm,.txt,application/pdf,text/html,text/plain"
          className="hidden"
          onChange={(e) => {
            onDropFile(e.target.files);
            e.target.value = "";
          }}
        />

        <div
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") fileInputRef.current?.click();
          }}
          onDragOver={(e) => {
            e.preventDefault();
            e.currentTarget.classList.add("border-teal-600", "bg-teal-50");
          }}
          onDragLeave={(e) => {
            e.preventDefault();
            e.currentTarget.classList.remove("border-teal-600", "bg-teal-50");
          }}
          onDrop={(e) => {
            e.preventDefault();
            e.currentTarget.classList.remove("border-teal-600", "bg-teal-50");
            onDropFile(e.dataTransfer.files);
          }}
          onClick={() => fileInputRef.current?.click()}
          className="cursor-pointer rounded-lg border-2 border-dashed border-slate-300 bg-slate-50 p-6 text-center transition"
        >
          <UploadCloud className="mx-auto mb-3 text-teal-700" size={42} />
          <p className="text-lg font-extrabold text-slate-800">Drop PDF / HTML / TXT here</p>
          <p className="mt-1 font-semibold text-slate-500">or click to choose a file — text will appear below</p>
        </div>

        <div className="mt-5 grid gap-3 md:grid-cols-2">
          <label className="block">
            <span className="mb-1.5 block text-sm font-black text-slate-700">Company name</span>
            <input
              type="text"
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              onBlur={() => saveDraftNow()}
              placeholder="e.g. Databricks"
              className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-base font-semibold text-slate-900 outline-none focus:border-teal-700"
            />
          </label>
          <label className="block">
            <span className="mb-1.5 block text-sm font-black text-slate-700">Job title</span>
            <input
              type="text"
              value={jobTitle}
              onChange={(e) => setJobTitle(e.target.value)}
              onBlur={() => saveDraftNow()}
              placeholder="e.g. Data Engineer"
              className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-base font-semibold text-slate-900 outline-none focus:border-teal-700"
            />
          </label>
        </div>
        <p className="mt-2 text-xs font-semibold text-slate-500">
          Enter manually — company names from JD text are often parsed incorrectly.
        </p>

        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          onBlur={() => saveDraftNow()}
          className="mt-4 h-40 w-full resize-none rounded-lg border border-slate-300 p-4 text-base outline-none focus:border-teal-700"
          placeholder="Paste the job description: location, salary, stack, requirements, deadline…"
        />

        <div className="mt-4 rounded-lg border border-teal-100 bg-teal-50/90 p-4">
          <label className="flex cursor-pointer items-start gap-3">
            <input
              type="checkbox"
              className="mt-1 h-4 w-4 shrink-0 accent-teal-700"
              checked={useCabinetProfile}
              onChange={(e) => {
                const on = e.target.checked;
                setUseCabinetProfile(on);
                if (on) {
                  const t = getProfileText();
                  if (t) setResumePaste(t);
                }
              }}
              disabled={!getSession()?.email || !getProfileText()}
            />
            <span>
              <span className="font-black text-slate-900">Use text from your dashboard</span>
              <span className="mt-1 block text-sm font-semibold text-slate-600">
                Data from Profile after uploading a resume. Clear the checkbox to enter different text for this
                analysis.
              </span>
            </span>
          </label>
          {!getSession()?.email ? (
            <p className="mt-3 text-sm font-semibold text-slate-700">
              <Link to="/login" className="font-black text-teal-800 underline">
                Sign in
              </Link>
              {" "}
              to link your dashboard with score calculation.
            </p>
          ) : !getProfileText() ? (
            <p className="mt-3 text-sm font-semibold text-slate-700">
              Open your{" "}
              <Link to="/profile" className="font-black text-teal-800 underline">
                job seeker dashboard
              </Link>{" "}
              and upload a resume PDF — profile text will appear here.
            </p>
          ) : null}
        </div>

        <label className="mt-4 block text-sm font-black text-slate-700">
          Resume / profile text (optional — for score and comparison)
        </label>
        <textarea
          value={resumePaste}
          onChange={(e) => setResumePaste(e.target.value)}
          className="mt-2 h-28 w-full resize-none rounded-lg border border-slate-300 p-4 text-sm outline-none focus:border-teal-700"
          placeholder="Paste a short resume or key CV bullets for a more accurate match score."
        />

        <div className="mt-5 grid gap-3 md:grid-cols-3">
          <div className="rounded-lg bg-slate-50 p-4">
            <Star className="mb-2 text-orange-600" />
            <h3 className="font-black">Score</h3>
            <p className="text-sm font-semibold text-slate-500">JobBERT skill match — as in Untitled1_skillmatch_fixed.ipynb.</p>
          </div>
          <div className="rounded-lg bg-slate-50 p-4">
            <Sparkles className="mb-2 text-orange-600" />
            <h3 className="font-black">ATS tips</h3>
            <p className="text-sm font-semibold text-slate-500">Map resume phrases to wording from the JD.</p>
          </div>
          <div className="rounded-lg bg-slate-50 p-4">
            <Mail className="mb-2 text-orange-600" />
            <h3 className="font-black">Cover letter</h3>
            <p className="text-sm font-semibold text-slate-500">On step 2 — LLM letter using Untitled.ipynb logic.</p>
          </div>
        </div>

        {analyzeErr ? (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm font-semibold text-red-800">
            {analyzeErr}
          </div>
        ) : null}

        {saveHint ? (
          <p className="mt-3 text-sm font-semibold text-teal-800">{saveHint}</p>
        ) : null}
        {jobId ? (
          <p className="mt-1 text-xs font-semibold text-slate-500">
            Draft in DB: <code className="font-mono">{jobId.slice(0, 12)}…</code>
          </p>
        ) : null}

        <button
          type="button"
          disabled={analyzeBusy}
          onClick={() => runAnalyze()}
          className="mt-6 flex w-full items-center justify-center gap-2 rounded-md bg-teal-700 px-5 py-4 text-lg font-black text-white shadow-sm hover:bg-teal-800 disabled:opacity-60"
        >
          <Sparkles size={22} /> {analyzeBusy ? "Analyzing…" : "Calculate score"}
        </button>

        {analysis ? (
          <div className="mt-8 space-y-6 border-t border-slate-200 pt-6">
            <h3 className="text-xl font-black text-slate-950">Analysis results</h3>

            {analysisScoreCalculated(analysis) ? (
              <div
                key={`score-${analysis.match_score}-${(analysis.ats_suggestions || []).length}-${analysis.comparison_summary || ""}`}
                className="rounded-lg border border-teal-200 bg-teal-50 p-4"
              >
                <p className="text-lg font-black text-teal-900">
                  Score: {analysis.match_score} {analysis.match_rank_label ? `— ${analysis.match_rank_label}` : ""}
                </p>
                {analysis.comparison_summary ? (
                  <p className="mt-2 font-semibold text-slate-800">{analysis.comparison_summary}</p>
                ) : null}
                {analysis.skills_available === false ? (
                  <p className="mt-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm font-semibold text-amber-900">
                    Job skills were not extracted — JobBERT found no entities in the Skills & Requirements block.
                  </p>
                ) : null}
                {analysis.matched_skills?.length ? (
                  <p className="mt-3 text-sm font-semibold text-teal-900">
                    <span className="font-black">Matched:</span> {analysis.matched_skills.join(", ")}
                  </p>
                ) : null}
                {analysis.unmatched_skills?.length ? (
                  <p className="mt-2 text-sm font-semibold text-amber-900">
                    <span className="font-black">Unmatched:</span> {analysis.unmatched_skills.join(", ")}
                  </p>
                ) : null}
              </div>
            ) : (
              <div className="rounded-lg border border-slate-200 bg-slate-100 p-4">
                <p className="text-lg font-black text-slate-800">
                  Score: 0 — {analysis.match_rank_label || "No resume provided"}
                </p>
                <p className="mt-2 text-sm font-semibold text-slate-600">
                  {analysis.comparison_summary ||
                    "Provide resume text from your dashboard or in the field below (at least 80 characters) and run analysis again."}
                </p>
              </div>
            )}

            {analysisScoreCalculated(analysis) ? (
              <OfferResumeSection
                analysis={analysis}
                onAnalysisChange={setAnalysis}
                jdText={description.trim() || meta?.job_description_text || ""}
                jobId={jobId}
                companyName={companyName}
                onPersist={handleResumePersist}
                onSaveHint={setSaveHint}
                onProfileSaved={(text) => {
                  setResumePaste(text);
                  setUseCabinetProfile(true);
                }}
                initialUseCabinetProfile={useCabinetProfile}
              />
            ) : null}

            <div className="rounded-xl border-2 border-teal-200 bg-teal-50/90 p-6 shadow-inner">
              <p className="text-sm font-black uppercase tracking-wide text-teal-900">Step 2</p>
              <h4 className="mt-1 text-xl font-black text-slate-950">Cover letter</h4>
              <p className="mt-3 text-sm font-semibold text-slate-700">
                After tailoring your resume, open step 2 and generate a cover letter for this job.
              </p>
              <button
                type="button"
                onClick={goReply}
                className="mt-5 w-full rounded-md bg-teal-700 px-5 py-4 text-lg font-black text-white shadow-sm hover:bg-teal-800 md:w-auto"
              >
                Next: cover letter →
              </button>
            </div>
          </div>
        ) : null}
      </section>
    </main>
  );
}
