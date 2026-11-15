/** Compact insight panel after AI tailor — data already from meta call. */

function InsightBlock({ title, badge, children }) {
  if (!children) return null;
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <p className="text-[11px] font-black uppercase tracking-wide text-slate-500">
        {badge ? `${badge} · ` : ""}
        {title}
      </p>
      <div className="mt-2 text-sm font-semibold text-slate-800">{children}</div>
    </div>
  );
}

function TagList({ items }) {
  if (!items?.length) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((item, i) => (
        <span key={i} className="rounded-full bg-teal-50 px-2.5 py-1 text-xs font-bold text-teal-900">
          {item}
        </span>
      ))}
    </div>
  );
}

function BulletList({ items, className = "text-slate-700" }) {
  if (!items?.length) return null;
  return (
    <ul className={`list-inside list-disc space-y-1 ${className}`}>
      {items.map((item, i) => (
        <li key={i}>{item}</li>
      ))}
    </ul>
  );
}

export default function ResumeAiInsights({ meta }) {
  if (!meta) return null;

  const hasContent =
    meta.ats_keywords_top10?.length ||
    meta.action_verbs?.length ||
    meta.career_advisor_tips?.length ||
    meta.bullet_improvements?.length ||
    meta.skill_match_ideas?.length ||
    meta.recruiter_strengths?.length ||
    meta.recruiter_gaps?.length ||
    meta.recruiter_feedback ||
    meta.phrase_substitutions_applied?.length;

  if (!hasContent) return null;

  return (
    <div className="mt-5 space-y-3 rounded-lg border border-slate-200 bg-slate-50/80 p-4">
      <p className="text-sm font-black text-slate-900">AI resume insights</p>
      <p className="text-xs font-semibold text-slate-500">
        From a single meta request during tailoring — no extra LLM calls.
      </p>

      <div className="grid gap-3 md:grid-cols-2">
        <InsightBlock title="KEYWORDS (ATS top 10)" badge="KEYWORDS">
          <TagList items={meta.ats_keywords_top10} />
        </InsightBlock>

        <InsightBlock title="ACTION VERBS" badge="VERBS">
          <TagList items={meta.action_verbs} />
        </InsightBlock>

        <InsightBlock title="Career Advisor — 5 tips" badge="ROLE PLAY">
          <BulletList items={meta.career_advisor_tips} />
        </InsightBlock>

        <InsightBlock title="SKILL MATCH — ideas" badge="SKILL MATCH">
          <BulletList items={meta.skill_match_ideas} />
        </InsightBlock>

        <InsightBlock title="REVISE — bullet improvements" badge="REVISE">
          <BulletList items={meta.bullet_improvements} />
        </InsightBlock>

        <InsightBlock title="SKILL COMPARISON — phrase swaps" badge="COMPARE">
          {meta.phrase_substitutions_applied?.length ? (
            <ul className="space-y-2 text-xs">
              {meta.phrase_substitutions_applied.map((pair, i) => (
                <li key={i} className="rounded border border-slate-100 bg-slate-50 p-2">
                  <span className="text-slate-600">{pair.from}</span>
                  <span className="mx-1 font-black text-teal-700">→</span>
                  <span className="text-teal-900">{pair.to}</span>
                </li>
              ))}
            </ul>
          ) : null}
        </InsightBlock>
      </div>

      {(meta.recruiter_strengths?.length ||
        meta.recruiter_gaps?.length ||
        meta.recruiter_feedback) && (
        <InsightBlock title="ROLE PLAY (Employer / Recruiter)" badge="EMPLOYER">
          {meta.recruiter_feedback ? (
            <p className="mb-2 italic text-slate-700">{meta.recruiter_feedback}</p>
          ) : null}
          {meta.recruiter_strengths?.length ? (
            <p className="mt-2 font-black text-emerald-800">Strengths</p>
          ) : null}
          <BulletList items={meta.recruiter_strengths} className="text-emerald-900" />
          {meta.recruiter_gaps?.length ? (
            <p className="mt-3 font-black text-amber-800">Gaps</p>
          ) : null}
          <BulletList items={meta.recruiter_gaps} className="text-amber-900" />
        </InsightBlock>
      )}
    </div>
  );
}