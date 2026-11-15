import { useEffect, useRef, useState } from "react";
import { PORTAL_CONTENT_CLASS } from "./layout";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  BriefcaseBusiness,
  CheckCircle2,
  ChevronRight,
  FileText,
  FileUp,
  GraduationCap,
  Languages,
  Mail,
  MapPin,
  MessageSquare,
  Phone,
  Sparkles,
  Trash2,
  User,
  Wrench,
} from "lucide-react";
import {
  deleteProfileOnServer,
  fetchProfileFromServer,
  getProfilePayload,
  getSession,
  profileHasResume,
  updateDesiredRoleOnServer,
  uploadResumePdfToServer,
} from "../lib/jobseekerProfile";
import ResumeDownloadBar from "../features/resume/ResumeDownloadBar";
import {
  displayName,
  educationForDisplay,
  experienceForDisplay,
  languagesLine,
  profileContact,
  profileSummary,
  skillsForDisplay,
} from "../lib/profileDisplay";

function ProfileField({ label, value, icon: Icon }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
      <div className="mb-2 flex items-center gap-2 text-sm font-black uppercase tracking-wide text-teal-700">
        <Icon size={17} /> {label}
      </div>
      <p className="break-words text-lg font-bold text-slate-900">{value || "—"}</p>
    </div>
  );
}

