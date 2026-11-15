from pathlib import Path
import argparse
import os
import re

import yaml
from liteparse import LiteParse
from cursor_sdk import Agent, AgentOptions, LocalAgentOptions
from dotenv import load_dotenv

load_dotenv()

SCHEMA = """
basics:
  name: ""
  headline: ""
  location: ""
  email: ""
  phone: ""
  links:
    - label: ""
      text: ""
      url: ""
  summary: ""

skills:
  - group: ""
    items: []

experience:
  - company: ""
    title: ""
    location: ""
    period: ""
    bullets: []

experience_earlier:
  - period: ""
    company: ""
    role: ""
    location: ""
    stack: []

projects:
  - name: ""
    bullets: []

education:
  - degree: ""
    school: ""
    period: ""
    note: ""

certifications: []

languages:
  - name: ""
    level: ""

recognition:
  books: []
  highlights: []
"""


MONTHS = {
    "January": "Jan",
    "February": "Feb",
    "March": "Mar",
    "April": "Apr",
    "May": "May",
    "June": "Jun",
    "July": "Jul",
    "August": "Aug",
    "September": "Sep",
    "October": "Oct",
    "November": "Nov",
    "December": "Dec",
}


def clean_yaml_output(text: str) -> str:
    text = text.strip()

    text = re.sub(
        r"^\s*```(?:yaml|yml)?\s*\n?",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\n?\s*```\s*$",
        "",
        text,
    )

    return text.strip()


def write_cv_yml(cv: dict, output: Path | str) -> Path:
    """Write normalized cv.yml (same format as CLI -o output)."""
    dst = Path(output).expanduser().resolve()
    data = normalize_dates(dict(cv))
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )
    return dst


def normalize_dates(cv: dict) -> dict:
    for job in cv.get("experience", []):
        period = str(job.get("period", ""))

        for full, short in MONTHS.items():
            period = re.sub(
                rf"\b{full}\b",
                short,
                period,
                flags=re.IGNORECASE,
            )

        period = re.sub(
            r"\s*[-–—]\s*",
            " – ",
            period,
        )

        job["period"] = period

    for job in cv.get("experience_earlier", []):
        period = str(job.get("period", ""))

        years = re.findall(
            r"\b(?:19|20)\d{2}\b",
            period,
        )

        if len(years) >= 2:
            job["period"] = f"{years[0]} – {years[-1]}"

        elif len(years) == 1:
            if re.search(
                r"\b(?:Present|Current|Now)\b",
                period,
                re.IGNORECASE,
            ):
                job["period"] = f"{years[0]} – Present"
            else:
                job["period"] = years[0]

    return cv


def main():
    ap = argparse.ArgumentParser(
        description="Convert resume PDF to normalized cv.yml."
    )

    ap.add_argument(
        "pdf",
        help="Input resume PDF",
    )

    ap.add_argument(
        "-o",
        "--output",
        required=True,
        help="Output cv.yml",
    )

    args = ap.parse_args()

    src = Path(args.pdf).expanduser().resolve()
    dst = Path(args.output).expanduser().resolve()

    if not src.exists():
        raise SystemExit(
            f"PDF not found: {src}"
        )

    # PDF -> Markdown
    parser = LiteParse(
        output_format="markdown",
        image_mode="off",
        extract_links=True,
        ocr_enabled=True,
    )

    md = parser.parse(
        str(src)
    ).text

    # Markdown -> strict YAML
    prompt = f"""
Convert the resume below into EXACTLY the YAML schema provided.

Return RAW YAML only.

Rules:
- Do not use Markdown code fences.
- Do not add explanations before or after the YAML.
- Do not invent facts, skills, technologies, companies, dates, or achievements.
- Preserve factual information from the resume.
- Normalize obvious PDF extraction artifacts and missing spaces.
- Keep the 3 most recent roles in `experience`.
- Put older roles into `experience_earlier`.
- Always extract basics.location, basics.email, and basics.phone from the resume header/contact block when present.
- Missing values must be "" or [].
- Group skills into useful categories when supported by the source.
- Preserve links, certifications, education, and languages.
- Keep experience bullets concise while preserving their meaning.
- Output must be valid YAML parseable by PyYAML.

YAML SCHEMA:

{SCHEMA}

RESUME:

{md}
"""

    response = Agent.prompt(
        prompt,
        AgentOptions(
            model="composer-2.5",
            api_key=os.environ["CURSOR_API_KEY"],
            local=LocalAgentOptions(
                cwd=str(src.parent)
            ),
            tools=[],
        ),
    )

    yml = clean_yaml_output(
        response.result
    )

    try:
        data = yaml.safe_load(
            yml
        )

    except yaml.YAMLError as exc:
        print("\n--- CURSOR OUTPUT ---")
        print(yml)
        print("--- END CURSOR OUTPUT ---\n")

        raise SystemExit(
            f"Cursor returned invalid YAML:\n{exc}"
        )

    if not isinstance(data, dict):
        raise SystemExit(
            "Cursor response is valid YAML, but root is not a mapping."
        )

    # Deterministic formatting, not LLM
    data = normalize_dates(
        data
    )

    dst.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    dst.write_text(
        yaml.safe_dump(
            data,
            sort_keys=False,
            allow_unicode=True,
            width=100,
        ),
        encoding="utf-8",
    )

    print(
        f"Wrote {dst}"
    )

    usage = getattr(
        response,
        "usage",
        None,
    )

    if usage:
        input_tokens = getattr(
            usage,
            "input_tokens",
            None,
        )
        output_tokens = getattr(
            usage,
            "output_tokens",
            None,
        )
        total_tokens = getattr(
            usage,
            "total_tokens",
            None,
        )

        if input_tokens is not None:
            print(f"Input tokens:  {input_tokens}")

        if output_tokens is not None:
            print(f"Output tokens: {output_tokens}")

        if total_tokens is not None:
            print(f"Total tokens:  {total_tokens}")


if __name__ == "__main__":
    main()