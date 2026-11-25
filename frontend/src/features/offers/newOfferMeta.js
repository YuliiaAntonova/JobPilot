/** Helpers for New application / offer draft meta. */

export function analysisScoreCalculated(analysis) {
  if (!analysis || typeof analysis !== "object") return false;
  if (analysis.scoring_skipped === true) return false;
  return analysis.match_score != null;
}

/** Manual company/title from UI — always win over JD heuristics. */
export function withJobMeta(analysis, companyName, jobTitle) {
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
