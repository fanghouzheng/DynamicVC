#!/usr/bin/env python3
import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any


PERT_PATTERNS = (
    re.compile(r"(?i)\b(?:cytokine|perturbation|pert|ligand)\s*[:：]\s*([^,，;；|]+)"),
)
GENE_PATTERNS = (
    re.compile(r"(?i)\bgene\s*[:：]\s*([^,，;；|]+)"),
)

JUDGE_LINE_PATTERNS = (
    re.compile(r"^(?:[-*•]\s*)?([ABC])\)\s*(.+\S.*)$", re.I),
    re.compile(
        r"^(?:[-*•]\s*)?(Yes|No|There is insufficient(?: evidence)?(?: to determine)?(?:[^\n.]*)?)\s*(?:[.!?].*)?$",
        re.I,
    ),
)
JUDGE_GLOBAL_PATTERNS = (
    re.compile(
        r"(?is)\b(?:final\s*(?:answer|judg(?:e)?ment)?|verdict|conclusion|answer)\s*[:：]\s*"
        r"((?:Yes|No|There is insufficient(?: evidence)?(?: to determine)?)(?:[^\n]*))"
    ),
    re.compile(
        r"(?is)\b([ABC])\)\s*"
        r"((?:Yes|No|There is insufficient(?: evidence)?(?: to determine)?)(?:[^\n]*))"
    ),
)

DIRECTION_PATTERN = re.compile(
    r"(?i)\b(increase|decrease|no\s*change|unchanged|upregulat(?:e|ed)|downregulat(?:e|ed))\b"
)
FINAL_SECTION_PATTERN = re.compile(
    r"(?is)\b(?:final\s+deterministic\s+prediction|final\s+prediction|final\s+answer|verdict|conclusion)\b"
)
JUDGE_HINT_PATTERN = re.compile(
    r"(?i)\b(perturbation|results?\s+in|prediction|final|verdict|conclusion|answer|judge(?:ment)?)\b"
)
PLAIN_DIRECTION_PATTERN = re.compile(
    r"(?i)^\s*(increase|decrease|no\s*change|unchanged|upregulat(?:e|ed)|downregulat(?:e|ed))\b"
)
PERT_RESULT_PATTERN = re.compile(
    r"(?i)\bperturbation\b.*\bresults?\s+in\b.*\b(increase|decrease|no\s*change|unchanged|upregulat(?:e|ed)|downregulat(?:e|ed))\b"
)
LETTER_JUDGE_PATTERN = re.compile(
    r"(?i)^[ABC]\)\s*(yes|no|there is insufficient|increase|decrease|no\s*change|unchanged)\b"
)
INSUFFICIENT_PATTERN = re.compile(r"(?i)\bthere is insufficient(?: evidence)?(?: to determine)?\b")
YES_PATTERN = re.compile(r"(?i)\byes\b")
NO_PATTERN = re.compile(r"(?i)\bno\b")
INCREASE_PATTERN = re.compile(r"(?i)\b(increase|upregulat(?:e|ed))\b")
DECREASE_PATTERN = re.compile(r"(?i)\b(decrease|downregulat(?:e|ed))\b")


def _clean_token(text: str) -> str:
    return (text or "").strip().strip("`'\"").strip()


