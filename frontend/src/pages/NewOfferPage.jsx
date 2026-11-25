import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Globe, UploadCloud } from "lucide-react";

import { PORTAL_CONTENT_CLASS } from "../portal/layout";
import { mergeOfferDraft, readOfferDraft } from "../lib/offerDraft";
import {
  hydrateOfferDraftFromServer,
  persistJdDraftOnServer,
  persistOfferDraft,
} from "../lib/offerDraftServer";
import { authFetch, getProfileText, getSession, getToken } from "../lib/jobseekerProfile";
import JdFormSection from "../features/offers/JdFormSection";
import NewOfferOption from "../features/offers/NewOfferOption";
import { withJobMeta } from "../features/offers/newOfferMeta";

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

  const applyAnalyzeResult = useCallback(
    async (data) => {
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
    },
    [companyName, jobTitle, jobId, resumePaste],
  );

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
      await applyAnalyzeResult(data);
    } catch (e) {
      setAnalyzeErr(String(e));
    } finally {
      setAnalyzeBusy(false);
    }
  }, [description, resumePaste, useCabinetProfile, applyAnalyzeResult]);

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
        await applyAnalyzeResult(data);
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

      <JdFormSection
        jdSectionRef={jdSectionRef}
        fileInputRef={fileInputRef}
        onDropFile={onDropFile}
        companyName={companyName}
        setCompanyName={setCompanyName}
        jobTitle={jobTitle}
        setJobTitle={setJobTitle}
        description={description}
        setDescription={setDescription}
        resumePaste={resumePaste}
        setResumePaste={setResumePaste}
        useCabinetProfile={useCabinetProfile}
        setUseCabinetProfile={setUseCabinetProfile}
        saveDraftNow={saveDraftNow}
        runAnalyze={runAnalyze}
        analyzeBusy={analyzeBusy}
        analyzeErr={analyzeErr}
        saveHint={saveHint}
        jobId={jobId}
        analysis={analysis}
        setAnalysis={setAnalysis}
        meta={meta}
        handleResumePersist={handleResumePersist}
        setSaveHint={setSaveHint}
        goReply={goReply}
      />
    </main>
  );
}
