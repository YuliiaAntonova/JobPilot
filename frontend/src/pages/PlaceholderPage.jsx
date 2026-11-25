import { Link } from "react-router-dom";

import { PORTAL_CONTENT_CLASS } from "../portal/layout";

export default function PlaceholderPage({ title, hint }) {
  return (
    <main className={`${PORTAL_CONTENT_CLASS} mt-20 rounded-lg bg-white p-10 text-center shadow-md`}>
      <h1 className="text-3xl font-black text-slate-950">{title}</h1>
      <p className="mt-4 text-lg text-slate-600">{hint}</p>
      <Link to="/" className="mt-8 inline-block font-bold text-teal-700 hover:text-teal-900">
        ← Back to home
      </Link>
    </main>
  );
}
