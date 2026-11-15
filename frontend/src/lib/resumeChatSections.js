/** Resume editor sections — aligned with workshops cv.yml schema. */

const BASIC_FIELDS = [
  { key: "name", label: "Full name", placeholder: "Alexey Grigorev", multiline: false, optional: false },
  {
    key: "headline",
    label: "Headline (target role — value phrase)",
    placeholder: "Applied AI Engineer — End-to-End LLM Systems",
    multiline: false,
    optional: false,
  },
  {
    key: "location",
    label: "Location",
    placeholder: "Berlin, Germany",
    multiline: false,
    optional: true,
  },
  { key: "email", label: "E-mail", placeholder: "name@example.com", multiline: false, optional: false },
  { key: "phone", label: "Phone", placeholder: "+49 170 0000000", multiline: false, optional: true },
  {
    key: "links",
    label: "Links",
    placeholder: "LinkedIn | https://linkedin.com/in/...\nGitHub | https://github.com/...",
    multiline: true,
    optional: true,
  },
  {
    key: "summary",
    label: "Summary",
    placeholder: "3–4 lines: end-to-end scope, impact, credibility anchors…",
    multiline: true,
    optional: true,
  },
  {
    key: "note",
    label: "Note under contact",
    placeholder: "Open to relocation · No sponsorship needed",
    multiline: true,
    optional: true,
  },
];

const EXP_FIELD_TEMPLATES = [
  { suffix: "company", label: "Company", placeholder: "DataTalks.Club", multiline: false, optional: false },
  { suffix: "title", label: "Job title", placeholder: "Founder & Product Engineer", multiline: false, optional: false },
  { suffix: "location", label: "Location", placeholder: "Berlin, Germany", multiline: false, optional: true },
  { suffix: "period", label: "Period", placeholder: "Sep 2020 – Present", multiline: false, optional: false },
  {
    suffix: "context",
    label: "Project context",
    placeholder:
      "Platform Modernization and Lakehouse Implementation for scalable analytics and initial integration of Generative AI capabilities.",
    multiline: true,
    optional: true,
  },
  {
    suffix: "bullets",
    label: "Bullets (one per line)",
    placeholder: "Own AI product work end-to-end for a 100k+ learner community.\nShip production LLM/RAG systems with evaluation pipelines.",
    multiline: true,
    optional: false,
  },
];

const SKILL_FIELD_TEMPLATES = [
  { suffix: "group", label: "Skill group", placeholder: "Applied AI / LLM", multiline: false, optional: false },
  {
    suffix: "items",
    label: "Items (comma-separated)",
    placeholder: "RAG, agentic workflows, evaluations",
    multiline: true,
    optional: false,
  },
];

const EARLIER_FIELD_TEMPLATES = [
  { suffix: "period", label: "Period", placeholder: "2017 – 2018", multiline: false, optional: false },
  { suffix: "company", label: "Company", placeholder: "Simplaex", multiline: false, optional: false },
  { suffix: "role", label: "Role", placeholder: "Data Scientist / Engineer", multiline: false, optional: false },
  { suffix: "location", label: "Location", placeholder: "Berlin", multiline: true, optional: true },
  {
    suffix: "stack",
    label: "Stack (comma-separated)",
    placeholder: "Python, Scala, Spark, AWS",
    multiline: false,
    optional: true,
  },
];

const PROJ_FIELD_TEMPLATES = [
  { suffix: "name", label: "Project name", placeholder: "Slack FAQ Assistant", multiline: false, optional: false },
  {
    suffix: "bullets",
    label: "Bullets",
    placeholder: "Slack RAG assistant deployed as a serverless application.",
    multiline: true,
    optional: false,
  },
];

const EDU_FIELD_TEMPLATES = [
  { suffix: "degree", label: "Degree", placeholder: "MSc — IT4BI", multiline: false, optional: false },
  { suffix: "school", label: "School", placeholder: "TU Berlin", multiline: false, optional: false },
  { suffix: "period", label: "Period", placeholder: "2013 – 2015", multiline: false, optional: true },
  { suffix: "note", label: "Note", placeholder: "Specialization: Large-Scale BI", multiline: true, optional: true },
];

