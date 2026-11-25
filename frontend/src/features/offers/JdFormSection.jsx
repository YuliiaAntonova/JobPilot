import { Link } from "react-router-dom";
import {
  ClipboardList,
  Mail,
  Sparkles,
  Star,
  UploadCloud,
} from "lucide-react";

import { getProfileText, getSession } from "../../lib/jobseekerProfile";
import ScoreResultsSection from "./ScoreResultsSection";

export default function JdFormSection({
  jdSectionRef,
  fileInputRef,
  onDropFile,
  companyName,
  setCompanyName,
  jobTitle,
  setJobTitle,
  description,
  setDescription,
  resumePaste,
  setResumePaste,
  useCabinetProfile,
  setUseCabinetProfile,
  saveDraftNow,
  runAnalyze,
  analyzeBusy,
  analyzeErr,
  saveHint,
  jobId,
  analysis,
  setAnalysis,
  meta,
  handleResumePersist,
  setSaveHint,
  goReply,
}) {
  return (
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
            </Link>{" "}
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

      {saveHint ? <p className="mt-3 text-sm font-semibold text-teal-800">{saveHint}</p> : null}
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

      <ScoreResultsSection
        analysis={analysis}
        setAnalysis={setAnalysis}
        description={description}
        meta={meta}
        jobId={jobId}
        companyName={companyName}
        jobTitle={jobTitle}
        handleResumePersist={handleResumePersist}
        setSaveHint={setSaveHint}
        setResumePaste={setResumePaste}
        setUseCabinetProfile={setUseCabinetProfile}
        useCabinetProfile={useCabinetProfile}
        goReply={goReply}
      />
    </section>
  );
}
