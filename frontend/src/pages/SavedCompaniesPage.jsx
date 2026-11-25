import { useCallback, useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { Bookmark } from "lucide-react";

import { fetchApplications, patchApplicationTracker } from "../lib/offerDraftServer";
import { getSession, getToken } from "../lib/jobseekerProfile";
import { PORTAL_CONTENT_CLASS } from "../portal/layout";

const PIPELINE_OPTIONS = [
  { value: "interested", label: "Interested" },
  { value: "applied", label: "Applied" },
  { value: "interview", label: "Interview" },
  { value: "offer", label: "Offer" },
  { value: "rejected", label: "Rejected" },
];

const SKILLS_PREVIEW = 8;

function SkillsCell({ skills }) {
  const [expanded, setExpanded] = useState(false);
  const list = Array.isArray(skills) ? skills.filter(Boolean) : [];
  if (!list.length) {
    return <span className="text-slate-400">—</span>;
  }
  const canExpand = list.length > SKILLS_PREVIEW;
  const shown = expanded || !canExpand ? list : list.slice(0, SKILLS_PREVIEW);
  const rest = list.length - SKILLS_PREVIEW;
  return (
    <div className={`flex flex-wrap gap-1 ${expanded ? "max-w-md" : "max-w-xs"}`}>
      {shown.map((skill) => (
        <span
          key={skill}
          className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-semibold text-slate-700"
        >
          {skill}
        </span>
      ))}
      {canExpand ? (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="rounded bg-teal-50 px-1.5 py-0.5 text-[11px] font-bold text-teal-800 hover:bg-teal-100"
          title={expanded ? "Collapse" : `Show ${rest} more`}
        >
          {expanded ? "collapse" : `+${rest}`}
        </button>
      ) : null}
    </div>
  );
}

export default function SavedCompaniesPage() {
  const session = getSession();
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [includeClosed, setIncludeClosed] = useState(false);
  const [busy, setBusy] = useState(true);
  const [err, setErr] = useState("");
  const [rowBusy, setRowBusy] = useState("");

  const reload = useCallback(async () => {
    setBusy(true);
    setErr("");
    const data = await fetchApplications({ includeClosed });
    if (data.error === "not_logged_in") {
      setErr("Sign in to see your saved job postings.");
      setItems([]);
      setTotal(0);
    } else if (data.error) {
      setErr(typeof data.error === "string" ? data.error : JSON.stringify(data.error));
      setItems([]);
      setTotal(0);
    } else {
      setItems(data.items);
      setTotal(data.total);
    }
    setBusy(false);
  }, [includeClosed]);

  useEffect(() => {
    reload();
  }, [reload]);

  if (!session?.email || !getToken()) {
    return <Navigate to="/login" replace />;
  }

  async function onPatch(jobId, patch) {
    setRowBusy(jobId);
    setErr("");
    // Optimistic UI so select does not snap back before the request finishes
    if (patch.pipeline_status != null) {
      setItems((prev) =>
        prev.map((row) =>
          row.job_id === jobId ? { ...row, pipeline_status: patch.pipeline_status } : row,
        ),
      );
    }
    const res = await patchApplicationTracker(jobId, patch);
    if (!res.ok) {
      setErr(typeof res.error === "string" ? res.error : JSON.stringify(res.error));
      setRowBusy("");
      await reload();
      return;
    }
    if (res.item) {
      setItems((prev) => {
        const next = prev.map((row) => (row.job_id === jobId ? { ...row, ...res.item } : row));
        if (!includeClosed) {
          return next.filter((row) => !row.closed);
        }
        return next;
      });
      if (res.item.closed && !includeClosed) {
        setTotal((t) => Math.max(0, t - 1));
      }
      if (
        patch.pipeline_status &&
        res.item.status &&
        res.item.status !== patch.pipeline_status
      ) {
        setErr(
          `DB status mismatch: UI=${patch.pipeline_status}, DB status=${res.item.status}. Restart the API (uvicorn).`,
        );
      }
    } else {
      await reload();
    }
    setRowBusy("");
  }

  return (
    <main className={`${PORTAL_CONTENT_CLASS} mt-12`}>
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="mb-2 flex items-center gap-3 text-teal-700">
            <Bookmark size={28} />
            <h1 className="text-3xl font-black text-slate-950">My company list</h1>
          </div>
          <p className="text-base font-semibold text-slate-600">
            Jobs after generating cv_tailored. Status and application date are updated here.
          </p>
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-sm font-bold text-slate-700">
          <input
            type="checkbox"
            className="h-4 w-4 accent-teal-700"
            checked={includeClosed}
            onChange={(e) => setIncludeClosed(e.target.checked)}
          />
          Show closed
        </label>
      </div>

      {err ? (
        <p className="mb-4 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-semibold text-rose-800">
          {err}
        </p>
      ) : null}

      {busy ? (
        <p className="rounded-lg bg-white p-8 text-center text-lg font-bold text-slate-500 shadow-md">
          Loading…
        </p>
      ) : items.length === 0 ? (
        <div className="rounded-lg bg-white p-10 text-center shadow-md">
          <p className="text-lg font-bold text-slate-700">
            Nothing here yet. Generate cv_tailored in New application — the job will appear here.
          </p>
          <Link to="/new" className="mt-6 inline-block font-bold text-teal-700 hover:text-teal-900">
            → New application
          </Link>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-md">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-xs font-black uppercase tracking-wide text-slate-600">
              <tr>
                <th className="px-4 py-3">Company</th>
                <th className="px-4 py-3">Role</th>
                <th className="px-4 py-3">Skills</th>
                <th className="px-4 py-3">Applied</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-center">Closed</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => {
                const disabled = rowBusy === row.job_id;
                return (
                  <tr
                    key={row.job_id}
                    className={`border-b border-slate-100 ${row.closed ? "bg-slate-50 opacity-70" : ""}`}
                  >
                    <td className="px-4 py-3">
                      <input
                        type="text"
                        disabled={disabled}
                        value={row.company_name || ""}
                        onChange={(e) =>
                          setItems((prev) =>
                            prev.map((r) =>
                              r.job_id === row.job_id ? { ...r, company_name: e.target.value } : r,
                            ),
                          )
                        }
                        onBlur={(e) => {
                          if ((e.target.value || "") !== (row.company_name || "")) {
                            onPatch(row.job_id, { company_name: e.target.value });
                          }
                        }}
                        placeholder="Company"
                        className="w-full min-w-[8rem] rounded-md border border-slate-200 px-2 py-1.5 font-bold text-slate-900 outline-none focus:border-teal-600"
                      />
                    </td>
                    <td className="px-4 py-3">
                      <input
                        type="text"
                        disabled={disabled}
                        value={row.job_title || ""}
                        onChange={(e) =>
                          setItems((prev) =>
                            prev.map((r) =>
                              r.job_id === row.job_id ? { ...r, job_title: e.target.value } : r,
                            ),
                          )
                        }
                        onBlur={(e) => {
                          if ((e.target.value || "") !== (row.job_title || "")) {
                            onPatch(row.job_id, { job_title: e.target.value });
                          }
                        }}
                        placeholder="Role"
                        className="w-full min-w-[8rem] rounded-md border border-slate-200 px-2 py-1.5 font-semibold text-slate-800 outline-none focus:border-teal-600"
                      />
                    </td>
                    <td className="px-4 py-3">
                      <SkillsCell skills={row.skills} />
                    </td>
                    <td className="px-4 py-3">
                      <input
                        type="date"
                        disabled={disabled}
                        value={(row.applied_at || "").slice(0, 10)}
                        onChange={(e) => onPatch(row.job_id, { applied_at: e.target.value || null })}
                        className="rounded-md border border-slate-200 px-2 py-1.5 text-slate-800 outline-none focus:border-teal-600"
                      />
                    </td>
                    <td className="px-4 py-3">
                      <select
                        disabled={disabled}
                        value={row.pipeline_status || "interested"}
                        onChange={(e) => onPatch(row.job_id, { pipeline_status: e.target.value })}
                        className="rounded-md border border-slate-200 px-2 py-1.5 font-semibold text-slate-800 outline-none focus:border-teal-600"
                      >
                        {PIPELINE_OPTIONS.map((opt) => (
                          <option key={opt.value} value={opt.value}>
                            {opt.label}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <input
                        type="checkbox"
                        disabled={disabled}
                        checked={Boolean(row.closed)}
                        onChange={(e) => onPatch(row.job_id, { closed: e.target.checked })}
                        className="h-4 w-4 accent-teal-700"
                        title="Closed / no longer active"
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="border-t border-slate-100 px-4 py-3 text-xs font-semibold text-slate-500">
            Total: {total}
          </p>
        </div>
      )}

      <Link to="/" className="mt-8 inline-block font-bold text-teal-700 hover:text-teal-900">
        ← Back to home
      </Link>
    </main>
  );
}