const EXTRA_FIELDS = [
  {
    key: "certifications",
    label: "Certifications",
    placeholder: "AWS Solutions Architect, 2024",
    multiline: true,
    optional: true,
  },
  {
    key: "languages",
    label: "Languages",
    placeholder: "English — fluent\nGerman — B2",
    multiline: true,
    optional: true,
  },
  {
    key: "recognition_books",
    label: "Publications (title | publisher | year | url)",
    placeholder: "ML Bookcamp | Manning | 2021 | https://…",
    multiline: true,
    optional: true,
  },
  {
    key: "recognition_highlights",
    label: "Recognition highlights",
    placeholder: "Kaggle Master — multiple top-10 finishes…",
    multiline: true,
    optional: true,
  },
  {
    key: "interests",
    label: "Interests",
    placeholder: "VR, board games, hiking",
    multiline: true,
    optional: true,
  },
];

const PREFIX_SPECS = [
  { prefix: "exp_", suffixes: ["company", "title", "location", "period", "context", "bullets"] },
  { prefix: "skill_", suffixes: ["group", "items"] },
  { prefix: "earlier_", suffixes: ["period", "company", "role", "location", "stack"] },
  { prefix: "proj_", suffixes: ["name", "bullets"] },
  { prefix: "edu_", suffixes: ["degree", "school", "period", "note"] },
  { prefix: "job_", suffixes: ["company", "roleAndDates", "description", "result", "technologies"] },
];

function indicesFromAnswers(answers, prefix) {
  if (!answers || typeof answers !== "object") return [];
  const re = new RegExp(`^${prefix}(\\d+)_`);
  const indices = new Set();
  for (const key of Object.keys(answers)) {
    const match = key.match(re);
    if (match) indices.add(Number(match[1]));
  }
  return [...indices].sort((a, b) => a - b);
}

function blockHasContent(answers, prefix, index, suffixes) {
  const p = `${prefix}${index}_`;
  return suffixes.some((suffix) => String(answers?.[`${p}${suffix}`] || "").trim().length > 0);
}

function compactIndexedAnswers(answers, prefix, suffixes) {
  const base = { ...answers };
  const oldIndices = indicesFromAnswers(base, prefix).filter((idx) =>
    blockHasContent(base, prefix, idx, suffixes),
  );
  for (const key of Object.keys(base)) {
    if (key.startsWith(prefix)) delete base[key];
  }
  oldIndices.forEach((oldIdx, newIdx) => {
    for (const suffix of suffixes) {
      const val = answers[`${prefix}${oldIdx}_${suffix}`];
      if (val != null && String(val).trim()) base[`${prefix}${newIdx}_${suffix}`] = val;
    }
  });
  return base;
}

export function compactJobAnswers(answers) {
  if (!answers || typeof answers !== "object") return {};
  let out = { ...answers };
  for (const spec of PREFIX_SPECS) {
    out = compactIndexedAnswers(out, spec.prefix, spec.suffixes);
  }
  return out;
}

export function jobIndicesFromAnswers(answers) {
  const exp = indicesFromAnswers(answers, "exp_").filter((idx) =>
    blockHasContent(answers, "exp_", idx, ["company", "title", "bullets"]),
  );
  if (exp.length) return exp;
  return indicesFromAnswers(answers, "job_").filter((idx) =>
    blockHasContent(answers, "job_", idx, ["company", "roleAndDates", "description"]),
  );
}

export function skillIndicesFromAnswers(answers) {
  return indicesFromAnswers(answers, "skill_").filter((idx) =>
    blockHasContent(answers, "skill_", idx, ["group", "items"]),
  );
}

export function earlierIndicesFromAnswers(answers) {
  return indicesFromAnswers(answers, "earlier_").filter((idx) =>
    blockHasContent(answers, "earlier_", idx, ["period", "company", "role"]),
  );
}

