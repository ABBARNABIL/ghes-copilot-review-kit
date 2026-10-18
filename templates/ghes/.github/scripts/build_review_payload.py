#!/usr/bin/env python3
"""Validate model findings and map RIGHT-side lines to GHES diff positions."""

import argparse
import codecs
import json
import re
from pathlib import Path, PurePosixPath

SEVERITIES = {"critical", "high", "medium", "low"}
MAX_FINDINGS = 8
MAX_DIFF_BYTES = 1_000_000
MAX_REVIEW_BYTES = 100_000


def decode_diff_path(value: str) -> str | None:
    if value == "/dev/null":
        return None
    if value.startswith('"'):
        if not value.endswith('"'):
            raise ValueError("Unterminated quoted diff path")
        # Git quotes UTF-8 bytes using C-style octal escapes.
        value = codecs.escape_decode(value[1:-1].encode("utf-8"))[0].decode("utf-8")
    if value.startswith("b/"):
        value = value[2:]
    return value


def parse_diff_positions(diff_text: str) -> dict[tuple[str, int], int]:
    positions: dict[tuple[str, int], int] = {}
    current_path: str | None = None
    in_hunk = False
    position = 0
    new_line = 0

    for raw_line in diff_text.split("\n"):
        if raw_line.startswith("diff --git "):
            current_path = None
            in_hunk = False
            position = 0
            continue

        if not in_hunk and raw_line.startswith("+++ "):
            current_path = decode_diff_path(raw_line[4:].removesuffix("\r"))
            continue

        if raw_line.startswith("@@"):
            match = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", raw_line)
            if not match:
                raise ValueError(f"Unsupported diff hunk header: {raw_line}")
            if in_hunk:
                position += 1
            else:
                in_hunk = True
                position = 0
            new_line = int(match.group(1))
            continue

        if not in_hunk or current_path is None or not raw_line:
            continue

        position += 1
        if raw_line.startswith("\\ No newline at end of file"):
            continue

        if raw_line[0] in {" ", "+"}:
            positions.setdefault((current_path, new_line), position)
            new_line += 1
        elif raw_line[0] != "-":
            raise ValueError("Unsupported line inside a unified diff hunk")

    return positions


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    value: dict = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"Duplicate JSON field: {key}")
        value[key] = item
    return value


def reject_constant(value: str) -> None:
    raise ValueError(f"Non-finite JSON constant: {value}")


def extract_json(text: str) -> dict:
    try:
        # Literal controls from model output are accepted, then sanitized below.
        value = json.loads(
            text.strip(), strict=False,
            object_pairs_hook=unique_object, parse_constant=reject_constant,
        )
    except json.JSONDecodeError as error:
        raise ValueError("Copilot did not return valid JSON") from error

    if not isinstance(value, dict):
        raise ValueError("Copilot review must be a JSON object")
    if set(value) != {"summary", "findings"}:
        raise ValueError("Copilot review must contain only summary and findings")
    if not isinstance(value["summary"], str) or not value["summary"].strip():
        raise ValueError("summary must be a non-empty string")
    if not isinstance(value["findings"], list):
        raise ValueError("findings must be an array")
    return value


def clean_text(value: object, limit: int, *, single_line: bool = False) -> str:
    if not isinstance(value, str):
        return ""
    text = value.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    if single_line:
        text = " ".join(text.split())
    text = text.strip()[:limit].strip()
    return text.replace("@", "@\u200b")


def normalize_path(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.replace("\\", "/")
    path = PurePosixPath(value)
    if (
        not value or path.is_absolute() or ".." in path.parts
        or re.match(r"^[A-Za-z]:", value)
        or re.search(r"[\x00-\x1f\x7f]", value)
    ):
        return None
    return str(path)


def build_payload(
    review: dict,
    positions: dict[tuple[str, int], int],
    head_sha: str,
) -> tuple[dict, int]:
    if not re.fullmatch(r"[0-9a-f]{40}", head_sha):
        raise ValueError("head SHA must be an exact 40-character commit ID")
    summary = clean_text(review.get("summary"), 4000, single_line=True)
    if not summary:
        raise ValueError("summary is empty after text normalization")

    findings = review["findings"]
    comments = []
    dropped = max(0, len(findings) - MAX_FINDINGS)
    seen_locations: set[tuple[str, int]] = set()

    for finding in findings[:MAX_FINDINGS]:
        if not isinstance(finding, dict) or set(finding) != {
            "severity", "path", "line", "title", "body"
        }:
            dropped += 1
            continue

        severity = finding["severity"]
        severity = severity.lower() if isinstance(severity, str) else ""
        path = normalize_path(finding["path"])
        line = finding["line"]
        title = clean_text(finding["title"], 160, single_line=True)
        body = clean_text(finding["body"], 2500)

        if (
            severity not in SEVERITIES
            or type(line) is not int or line < 1
            or path is None or not title or not body
        ):
            dropped += 1
            continue
        position = positions.get((path, line))
        if position is None or (path, line) in seen_locations:
            dropped += 1
            continue
        seen_locations.add((path, line))
        comments.append({
            "path": path,
            "position": position,
            "body": (
                f"**{severity.upper()} - {title}**\n\n{body}\n\n"
                "_Generated by the Copilot Review GitHub App._"
            ),
        })

    if comments:
        status = f"Posted {len(comments)} validated inline finding"
        status += "." if len(comments) == 1 else "s."
    elif dropped:
        status = "No validated inline findings were posted."
    else:
        status = "No high-confidence inline findings were found."
    if dropped:
        status += f" Discarded {dropped} invalid, duplicate, off-diff, or excess findings."

    return ({
        "commit_id": head_sha,
        "event": "COMMENT",
        "body": (
            f"## Copilot Review\n\n{summary}\n\n{status}\n\n"
            "_Generated by the `Copilot Review` GitHub App. "
            "Verify all findings before merging._"
        ),
        "comments": comments,
    }, dropped)


def read_limited(path: Path, limit: int) -> str:
    with path.open("rb") as source:
        data = source.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"{path.name} exceeds the {limit}-byte input limit")
    return data.decode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diff", required=True)
    parser.add_argument("--review", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        diff = read_limited(Path(args.diff), MAX_DIFF_BYTES)
        review = extract_json(read_limited(Path(args.review), MAX_REVIEW_BYTES))
        payload, dropped = build_payload(
            review, parse_diff_positions(diff), args.head_sha
        )
        Path(args.output).write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
    except (ValueError, OSError, UnicodeError) as error:
        parser.exit(1, f"Review validation failed: {error}\n")
    print(
        f"Validated {len(payload['comments'])} inline findings; "
        f"dropped {dropped} invalid or excess findings."
    )


if __name__ == "__main__":
    main()
