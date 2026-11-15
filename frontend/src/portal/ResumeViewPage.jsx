import { Link, Navigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  BriefcaseBusiness,
  GraduationCap,
  Languages,
  Mail,
  MapPin,
  Phone,
  User,
  Wrench,
} from "lucide-react";
import { PORTAL_CONTENT_CLASS } from "./layout";
import { getProfilePayload, getProfileText, getSession } from "../lib/jobseekerProfile";
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

function InfoBlock({ label, value, icon: Icon }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <div className="mb-1 flex items-center gap-2 text-sm font-bold uppercase tracking-wide text-slate-500">
        {Icon ? <Icon size={16} /> : null} {label}
      </div>
      <p className="text-lg font-bold text-slate-900">{value || "Not specified"}</p>
    </div>
  );
}

export default function ResumeViewPage() {
  const session = getSession();
  const payload = getProfilePayload();
  const structured = payload?.structured ?? null;
  const profileText = getProfileText();

  if (!session?.email) {
    return <Navigate to="/login" replace state={{ from: "/resume/view" }} />;
  }

  if (!structured && !profileText) {
    return (
      <main className={`${PORTAL_CONTENT_CLASS} mt-8`}>
        <Link to="/profile" className="text-sm font-bold text-teal-700 hover:text-teal-900">
          ← Dashboard
        </Link>
        <p className="mt-8 text-xl font-semibold text-slate-700">
          No resume yet.{" "}
          <Link to="/resume/create" className="font-black text-teal-700 hover:text-teal-900">
            Create with the chat wizard
          </Link>
        </p>
      </main>
    );
  }

  const contact = profileContact(structured || {});
  const summary = profileSummary(structured || {});
  const skills = skillsForDisplay(structured || {});
  const experiences = experienceForDisplay(structured || {});
  const education = educationForDisplay(structured || {});
  const desiredRole = payload?.desired_role || structured?.basics?.headline || "";

  return (
    <main className={`${PORTAL_CONTENT_CLASS} mt-8`}>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <Link to="/profile" className="text-sm font-bold text-teal-700 hover:text-teal-900">
          ← Job seeker dashboard
        </Link>
        <div className="flex flex-wrap gap-2">
          <ResumeDownloadBar structured={structured} size="md" />
          <Link
            to="/resume/create?edit=1"
            className="rounded-md bg-slate-200 px-4 py-2 text-sm font-black text-slate-800 hover:bg-slate-300"
          >
            Edit
          </Link>
        </div>
      </div>

      <motion.article
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        className="rounded-3xl border border-slate-200 bg-white p-8 shadow-md"
      >
        <header className="mb-8 border-b border-slate-200 pb-6">
          <p className="text-sm font-bold uppercase tracking-wide text-teal-700">Resume</p>
          <h1 className="mt-2 text-4xl font-black text-slate-950">{displayName(structured)}</h1>
          {desiredRole ? (
            <p className="mt-2 text-xl font-bold text-slate-700">{desiredRole}</p>
          ) : null}
        </header>

        <div className="grid gap-4 md:grid-cols-2">
          <InfoBlock icon={MapPin} label="City" value={contact.location} />
          <InfoBlock icon={Phone} label="Phone" value={contact.phone} />
          <InfoBlock icon={Mail} label="Email" value={contact.email} />
          <InfoBlock icon={Languages} label="Languages" value={languagesLine(structured)} />
        </div>

        {summary ? (
          <section className="mt-6 rounded-2xl bg-slate-50 p-5">
            <h2 className="mb-2 flex items-center gap-2 font-black text-slate-950">
              <User size={18} /> About
            </h2>
            <p className="whitespace-pre-wrap text-slate-700">{summary}</p>
          </section>
        ) : null}

        {skills.length ? (
          <section className="mt-6">
            <h2 className="mb-3 flex items-center gap-2 font-black text-slate-950">
              <Wrench size={18} /> Skills
            </h2>
            <div className="flex flex-wrap gap-2">
              {skills.map((skill) => (
                <span
                  key={String(skill)}
                  className="rounded-full border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-bold text-slate-700"
                >
                  {String(skill)}
                </span>
              ))}
            </div>
          </section>
        ) : null}

        {experiences.length ? (
          <section className="mt-6">
            <h2 className="mb-3 flex items-center gap-2 font-black text-slate-950">
              <BriefcaseBusiness size={18} /> Work experience
            </h2>
            <div className="space-y-4">
              {experiences.map((ex, i) => (
                <div key={i} className="rounded-xl border border-slate-200 bg-slate-50 p-4">
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
                      {ex.bullets.map((h, j) => (
                        <li key={j}>{h}</li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              ))}
            </div>
          </section>
        ) : null}

        {education.length ? (
          <section className="mt-6">
            <h2 className="mb-3 flex items-center gap-2 font-black text-slate-950">
              <GraduationCap size={18} /> Education
            </h2>
            <div className="space-y-3">
              {education.map((edu, i) => (
                <div key={i} className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                  <p className="font-black text-slate-950">
                    {[edu.degree, edu.school].filter(Boolean).join(" — ") || "—"}
                  </p>
                  {edu.period ? (
                    <p className="mt-1 text-sm font-semibold text-slate-500">{edu.period}</p>
                  ) : null}
                  {edu.note ? <p className="mt-1 font-semibold text-slate-600">{edu.note}</p> : null}
                </div>
              ))}
            </div>
          </section>
        ) : null}

        {profileText ? (
          <details className="mt-8 rounded-xl border border-slate-200 bg-slate-50 p-4">
            <summary className="cursor-pointer font-black text-slate-800">Profile text for job analysis</summary>
            <pre className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap text-sm font-medium text-slate-600">
              {profileText}
            </pre>
          </details>
        ) : null}
      </motion.article>
    </main>
  );
}