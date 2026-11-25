/** Verbose LLM token logs in the browser console (DevTools). */

function n(v) {
  const x = Number(v);
  return Number.isFinite(x) ? x : 0;
}

/**
 * @param {string} label — human-readable operation name
 * @param {object|null|undefined} tokenUsage — { operation, model, calls[], total{} }
 */
export function logLlmTokenUsage(label, tokenUsage) {
  if (!tokenUsage || typeof tokenUsage !== "object") {
    console.warn(`[LLM tokens] ${label}: usage not returned from server`);
    return;
  }

  const total = tokenUsage.total || {};
  const prompt = n(total.prompt_tokens);
  const completion = n(total.completion_tokens);
  const sum = n(total.total_tokens) || prompt + completion;
  const model = tokenUsage.model || "—";
  const operation = tokenUsage.operation || label;

  console.group(`[LLM tokens] ${label}`);
  console.log(`Operation: ${operation}`);
  console.log(`Model: ${model}`);
  console.log(`Total: ${sum} tokens (prompt ${prompt} + completion ${completion})`);

  const calls = Array.isArray(tokenUsage.calls) ? tokenUsage.calls : [];
  if (calls.length) {
    console.table(
      calls.map((c) => ({
        step: c.step || "call",
        prompt: n(c.prompt_tokens),
        completion: n(c.completion_tokens),
        total: n(c.total_tokens) || n(c.prompt_tokens) + n(c.completion_tokens),
      })),
    );
  }

  console.groupEnd();
}