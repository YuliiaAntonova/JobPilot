/** Word/line diff to highlight LLM edits (green = new or changed). */

function normalizeText(text) {
  return String(text || "")
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n")
    .replace(/[ \t]+$/gm, "");
}

function tokenizeWords(text) {
  return String(text || "").split(/(\s+)/).filter((t) => t.length > 0);
}

function lcsDiffWords(oldItems, newItems, equals = (a, b) => a === b) {
  const n = oldItems.length;
  const m = newItems.length;
  const dp = Array.from({ length: n + 1 }, () => Array(m + 1).fill(0));

  for (let i = 1; i <= n; i += 1) {
    for (let j = 1; j <= m; j += 1) {
      if (equals(oldItems[i - 1], newItems[j - 1])) {
        dp[i][j] = dp[i - 1][j - 1] + 1;
      } else {
        dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1]);
      }
    }
  }

  const out = [];
  let i = n;
  let j = m;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && equals(oldItems[i - 1], newItems[j - 1])) {
      out.unshift({ text: newItems[j - 1], added: false });
      i -= 1;
      j -= 1;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      out.unshift({ text: newItems[j - 1], added: true });
      j -= 1;
    } else {
      i -= 1;
    }
  }
  return out;
}

function diffLineWords(oldLine, newLine) {
  if (oldLine === newLine) {
    return [{ text: newLine, added: false }];
  }
  return lcsDiffWords(tokenizeWords(oldLine), tokenizeWords(newLine));
}

/** @returns {{ type: 'equal'|'insert'|'replace', text: string, oldText?: string }[]} */
function diffLineOps(oldLines, newLines) {
  const n = oldLines.length;
  const m = newLines.length;
  const dp = Array.from({ length: n + 1 }, () => Array(m + 1).fill(0));

  for (let i = 1; i <= n; i += 1) {
    for (let j = 1; j <= m; j += 1) {
      if (oldLines[i - 1] === newLines[j - 1]) {
        dp[i][j] = dp[i - 1][j - 1] + 1;
      } else {
        dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1]);
      }
    }
  }

  const ops = [];
  let i = n;
  let j = m;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && oldLines[i - 1] === newLines[j - 1]) {
      ops.unshift({ type: "equal", text: newLines[j - 1] });
      i -= 1;
      j -= 1;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      if (i > 0 && dp[i][j - 1] === dp[i - 1][j]) {
        ops.unshift({ type: "replace", oldText: oldLines[i - 1], text: newLines[j - 1] });
        i -= 1;
      } else {
        ops.unshift({ type: "insert", text: newLines[j - 1] });
      }
      j -= 1;
    } else {
      i -= 1;
    }
  }
  return ops;
}

function mergeAdjacentSegments(segments) {
  const merged = [];
  for (const seg of segments) {
    const prev = merged[merged.length - 1];
    if (prev && prev.added === seg.added) {
      prev.text += seg.text;
    } else {
      merged.push({ ...seg });
    }
  }
  return merged;
}

/** @returns {{ text: string, added: boolean }[]} */
export function buildTextDiff(before, after) {
  const b = normalizeText(before);
  const a = normalizeText(after);
  if (b === a) {
    return [{ text: a, added: false }];
  }

  const ops = diffLineOps(b.split("\n"), a.split("\n"));
  const segments = [];

  ops.forEach((op, idx) => {
    if (op.type === "equal") {
      segments.push({ text: op.text, added: false });
    } else if (op.type === "insert") {
      segments.push({ text: op.text, added: true });
    } else {
      segments.push(...diffLineWords(op.oldText || "", op.text));
    }
    if (idx < ops.length - 1) {
      segments.push({ text: "\n", added: false });
    }
  });

  return mergeAdjacentSegments(segments.length ? segments : [{ text: a, added: true }]);
}
