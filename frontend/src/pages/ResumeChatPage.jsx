import { useEffect, useRef, useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { ChevronLeft, ChevronRight, Download, FileUp, MessageSquare, Plus, Trash2 } from "lucide-react";
import {
  chatAnswersFromProfilePayload,
  previewCvFilesFromAnswers,
  sanitizeChatAnswers,
  saveProfileFromChatAnswers,
} from "../lib/resumeChat";
import {
  appendIndexedBlock,
  buildResumeSections,
  compactJobAnswers,
  jobIndicesFromAnswers,
  deleteConfirmMessage,
  removeIndexedBlockFromAnswers,
  validateSection,
} from "../lib/resumeChatSections";
import {
  downloadProfileResume,
  getProfilePayload,
  getSession,
  uploadResumePdfToServer,
} from "../lib/jobseekerProfile";
import { PORTAL_CONTENT_CLASS } from "../portal/layout";

function SectionField({ field, value, onChange, disabled }) {
  const common = {
    value: value || "",
    onChange: (e) => onChange(field.key, e.target.value),
    placeholder: field.placeholder,
    disabled,
    className:
      "w-full rounded-2xl border border-slate-200 px-4 py-3 text-base outline-none focus:border-teal-600 disabled:opacity-50",
  };
  return (
    <label className="block">
      <span className="mb-1 flex items-center gap-2 text-sm font-black uppercase tracking-wide text-slate-700">
        {field.label}
        {field.optional ? (
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-bold normal-case text-slate-500">
            optional
          </span>
        ) : null}
      </span>
      {field.multiline ? <textarea {...common} rows={field.key.endsWith("_description") ? 6 : 4} className={`${common.className} resize-y`} /> : <input {...common} />}
    </label>
  );
}

export default function ResumeChatPage() {
  const authSession = getSession();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const isEdit = searchParams.get("edit") === "1";
  const fileRef = useRef(null);

  const [phase, setPhase] = useState(isEdit ? "sections" : "choose");
  const [answers, setAnswers] = useState({});
  const [sectionIndex, setSectionIndex] = useState(0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [done, setDone] = useState(false);
  const [downloadBusy, setDownloadBusy] = useState("");
  const [savedPayload, setSavedPayload] = useState(null);
  const [cvPreviewHint, setCvPreviewHint] = useState("");
  const previewTimerRef = useRef(null);

  const sections = buildResumeSections(answers);
  const section = sections[sectionIndex] || sections[0];
  const progress = sections.length ? ((sectionIndex + 1) / sections.length) * 100 : 0;

  useEffect(() => {
    if (!isEdit) return;
    const seed = chatAnswersFromProfilePayload(getProfilePayload());
    if (seed) setAnswers(seed);
  }, [isEdit]);

  useEffect(() => {
    if (phase !== "sections") return undefined;
    window.clearTimeout(previewTimerRef.current);
    previewTimerRef.current = window.setTimeout(() => {
      previewCvFilesFromAnswers(answers)
        .then((data) => {
          if (data?.cv_yml && data?.cv_html) {
            setCvPreviewHint(`Local preview: ${data.cv_yml} · ${data.cv_html}`);
          }
        })
        .catch(() => {});
    }, 1200);
    return () => window.clearTimeout(previewTimerRef.current);
  }, [answers, phase]);

  if (!authSession?.email) {
    return <Navigate to="/login" replace state={{ from: "/resume/create" }} />;
  }

  function updateField(key, value) {
    setAnswers((prev) => ({ ...prev, [key]: value }));
  }

  function removeIndexedBlock(field) {
    const prefix = field.blockPrefix || "exp_";
    const index = field.jobIndex;
    if (!window.confirm(deleteConfirmMessage(field, answers))) {
      return;
    }
    setErr("");
    setAnswers((prev) => removeIndexedBlockFromAnswers(prev, prefix, index));
  }

  function addIndexedBlock() {
    if (!section?.blockPrefix) return;
    setErr("");
    setAnswers((prev) => appendIndexedBlock(prev, section.blockPrefix));
  }

  async function handleResumeUpload(file) {
    if (!file || busy) return;
    const name = (file.name || "").toLowerCase();
    if (!name.endsWith(".pdf") && !name.endsWith(".txt")) {
      setErr("PDF and TXT are supported.");
      return;
    }
    setErr("");
    setBusy(true);
    try {
      await uploadResumePdfToServer(file);
      const seed = compactJobAnswers(chatAnswersFromProfilePayload(getProfilePayload()) || {});
      setAnswers(seed);
      setSectionIndex(0);
      setPhase("sections");
      setDone(false);
      previewCvFilesFromAnswers(seed)
        .then((data) => {
          if (data?.cv_yml && data?.cv_html) {
            setCvPreviewHint(`Local preview: ${data.cv_yml} · ${data.cv_html}`);
          }
        })
        .catch(() => {});
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  function startManual() {
    setAnswers({});
    setSectionIndex(0);
    setPhase("sections");
    setDone(false);
    setErr("");
  }

  function goBack() {
    setErr("");
    setSectionIndex((i) => Math.max(0, i - 1));
  }

  async function goNext() {
    if (!section) return;
    const missing = validateSection(section, answers);
    if (missing.length) {
      setErr(`Fill required fields: ${missing.join(", ")}`);
      return;
    }
    setErr("");

    if (sectionIndex >= sections.length - 1) {
      await finishProfile();
      return;
    }

    try {
      await previewCvFilesFromAnswers(answers);
    } catch {
      /* preview is best-effort while editing */
    }
    setSectionIndex((i) => i + 1);
  }

  async function finishProfile() {
    setBusy(true);
    setErr("");
    try {
      const cleaned = sanitizeChatAnswers(answers);
      if (!cleaned.name || !cleaned.email) {
        throw new Error("Name and email are required.");
      }
      if (!cleaned.headline) {
        throw new Error("Headline (target role) is required.");
      }
      const result = await saveProfileFromChatAnswers(cleaned);
      setSavedPayload(result.profile);
      if (result.cvPreview?.cv_yml) {
        setCvPreviewHint(`Local preview: ${result.cvPreview.cv_yml} · ${result.cvPreview.cv_html}`);
      }
      setDone(true);
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  async function handleDownload(format) {
    if (downloadBusy) return;
    setDownloadBusy(format);
    try {
      const cleaned = sanitizeChatAnswers(answers);
      await downloadProfileResume(format, {
        chat_answers: Object.keys(cleaned).length ? cleaned : savedPayload?.chat_answers,
        structured: savedPayload?.structured,
        profile_text: savedPayload?.profile_text,
      });
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setDownloadBusy("");
    }
  }

  function onFileInputChange(e) {
    const file = e.target.files?.[0];
    if (file) handleResumeUpload(file);
    e.target.value = "";
  }

  if (phase === "choose") {
    return (
      <main className={`${PORTAL_CONTENT_CLASS} mt-8`}>
        <div className="mb-6">
          <Link to="/profile" className="text-sm font-bold text-teal-700 hover:text-teal-900">
            ← Job seeker dashboard
          </Link>
        </div>

        <div className="mx-auto max-w-2xl text-center">
          <h1 className="text-3xl font-black uppercase tracking-wide text-slate-950">Build your resume</h1>
          <p className="mt-4 text-lg font-semibold text-slate-600">
            Upload a PDF — we parse it into sections. Review and edit page by page, then save.
          </p>
        </div>

        <input
          ref={fileRef}
          type="file"
          accept=".pdf,.txt,application/pdf,text/plain"
          className="hidden"
          onChange={onFileInputChange}
        />

        <div className="mx-auto mt-10 grid max-w-2xl gap-4">
          <button
            type="button"
            disabled={busy}
            onClick={() => fileRef.current?.click()}
            className="flex items-center justify-center gap-3 rounded-2xl bg-teal-600 px-6 py-5 text-lg font-black text-white shadow hover:bg-teal-700 disabled:opacity-50"
          >
            <FileUp size={22} />
            {busy ? "Parsing resume…" : "Upload resume (PDF / TXT)"}
          </button>

          <button
            type="button"
            disabled={busy}
            onClick={startManual}
            className="flex items-center justify-center gap-3 rounded-2xl border-2 border-slate-300 bg-white px-6 py-5 text-lg font-black text-slate-900 hover:bg-slate-50 disabled:opacity-50"
          >
            <MessageSquare size={22} />
            Fill in manually
          </button>
        </div>

        {err ? (
          <div className="mx-auto mt-6 max-w-2xl rounded-lg border border-red-200 bg-red-50 p-4 text-sm font-semibold text-red-800">
            {err}
          </div>
        ) : null}
      </main>
    );
  }

  if (done) {
    return (
      <main className={`${PORTAL_CONTENT_CLASS} mt-8`}>
        <div className="mb-6">
          <Link to="/profile" className="text-sm font-bold text-teal-700 hover:text-teal-900">
            ← Job seeker dashboard
          </Link>
        </div>
        <div className="mx-auto max-w-2xl rounded-2xl border-2 border-teal-500 bg-teal-50 p-6 text-center shadow-md">
          <h2 className="text-2xl font-black text-teal-900">Profile saved</h2>
          <p className="mt-2 text-sm font-semibold text-teal-800">
            {jobIndicesFromAnswers(answers).length} work block(s) · ready for job applications
          </p>
          {cvPreviewHint ? (
            <p className="mt-2 text-xs font-semibold text-teal-700">{cvPreviewHint}</p>
          ) : null}
          <div className="mt-6 flex flex-wrap justify-center gap-3">
            <button
              type="button"
              disabled={Boolean(downloadBusy)}
              onClick={() => handleDownload("pdf")}
              className="inline-flex items-center gap-2 rounded-2xl border border-teal-600 bg-white px-5 py-3 font-black text-teal-800"
            >
              <Download size={18} />
              {downloadBusy === "pdf" ? "…" : "PDF"}
            </button>
            <button
              type="button"
              onClick={() => navigate("/profile")}
              className="rounded-2xl border border-slate-300 bg-white px-5 py-3 font-black text-slate-800"
            >
              Dashboard
            </button>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className={`${PORTAL_CONTENT_CLASS} mt-8`}>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <Link to="/profile" className="text-sm font-bold text-teal-700 hover:text-teal-900">
          ← Job seeker dashboard
        </Link>
        <input
          ref={fileRef}
          type="file"
          accept=".pdf,.txt,application/pdf,text/plain"
          className="hidden"
          onChange={onFileInputChange}
        />
        <button
          type="button"
          disabled={busy}
          onClick={() => fileRef.current?.click()}
          className="inline-flex items-center gap-2 rounded-xl border border-teal-200 bg-teal-50 px-4 py-2 text-sm font-black text-teal-900"
        >
          <FileUp size={16} />
          Re-upload PDF
        </button>
      </div>

      <div className="mb-6 text-center">
        <h1 className="text-3xl font-black uppercase tracking-wide text-slate-950">Edit resume</h1>
        <div className="mx-auto mt-4 h-2 max-w-xl overflow-hidden rounded-full bg-slate-200">
          <div className="h-full rounded-full bg-teal-600 transition-all" style={{ width: `${progress}%` }} />
        </div>
        <p className="mt-2 text-sm font-semibold text-slate-600">
          Section {sectionIndex + 1} of {sections.length}: {section?.title}
        </p>
        {section?.subtitle ? (
          <p className="mt-1 text-xs font-medium text-slate-400">{section.subtitle}</p>
        ) : null}
        {cvPreviewHint ? (
          <p className="mt-2 text-xs font-semibold text-teal-700">{cvPreviewHint}</p>
        ) : null}
      </div>

      <div className="mx-auto max-w-2xl space-y-4 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        {!section?.fields?.length && section?.allOptional ? (
          <p className="text-sm font-semibold text-slate-500">No entries yet — skip with Next or add one below.</p>
        ) : null}
        {(section?.fields || []).map((field) =>
          field.type === "job_heading" ? (
            <div
              key={field.key}
              className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-200 pt-4 first:border-t-0 first:pt-0"
            >
              <h3 className="text-sm font-black uppercase tracking-wide text-teal-800">{field.label}</h3>
              <button
                type="button"
                disabled={busy}
                onClick={() => removeIndexedBlock(field)}
                className="inline-flex items-center gap-1.5 rounded-xl border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-black uppercase tracking-wide text-red-800 hover:bg-red-100 disabled:opacity-50"
              >
                <Trash2 size={14} />
                Delete
              </button>
            </div>
          ) : field.type === "heading" ? (
            <div
              key={field.key}
              className="border-t border-slate-200 pt-4 first:border-t-0 first:pt-0"
            >
              <h3 className="text-sm font-black uppercase tracking-wide text-teal-800">{field.label}</h3>
            </div>
          ) : (
            <SectionField
              key={field.key}
              field={field}
              value={answers[field.key] || ""}
              onChange={updateField}
              disabled={busy}
            />
          ),
        )}
        {section?.blockPrefix ? (
          <button
            type="button"
            disabled={busy}
            onClick={addIndexedBlock}
            className="inline-flex w-full items-center justify-center gap-2 rounded-2xl border border-dashed border-teal-300 bg-teal-50/50 px-4 py-3 text-sm font-black text-teal-800 hover:bg-teal-50 disabled:opacity-50"
          >
            <Plus size={16} />
            {section.addBlockLabel || "Add entry"}
          </button>
        ) : null}
      </div>

      {err ? (
        <div className="mx-auto mt-4 max-w-2xl rounded-lg border border-red-200 bg-red-50 p-4 text-sm font-semibold text-red-800">
          {err}
        </div>
      ) : null}

      <div className="mx-auto mt-6 flex max-w-2xl gap-3">
        <button
          type="button"
          disabled={busy || sectionIndex <= 0}
          onClick={goBack}
          className="inline-flex flex-1 items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-3 font-black text-slate-700 disabled:opacity-40"
        >
          <ChevronLeft size={18} />
          Back
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={goNext}
          className="inline-flex flex-[2] items-center justify-center gap-2 rounded-2xl bg-teal-600 px-4 py-3 font-black text-white disabled:opacity-50"
        >
          {sectionIndex >= sections.length - 1 ? (busy ? "Saving…" : "Save profile") : "Next"}
          {sectionIndex < sections.length - 1 ? <ChevronRight size={18} /> : null}
        </button>
      </div>
    </main>
  );
}