export function projectIndicesFromAnswers(answers) {
  return indicesFromAnswers(answers, "proj_").filter((idx) =>
    blockHasContent(answers, "proj_", idx, ["name", "bullets"]),
  );
}

export function educationIndicesFromAnswers(answers) {
  return indicesFromAnswers(answers, "edu_").filter((idx) =>
    blockHasContent(answers, "edu_", idx, ["degree", "school"]),
  );
}

function prefixSpec(prefix) {
  return PREFIX_SPECS.find((spec) => spec.prefix === prefix) || null;
}

const SECTION_LABELS = {
  exp_: "Experience",
  job_: "Experience",
  earlier_: "Earlier experience",
  skill_: "Skills",
  proj_: "Projects",
  edu_: "Education",
};

/** Short summary of the block being deleted (company, role, project name, …). */
export function blockLabelFromAnswers(answers, prefix, index) {
  const p = `${prefix}${index}_`;
  const pick = (...keys) => {
    for (const key of keys) {
      const val = String(answers?.[`${p}${key}`] || "").trim();
      if (val) return val;
    }
    return "";
  };
  if (prefix === "exp_" || prefix === "job_") {
    const company = pick("company");
    const title = pick("title");
    if (company && title) return `${company} — ${title}`;
    return company || title || `Job ${index + 1}`;
  }
  if (prefix === "earlier_") {
    const company = pick("company");
    const role = pick("role");
    if (company && role) return `${company} — ${role}`;
    return company || role || `Earlier role ${index + 1}`;
  }
  if (prefix === "skill_") return pick("group") || `Skill group ${index + 1}`;
  if (prefix === "proj_") return pick("name") || `Project ${index + 1}`;
  if (prefix === "edu_") {
    const school = pick("school");
    const degree = pick("degree");
    if (school && degree) return `${degree} — ${school}`;
    return school || degree || `Education ${index + 1}`;
  }
  return `Item ${index + 1}`;
}

/** Clear multi-line confirm text for the Delete button. */
export function deleteConfirmMessage(field, answers) {
  const prefix = field.blockPrefix || "exp_";
  const section = SECTION_LABELS[prefix] || "Resume section";
  const summary = blockLabelFromAnswers(answers, prefix, field.jobIndex);
  return [
    `Delete this entry from ${section}?`,
    "",
    summary,
    "",
    "It will be removed from your PDF when you save.",
  ].join("\n");
}

/** Remove one indexed block (experience, earlier, skills, projects, education) and renumber. */
export function removeIndexedBlockFromAnswers(answers, prefix, index) {
  if (!answers || typeof answers !== "object") return {};
  const spec = prefixSpec(prefix);
  if (!spec) return { ...answers };

  const base = { ...answers };
  const blockPrefix = `${prefix}${index}_`;
  for (const key of Object.keys(base)) {
    if (key.startsWith(blockPrefix)) delete base[key];
  }
  if (prefix === "exp_") {
    for (const key of Object.keys(base)) {
      if (key.startsWith(`job_${index}_`)) delete base[key];
    }
    let out = compactIndexedAnswers(base, "exp_", spec.suffixes);
    out = compactIndexedAnswers(out, "job_", prefixSpec("job_").suffixes);
    return out;
  }
  return compactIndexedAnswers(base, prefix, spec.suffixes);
}

export function removeJobFromAnswers(answers, jobIndex) {
  return removeIndexedBlockFromAnswers(answers, "exp_", jobIndex);
}

/** Optional sections: show indexed blocks only when keys exist (no empty placeholder after delete). */
function optionalIndexedFields(answers, prefix, templates, sectionLabel) {
  const indices = indicesFromAnswers(answers, prefix);
  return indices.length ? indexedFields(prefix, indices, templates, answers, sectionLabel) : [];
}