def _clean_judge_line(line: str) -> str:
    s = (line or "").strip()
    s = re.sub(r"^[-*•]\s*", "", s)
    s = s.strip()
    s = s.strip("`")
    s = re.sub(r"\*{1,2}", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def parse_pert_gene(prompt_title: str) -> tuple[str, str]:
    title = (prompt_title or "").strip()
    pert = ""
    gene = ""

    for pat in PERT_PATTERNS:
        match = pat.search(title)
        if match:
            pert = _clean_token(match.group(1))
            break

    for pat in GENE_PATTERNS:
        match = pat.search(title)
        if match:
            gene = _clean_token(match.group(1))
            break

    if not pert or not gene:
        kv = {
            k.lower().strip(): _clean_token(v)
            for k, v in re.findall(r"([A-Za-z_]+)\s*[:：]\s*([^,，;；|]+)", title)
        }
        if not pert:
            for key in ("cytokine", "perturbation", "pert", "ligand"):
                if kv.get(key):
                    pert = kv[key]
                    break
        if not gene:
            gene = kv.get("gene", "")

    return pert, gene


def _extract_from_final_section(text: str) -> str:
    m = None
    for mm in FINAL_SECTION_PATTERN.finditer(text):
        m = mm
    if not m:
        return ""
    section = text[m.start() : m.start() + 1000]
    lines = [_clean_judge_line(line) for line in section.splitlines() if line.strip()]
    for i, line in enumerate(lines):
        if i == 0 and "final" in line.lower() and "prediction" in line.lower():
            continue
        if _is_judgment_candidate(line):
            return line
    return ""


def _is_judgment_candidate(line: str) -> bool:
    if not line:
        return False
    lower = line.lower()
    if len(line) > 260:
        return False
    if "example" in lower or "most examples" in lower:
        return False
    if "increase or decrease" in lower or "increase/decrease" in lower:
        return False
    if lower.startswith("my task is") or lower.startswith("i need to predict") or lower.startswith("the user wants me"):
        return False
    if "output the final direction" in lower:
        return False
    if "task asks" in lower:
        return False
    if PLAIN_DIRECTION_PATTERN.search(line):
        return True
    if LETTER_JUDGE_PATTERN.search(line):
        return True
    if PERT_RESULT_PATTERN.search(line):
        return True
    if DIRECTION_PATTERN.search(line) and JUDGE_HINT_PATTERN.search(line):
        return True
    return False


def extract_judge_text(response_text: str, existing_judge_text: str = "") -> str:
    if (existing_judge_text or "").strip():
        return _clean_judge_line(existing_judge_text)

    text = (response_text or "").strip()
    if not text:
        return ""

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in reversed(lines):
        for pattern in JUDGE_LINE_PATTERNS:
            match = pattern.match(line)
            if match:
                if len(match.groups()) == 2 and pattern is JUDGE_LINE_PATTERNS[0]:
                    letter, body = match.group(1).upper(), match.group(2).strip()
                    return _clean_judge_line(f"{letter}) {body}")
                return _clean_judge_line(match.group(1).strip())

    for pattern in JUDGE_GLOBAL_PATTERNS:
        matches = list(pattern.finditer(text))
        if not matches:
            continue
        m = matches[-1]
        if len(m.groups()) == 2 and pattern is JUDGE_GLOBAL_PATTERNS[1]:
            return _clean_judge_line(f"{m.group(1).upper()}) {m.group(2).strip()}")
        return _clean_judge_line(m.group(1).strip())

    from_final = _extract_from_final_section(text)
    if from_final:
        return from_final

    return ""


def iter_result_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        return [x for x in payload["results"] if isinstance(x, dict)]
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    return []


def infer_task_type(path: Path) -> str:
    parts_upper = [p.upper() for p in path.parts]
    if "DIR" in parts_upper:
        return "DIR"
    return "DE"


def map_label(task_type: str, judge_text: str) -> str:
    text = (judge_text or "").strip()
    if not text:
        return ""

    if INSUFFICIENT_PATTERN.search(text):
        return "2"

    if task_type == "DIR":
        if INCREASE_PATTERN.search(text):
            return "1"
        if DECREASE_PATTERN.search(text):
            return "0"
        if YES_PATTERN.search(text):
            return "1"
        if NO_PATTERN.search(text):
            return "0"
        return ""

    if YES_PATTERN.search(text):
        return "1"
    if NO_PATTERN.search(text):
        return "0"
    return ""


def process_one_json(path: Path) -> tuple[int, int, int, int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = iter_result_items(payload)
    task_type = infer_task_type(path)

    rows: list[dict[str, str]] = []
    missing_pert_gene = 0
    nonempty_judge = 0
    nonempty_label = 0

    for item in items:
        prompt_title = str(item.get("prompt_title", ""))
        response_text = str(item.get("response_text", ""))
        judge_text_raw = str(item.get("judge_text", ""))

        pert, gene = parse_pert_gene(prompt_title)
        judge_text = extract_judge_text(response_text, judge_text_raw)
        label = map_label(task_type, judge_text)

        if not pert or not gene:
            missing_pert_gene += 1
        if judge_text:
            nonempty_judge += 1
        if label:
            nonempty_label += 1

        rows.append({"pert": pert, "gene": gene, "label": label, "judge_text": judge_text})

    out_csv = path.with_suffix(".csv")
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["pert", "gene", "label", "judge_text"])
        writer.writeheader()
        writer.writerows(rows)

    return len(items), missing_pert_gene, nonempty_judge, nonempty_label


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract (pert, gene, judge_text) triples from JSON files and write one CSV per JSON."
    )
    parser.add_argument(
        "--dirs",
        nargs="+",
        default=["DE", "DIR"],
        help="Directories to scan recursively for JSON files.",
    )
    args = parser.parse_args()

    json_files: list[Path] = []
    for d in args.dirs:
        root = Path(d)
        if not root.exists():
            continue
        json_files.extend(sorted(root.rglob("*.json")))

    if not json_files:
        raise FileNotFoundError(f"No JSON files found in: {args.dirs}")

    total_items = 0
    total_missing = 0
    total_nonempty_judge = 0
    total_nonempty_label = 0

    for p in json_files:
        item_cnt, missing_cnt, judge_cnt, label_cnt = process_one_json(p)
        total_items += item_cnt
        total_missing += missing_cnt
        total_nonempty_judge += judge_cnt
        total_nonempty_label += label_cnt
        print(
            f"[OK] {p} -> {p.with_suffix('.csv')} "
            f"(rows={item_cnt}, judge_nonempty={judge_cnt}, label_nonempty={label_cnt})"
        )

    print("\nSummary")
    print(f"JSON files processed: {len(json_files)}")
    print(f"Total rows: {total_items}")
    print(f"Rows with non-empty judge_text: {total_nonempty_judge}")
    print(f"Rows with non-empty label: {total_nonempty_label}")
    print(f"Rows missing pert/gene: {total_missing}")


if __name__ == "__main__":
    main()
