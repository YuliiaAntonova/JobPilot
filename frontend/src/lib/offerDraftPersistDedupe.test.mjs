import assert from "node:assert/strict";
import {
  createOfferDraftPutGate,
  offerDraftPersistFingerprint,
} from "./offerDraftPersistDedupe.js";

const body = {
  jd_text: "JD",
  resume_paste: "resume",
  cover_letter_text: "",
  tailored_resume_text: "tailored",
  model: "gpt",
  analysis: {
    company_name: "Databricks",
    job_title: "DE",
    match_score: 12,
    tailored_resume_text: "tailored",
    resume_tailoring: { phase: "done", ask_user: [], selected_ids: [] },
  },
};

const a = offerDraftPersistFingerprint("job1", body);
const b = offerDraftPersistFingerprint("job1", {
  ...body,
  analysis: { ...body.analysis }, // new object identity, same content
});
assert.equal(a, b, "fingerprint ignores analysis object identity");

const gate = createOfferDraftPutGate();
assert.equal(gate.decide(a), "run");
let calls = 0;
const p1 = gate.begin(
  a,
  Promise.resolve(null).then(() => {
    calls += 1;
    gate.markSaved(a);
    return { job_id: "job1" };
  }),
);
assert.equal(gate.decide(a), "join");
const p2 = gate.getInflight();
await Promise.all([p1, p2]);
assert.equal(calls, 1, "inflight join must not double-run");
assert.equal(gate.decide(a), "skip", "identical payload after save is skipped");

const c = offerDraftPersistFingerprint("job1", {
  ...body,
  analysis: { ...body.analysis, company_name: "Revolut" },
});
assert.notEqual(a, c);
assert.equal(gate.decide(c), "run");

console.log("offerDraftPersistDedupe: ok");