/** Append an empty indexed block (for "Add project" etc.). */
export function appendIndexedBlock(answers, prefix) {
  const spec = prefixSpec(prefix);
  if (!spec) return { ...(answers || {}) };
  const indices = indicesFromAnswers(answers || {}, prefix);
  const nextIndex = indices.length ? Math.max(...indices) + 1 : 0;
  const out = { ...(answers || {}) };
  for (const suffix of spec.suffixes) {
    const key = `${prefix}${nextIndex}_${suffix}`;
    if (out[key] == null) out[key] = "";
  }
  return out;
}

function indexedFields(prefix, indices, templates, answers, sectionLabel) {
  const fields = [];
  for (const index of indices) {
    fields.push({
      key: `__${prefix}${index}_heading`,
      type: "job_heading",
      label: indices.length > 1 ? `${sectionLabel} ${index + 1}` : sectionLabel,
      jobIndex: index,
      blockPrefix: prefix,
    });
    for (const tpl of templates) {
      fields.push({
        key: `${prefix}${index}_${tpl.suffix}`,
        label: tpl.suffix === templates[0].suffix ? `${sectionLabel} ${index + 1} — ${tpl.label}` : tpl.label,
        placeholder: tpl.placeholder,
        multiline: tpl.multiline,
        optional: tpl.optional,
      });
    }
  }
  return fields;
}

/** @param {Record<string, string>} answers */
export function buildResumeSections(answers = {}) {
  const expIndices = jobIndicesFromAnswers(answers);
  const expList = expIndices.length ? expIndices : [0];

  return [
    {
      id: "basics",
      title: "Header & summary",
      subtitle: "basics — name, headline, contact, summary",
      fields: BASIC_FIELDS,
    },
    {
      id: "skills",
      title: "Skills",
      subtitle: "Grouped skills (group + items)",
      fields: optionalIndexedFields(answers, "skill_", SKILL_FIELD_TEMPLATES, "Skill group"),
      allOptional: true,
      blockPrefix: "skill_",
      addBlockLabel: "Add skill group",
    },
    {
      id: "experience",
      title: "Experience",
      subtitle: "company, title, location, period, bullets",
      fields: indexedFields("exp_", expList, EXP_FIELD_TEMPLATES, answers, "Job"),
    },
    {
      id: "earlier",
      title: "Earlier experience",
      subtitle: "Compact one-liners — optional",
      fields: optionalIndexedFields(answers, "earlier_", EARLIER_FIELD_TEMPLATES, "Earlier role"),
      allOptional: true,
      blockPrefix: "earlier_",
      addBlockLabel: "Add earlier role",
    },
    {
      id: "projects",
      title: "Projects",
      subtitle: "Selected projects — optional",
      fields: optionalIndexedFields(answers, "proj_", PROJ_FIELD_TEMPLATES, "Project"),
      allOptional: true,
      blockPrefix: "proj_",
      addBlockLabel: "Add project",
    },
    {
      id: "education",
      title: "Education",
      subtitle: "degree, school, period, note",
      fields: optionalIndexedFields(answers, "edu_", EDU_FIELD_TEMPLATES, "Education"),
      allOptional: true,
      blockPrefix: "edu_",
      addBlockLabel: "Add education",
    },
    {
      id: "extra",
      title: "Certifications, languages, recognition, interests",
      subtitle: "Optional sections from cv.yml (interests render last in PDF)",
      fields: EXTRA_FIELDS,
      allOptional: true,
    },
  ];
}

/** @param {{ fields: Array<{ key: string, optional?: boolean, type?: string }> }} section @param {Record<string, string>} values */
export function validateSection(section, values) {
  if (section.allOptional) return [];
  const missing = [];
  for (const field of section.fields || []) {
    if (field.type === "heading" || field.type === "job_heading" || field.key.startsWith("__")) continue;
    if (field.optional) continue;
    if (!String(values[field.key] || "").trim()) {
      missing.push(field.label || field.key);
    }
  }
  if (section.id === "basics") {
    if (!String(values.name || "").trim()) missing.unshift("Full name");
    if (!String(values.headline || "").trim()) missing.unshift("Headline");
    if (!String(values.email || "").trim()) missing.unshift("E-mail");
  }
  return [...new Set(missing)];
}
