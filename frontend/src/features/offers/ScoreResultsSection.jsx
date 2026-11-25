import OfferResumeSection from "../resume/OfferResumeSection";
import { analysisScoreCalculated } from "./newOfferMeta";

export default function ScoreResultsSection({
  analysis,
  setAnalysis,
  description,
  meta,
  jobId,
  companyName,
  jobTitle,
  handleResumePersist,
  setSaveHint,
  setResumePaste,
  setUseCabinetProfile,
  useCabinetProfile,
  goReply,
}) {
  if (!analysis) return null;

  return (
    <div className="mt-8 space-y-6 border-t border-slate-200 pt-6">
      <h3 className="text-xl font-black text-slate-950">Analysis results</h3>

      {analysisScoreCalculated(analysis) ? (
        <div
          key={`score-${analysis.match_score}-${(analysis.ats_suggestions || []).length}-${analysis.comparison_summary || ""}`}
          className="rounded-lg border border-teal-200 bg-teal-50 p-4"
        >
          <p className="text-lg font-black text-teal-900">
            Score: {analysis.match_score} {analysis.match_rank_label ? `— ${analysis.match_rank_label}` : ""}
          </p>
          {analysis.comparison_summary ? (
            <p className="mt-2 font-semibold text-slate-800">{analysis.comparison_summary}</p>
          ) : null}
          {analysis.skills_available === false ? (
            <p className="mt-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm font-semibold text-amber-900">
              Job skills were not extracted — JobBERT found no entities in the Skills & Requirements block.
            </p>
          ) : null}
          {analysis.matched_skills?.length ? (
            <p className="mt-3 text-sm font-semibold text-teal-900">
              <span className="font-black">Matched:</span> {analysis.matched_skills.join(", ")}
            </p>
          ) : null}
          {analysis.unmatched_skills?.length ? (
            <p className="mt-2 text-sm font-semibold text-amber-900">
              <span className="font-black">Unmatched:</span> {analysis.unmatched_skills.join(", ")}
            </p>
          ) : null}
        </div>
      ) : (
        <div className="rounded-lg border border-slate-200 bg-slate-100 p-4">
          <p className="text-lg font-black text-slate-800">
            Score: 0 — {analysis.match_rank_label || "No resume provided"}
          </p>
          <p className="mt-2 text-sm font-semibold text-slate-600">
            {analysis.comparison_summary ||
              "Provide resume text from your dashboard or in the field below (at least 80 characters) and run analysis again."}
          </p>
        </div>
      )}

      {analysisScoreCalculated(analysis) ? (
        <OfferResumeSection
          analysis={analysis}
          onAnalysisChange={setAnalysis}
          jdText={description.trim() || meta?.job_description_text || ""}
          jobId={jobId}
          companyName={companyName}
          jobTitle={jobTitle}
          onPersist={handleResumePersist}
          onSaveHint={setSaveHint}
          onProfileSaved={(text) => {
            setResumePaste(text);
            setUseCabinetProfile(true);
          }}
          initialUseCabinetProfile={useCabinetProfile}
        />
      ) : null}

      <div className="rounded-xl border-2 border-teal-200 bg-teal-50/90 p-6 shadow-inner">
        <p className="text-sm font-black uppercase tracking-wide text-teal-900">Step 2</p>
        <h4 className="mt-1 text-xl font-black text-slate-950">Cover letter</h4>
        <p className="mt-3 text-sm font-semibold text-slate-700">
          After tailoring your resume, open step 2 and generate a cover letter for this job.
        </p>
        <button
          type="button"
          onClick={goReply}
          className="mt-5 w-full rounded-md bg-teal-700 px-5 py-4 text-lg font-black text-white shadow-sm hover:bg-teal-800 md:w-auto"
        >
          Next: cover letter →
        </button>
      </div>
    </div>
  );
}