export default function ProfilePage() {
  const session = getSession();
  const navigate = useNavigate();
  const fileRef = useRef(null);

  const [structured, setStructured] = useState(() => getProfilePayload()?.structured ?? null);
  const [desiredRole, setDesiredRole] = useState(() => getProfilePayload()?.desired_role ?? "");
  const [source, setSource] = useState(() => getProfilePayload()?.source ?? null);
  const [profileText, setProfileText] = useState(() => getProfilePayload()?.profile_text ?? "");
  const [updatedAt, setUpdatedAt] = useState(() => getProfilePayload()?.updatedAt ?? null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [savedHint, setSavedHint] = useState("");

  useEffect(() => {
    fetchProfileFromServer()
      .then((p) => {
        if (p?.structured) setStructured(p.structured);
        if (p && "desired_role" in p) setDesiredRole(p.desired_role ?? "");
        if (p?.source) setSource(p.source);
        if (typeof p?.profile_text === "string") setProfileText(p.profile_text);
        if (p?.updatedAt) setUpdatedAt(p.updatedAt);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    const sync = () => {
      const p = getProfilePayload();
      if (p?.structured) setStructured(p.structured);
      if (p && "desired_role" in p) setDesiredRole(p.desired_role ?? "");
      if (p?.source) setSource(p.source);
      if (typeof p?.profile_text === "string") setProfileText(p.profile_text);
      if (p?.updatedAt) setUpdatedAt(p.updatedAt);
    };
    window.addEventListener("jobseeker-profile-updated", sync);
    return () => window.removeEventListener("jobseeker-profile-updated", sync);
  }, []);

  if (!session?.email) {
    return <Navigate to="/login" replace state={{ from: "/profile" }} />;
  }

  const contact = profileContact(structured || {});
  const hasProfile = profileHasResume(structured);
  const summary = profileSummary(structured || {});
  const skills = skillsForDisplay(structured || {});
  const experiences = experienceForDisplay(structured || {});

  async function runUpload(file) {
    if (!file) return;
    setErr("");
    setSavedHint("");
    setBusy(true);
    try {
      await uploadResumePdfToServer(file);
      const p = getProfilePayload();
      if (p?.structured) setStructured(p.structured);
      if (p?.source) setSource(p.source);
      setSavedHint("Profile updated from resume and saved locally in the browser.");
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function saveDesiredRoleOnly() {
    setErr("");
    try {
      await updateDesiredRoleOnServer(desiredRole);
      setSavedHint("Desired role saved locally.");
    } catch (e) {
      setErr(String(e));
    }
  }

  async function deleteProfile() {
    if (!window.confirm("Delete the saved resume and profile from your dashboard?")) return;
    setErr("");
    try {
      await deleteProfileOnServer();
      setStructured(null);
      setDesiredRole("");
      setSource(null);
      setSavedHint("Profile deleted.");
    } catch (e) {
      setErr(String(e));
    }
  }

  return (
    <main className={`${PORTAL_CONTENT_CLASS} mt-8`}>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <Link to="/" className="text-sm font-bold text-teal-700 hover:text-teal-900">
          ← Back to home
        </Link>
        <p className="text-sm font-semibold text-slate-600">
          Signed in as <strong className="text-slate-900">{session.email}</strong>
        </p>
      </div>

      <h1 className="text-5xl font-black text-slate-950">Job seeker dashboard</h1>
      <p className="mt-4 text-xl font-medium text-slate-800">
        Create a resume via the career interview or upload a PDF — your profile is saved in the database.
      </p>

      <ResumeDownloadBar structured={structured} className="mt-6" size="lg" alwaysShow />

      <input
        ref={fileRef}
        type="file"
        accept=".pdf,application/pdf"
        className="hidden"
        onChange={(e) => {
          runUpload(e.target.files?.[0]);
          e.target.value = "";
        }}
      />

      <div className="mt-7 space-y-5">
        <motion.div whileHover={{ y: -3 }}>
          <Link
            to="/resume/create"
            className="flex w-full items-center gap-7 rounded-lg border border-slate-200 bg-white p-5 text-left shadow-md transition hover:shadow-xl"
          >
            <div className="flex h-24 w-24 shrink-0 items-center justify-center rounded-full bg-teal-50 text-teal-700 shadow-inner">
              <MessageSquare size={46} />
            </div>
            <div className="min-w-0 flex-1">
              <h2 className="text-2xl font-extrabold text-slate-950">Build your resume via chat</h2>
              <p className="mt-3 text-lg font-bold leading-snug text-teal-700">
                Answer the questions — your profile will be saved to your dashboard automatically.
              </p>
            </div>
            <ChevronRight size={34} className="shrink-0 text-slate-900" />
          </Link>
        </motion.div>

        <motion.button
          type="button"
          whileHover={{ y: -3 }}
          disabled={busy}
          onClick={() => fileRef.current?.click()}
          className="flex w-full items-center gap-7 rounded-lg border border-slate-200 bg-white p-5 text-left shadow-md transition hover:shadow-xl disabled:opacity-60"
        >
          <div className="flex h-24 w-24 shrink-0 items-center justify-center rounded-full bg-slate-100 text-orange-600 shadow-inner">
            <FileUp size={46} />
          </div>
          <div className="min-w-0 flex-1">
            <h2 className="text-2xl font-extrabold text-slate-950">Upload resume (PDF)</h2>
            <p className="mt-3 text-lg font-bold leading-snug text-teal-700">
              Chat alternative: we extract structure from the PDF via the server LLM.
            </p>
          </div>
          <ChevronRight size={34} className="shrink-0 text-slate-900" />
        </motion.button>

        {err ? (
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm font-semibold text-red-800">{err}</div>
        ) : null}
        {savedHint ? (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm font-semibold text-emerald-800">
            {savedHint}
          </div>
        ) : null}

        <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-md">
          <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
            <div className="flex items-start gap-4">
              <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full bg-teal-700 text-white">
                <User size={32} />
              </div>
              <div>
                <p className="mb-1 text-sm font-bold uppercase tracking-wide text-teal-700">Your profile</p>
                <h2 className="text-3xl font-black text-slate-950">{hasProfile ? displayName(structured) : "Your name"}</h2>
                <p className="mt-1 text-xl font-bold text-slate-700">
                  {desiredRole || "Target role"}
                </p>
                {source ? (
                  <p className="mt-2 text-sm font-semibold text-slate-500">
                    Source:{" "}
                    {source === "chat"
                      ? "chat wizard"
                      : source === "tailored"
                        ? "job tailoring"
                        : "PDF upload"}
                    {updatedAt ? (
                      <span className="ml-2">
                        · updated{" "}
                        {new Date(updatedAt).toLocaleString("en-US", {
                          day: "numeric",
                          month: "short",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </span>
                    ) : null}
                  </p>
                ) : null}
              </div>
            </div>
            {hasProfile ? (
              <span className="flex items-center gap-2 rounded-full bg-emerald-50 px-4 py-2 text-sm font-black text-emerald-700">
                <CheckCircle2 size={17} /> Profile ready
              </span>
            ) : (
              <span className="rounded-full bg-slate-100 px-4 py-2 text-sm font-black text-slate-500">No data</span>
            )}
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <ProfileField icon={MapPin} label="City" value={contact.location} />
            <ProfileField icon={Phone} label="Phone" value={contact.phone} />
            <ProfileField icon={Mail} label="Email" value={contact.email || session.email} />
            <ProfileField icon={Languages} label="Languages" value={languagesLine(structured)} />
          </div>

          {profileText.trim() ? (
            <div className="mt-5 rounded-lg border border-teal-100 bg-teal-50/60 p-4">
              <p className="text-sm font-black uppercase tracking-wide text-teal-900">
                Current resume text (for score and applications)
              </p>
              <p className="mt-1 text-xs font-semibold text-slate-600">
                {profileText.length} characters
                {source === "tailored" ? " · saved after job tailoring" : ""}
              </p>
              <pre className="mt-3 max-h-48 overflow-y-auto whitespace-pre-wrap rounded-lg border border-slate-200 bg-white p-3 font-mono text-xs text-slate-800">
                {profileText.slice(0, 4000)}
                {profileText.length > 4000 ? "\n…" : ""}
              </pre>
            </div>
          ) : null}

          {summary ? (
            <div className="mt-6 rounded-2xl bg-slate-50 p-5">
              <h3 className="mb-2 font-black text-slate-950">About</h3>
              <p className="whitespace-pre-wrap text-slate-700">{summary}</p>
            </div>
          ) : null}

          <div className="mt-5 rounded-lg border border-slate-200 bg-slate-50 p-4 md:col-span-2">
            <div className="mb-2 flex items-center gap-2 text-sm font-black uppercase tracking-wide text-teal-700">
              <BriefcaseBusiness size={17} /> Target role
            </div>
            <input
              type="text"
              value={desiredRole}
              onChange={(e) => setDesiredRole(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-lg font-bold text-slate-900 outline-none focus:border-teal-700"
              placeholder="e.g. Junior Data Engineer"
            />
            <button
              type="button"
              onClick={saveDesiredRoleOnly}
              className="mt-3 rounded-md bg-slate-200 px-4 py-2 text-sm font-black text-slate-800 hover:bg-slate-300"
            >
              Save role for job analysis
            </button>
          </div>

          <div className="mt-5 rounded-lg border border-slate-200 bg-slate-50 p-4">
            <div className="mb-3 flex items-center gap-2 text-sm font-black uppercase tracking-wide text-teal-700">
              <Wrench size={17} /> Skills
            </div>
            {skills.length ? (
              <div className="flex flex-wrap gap-2">
                {skills.map((skill) => (
                  <span
                    key={String(skill)}
                    className="rounded-full bg-white px-3 py-2 text-sm font-black text-slate-700 shadow-sm"
                  >
                    {String(skill)}
                  </span>
                ))}
              </div>
            ) : (
              <p className="font-semibold text-slate-500">Build your resume via chat or upload a PDF.</p>
            )}
          </div>

          <div className="mt-5 rounded-lg border border-slate-200 bg-slate-50 p-4">
            <div className="mb-3 flex items-center gap-2 text-sm font-black uppercase tracking-wide text-teal-700">
              <GraduationCap size={17} /> Experience from resume
            </div>
            {experiences.length ? (
              <div className="space-y-3">
                {experiences.map((ex, i) => (
                  <div key={`${ex.title}-${ex.company}-${i}`} className="rounded-lg bg-white p-4 shadow-sm">
                    <h3 className="font-black text-slate-950">
                      {ex.title || "—"} {ex.company ? `· ${ex.company}` : ""}
                    </h3>
                    {ex.dates ? <p className="mt-1 text-sm font-semibold text-slate-500">{ex.dates}</p> : null}
                    {ex.context ? (
                      <p className="mt-2 text-sm font-semibold italic text-slate-600">
                        <span className="font-black not-italic text-slate-700">Project context:</span> {ex.context}
                      </p>
                    ) : null}
                    {ex.bullets.length ? (
                      <ul className="mt-2 list-disc pl-5 text-sm font-semibold text-slate-600">
                        {ex.bullets.slice(0, 8).map((h, j) => (
                          <li key={j}>{h}</li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                ))}
              </div>
            ) : (
              <p className="font-semibold text-slate-500">This section appears after you create or upload a resume.</p>
            )}
          </div>

          <div className="mt-8 flex flex-wrap gap-3">
            <button
              type="button"
              disabled={!hasProfile}
              onClick={() => navigate("/resume/view")}
              className="inline-flex items-center gap-2 rounded-2xl bg-teal-600 px-6 py-3 font-black text-white shadow hover:bg-teal-700 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <FileText size={18} /> View resume
            </button>
            <button
              type="button"
              disabled={!hasProfile}
              onClick={() => navigate("/resume/create?edit=1")}
              className="rounded-2xl border border-slate-300 bg-white px-6 py-3 font-black hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Edit
            </button>
            <button
              type="button"
              disabled={!hasProfile || busy}
              onClick={deleteProfile}
              className="inline-flex items-center gap-2 rounded-2xl border border-red-200 bg-red-50 px-6 py-3 font-black text-red-600 hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Trash2 size={18} /> Delete
            </button>
          </div>

          <button
            type="button"
            disabled={busy}
            onClick={() => fileRef.current?.click()}
            className="mt-6 flex w-full items-center justify-center gap-2 rounded-md bg-teal-700 px-5 py-4 text-lg font-black text-white shadow-sm hover:bg-teal-800 disabled:opacity-60"
          >
            <Sparkles size={22} /> {busy ? "Processing…" : "Refresh profile from PDF"}
          </button>

          <p className="mt-4 text-center text-sm font-semibold text-slate-600">
            Next:{" "}
            <Link to="/new" className="font-black text-teal-700 hover:text-teal-900">
              New application
            </Link>{" "}
            — your profile text will be used to compare against the job.
          </p>
        </section>
      </div>
    </main>
  );
}
