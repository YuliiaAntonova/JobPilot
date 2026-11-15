import { motion } from "framer-motion";
import { Link } from "react-router-dom";
import { Bookmark, CalendarDays, FileText, Send } from "lucide-react";

import { PORTAL_CONTENT_CLASS } from "./layout";

function HomeCard({ icon: Icon, title, text, to }) {
  const inner = (
    <>
      <div className="flex h-24 w-24 shrink-0 items-center justify-center rounded-full bg-slate-100 text-orange-600 shadow-inner">
        <Icon size={46} />
      </div>
      <div>
        <h2 className="mb-3 text-2xl font-extrabold text-slate-950">{title}</h2>
        <p className="text-lg font-bold leading-snug text-teal-700">{text}</p>
      </div>
    </>
  );

  if (to) {
    return (
      <motion.div whileHover={{ y: -3 }}>
        <Link
          to={to}
          className="flex w-full items-center gap-7 rounded-lg border border-slate-200 bg-white p-5 text-left shadow-md transition hover:shadow-xl"
        >
          {inner}
        </Link>
      </motion.div>
    );
  }

  return (
    <motion.button
      type="button"
      whileHover={{ y: -3 }}
      className="flex w-full items-center gap-7 rounded-lg border border-slate-200 bg-white p-5 text-left shadow-md transition hover:shadow-xl"
      onClick={() => window.alert("This section will be available in the next version.")}
    >
      {inner}
    </motion.button>
  );
}

export default function HomePage() {
  return (
    <main className={`${PORTAL_CONTENT_CLASS} mt-12`}>
      <div className="space-y-5">
        <HomeCard
          icon={FileText}
          title="Resume"
          text="Build your resume with the chat wizard or open your job seeker dashboard."
          to="/resume/create"
        />
        <HomeCard
          icon={Send}
          title="New application"
          text="Upload a job description — score, ATS tips, and resume tailoring (safe YAML)."
          to="/new"
        />
        <HomeCard
          icon={Bookmark}
          title="My company list"
          text="Companies you saved for future applications."
          to="/saved"
        />
        <HomeCard
          icon={CalendarDays}
          title="Job search calendar"
          text="Deadlines, interviews, and reminders in one place."
          to="/calendar"
        />
      </div>
    </main>
  );
}
