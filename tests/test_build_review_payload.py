import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "templates"
    / "ghes"
    / ".github"
    / "scripts"
    / "build_review_payload.py"
)
SPEC = importlib.util.spec_from_file_location("build_review_payload", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

DIFF = """\
diff --git a/src/example.py b/src/example.py
index 1111111..2222222 100644
--- a/src/example.py
+++ b/src/example.py
@@ -1,3 +1,4 @@
 one
-old
+new
+return 1 / 0
 tail
"""


class BuildReviewPayloadTests(unittest.TestCase):
    def setUp(self):
        self.positions = MODULE.parse_diff_positions(DIFF)
        self.finding = {
            "severity": "high",
            "path": "src/example.py",
            "line": 3,
            "title": "Division by zero",
            "body": "This expression always raises ZeroDivisionError.",
        }

    def payload(self, findings, summary="Review complete."):
        return MODULE.build_payload(
            {"summary": summary, "findings": findings},
            self.positions,
            "a" * 40,
        )

    def test_maps_new_file_line_to_diff_position(self):
        self.assertEqual(self.positions[("src/example.py", 3)], 4)

    def test_builds_inline_comment_for_valid_finding(self):
        payload, dropped = self.payload([self.finding])
        self.assertEqual(dropped, 0)
        self.assertEqual(payload["event"], "COMMENT")
        self.assertEqual(payload["commit_id"], "a" * 40)
        self.assertEqual(
            set(payload), {"event", "commit_id", "body", "comments"}
        )
        self.assertEqual(
            set(payload["comments"][0]), {"path", "position", "body"}
        )
        self.assertEqual(payload["comments"][0]["position"], 4)
        self.assertEqual(payload["comments"][0]["path"], "src/example.py")

    def test_accepts_visible_right_side_context(self):
        payload, dropped = self.payload([{**self.finding, "line": 4}])
        self.assertEqual(dropped, 0)
        self.assertEqual(payload["comments"][0]["position"], 5)

    def test_drops_finding_that_is_not_on_the_diff(self):
        payload, dropped = self.payload([{**self.finding, "line": 99}])
        self.assertEqual(dropped, 1)
        self.assertEqual(payload["comments"], [])
        self.assertIn("Discarded 1", payload["body"])
        self.assertNotIn("No high-confidence inline findings", payload["body"])

    def test_counts_positions_across_multiple_hunks(self):
        diff = """\
diff --git a/src/example.py b/src/example.py
--- a/src/example.py
+++ b/src/example.py
@@ -1,2 +1,2 @@
-old
+new
 keep
@@ -10,2 +10,3 @@
 context
+bug
 tail
"""
        positions = MODULE.parse_diff_positions(diff)
        self.assertEqual(positions[("src/example.py", 11)], 6)

    def test_resets_positions_for_each_file(self):
        diff = DIFF + DIFF.replace("src/example.py", "src/second.py")
        positions = MODULE.parse_diff_positions(diff)
        self.assertEqual(positions[("src/second.py", 3)], 4)

    def test_maps_new_files_and_renames_but_not_deleted_or_binary_files(self):
        diff = """\
diff --git a/new.py b/new.py
new file mode 100644
--- /dev/null
+++ b/new.py
@@ -0,0 +1 @@
+new
diff --git a/old.py b/old.py
deleted file mode 100644
--- a/old.py
+++ /dev/null
@@ -1 +0,0 @@
-old
diff --git a/before.py b/after.py
similarity index 60%
rename from before.py
rename to after.py
--- a/before.py
+++ b/after.py
@@ -1 +1 @@
-old
+new
diff --git a/picture.bin b/picture.bin
Binary files a/picture.bin and b/picture.bin differ
"""
        positions = MODULE.parse_diff_positions(diff)
        self.assertEqual(positions[("new.py", 1)], 1)
        self.assertEqual(positions[("after.py", 1)], 2)
        self.assertFalse(any(path == "old.py" for path, _ in positions))
        self.assertFalse(any(path == "picture.bin" for path, _ in positions))

    def test_counts_no_newline_markers(self):
        diff = """\
diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1 +1 @@
-old
\\ No newline at end of file
+new
\\ No newline at end of file
"""
        self.assertEqual(
            MODULE.parse_diff_positions(diff)[("a.py", 1)], 3
        )

    def test_decodes_git_quoted_utf8_and_space_paths(self):
        diff = (
            'diff --git "a/caf\\303\\251 name.py" "b/caf\\303\\251 name.py"\n'
            '--- "a/caf\\303\\251 name.py"\n'
            '+++ "b/caf\\303\\251 name.py"\n'
            "@@ -1 +1 @@\n-old\n+new\n"
        )
        positions = MODULE.parse_diff_positions(diff)
        self.assertEqual(positions[("caf\u00e9 name.py", 1)], 2)

    def test_does_not_split_code_on_unicode_line_separators(self):
        diff = DIFF.replace("+new\n", '+new = "\\u2028"\n'.replace(
            "\\u2028", "\u2028"
        ))
        self.assertEqual(
            MODULE.parse_diff_positions(diff)[("src/example.py", 3)], 4
        )

    def test_rejects_malformed_hunk_header(self):
        with self.assertRaisesRegex(ValueError, "hunk header"):
            MODULE.parse_diff_positions(DIFF.replace("@@ -1,3 +1,4 @@", "@@ bad"))

    def test_rejects_non_json_model_output(self):
        with self.assertRaisesRegex(ValueError, "valid JSON"):
            MODULE.extract_json('```json\n{"summary":"x","findings":[]}\n```')

    def test_rejects_unexpected_top_level_fields(self):
        with self.assertRaisesRegex(ValueError, "only summary and findings"):
            MODULE.extract_json(
                '{"summary":"x","findings":[],"commands":["do not run"]}'
            )

    def test_rejects_invalid_top_level_types(self):
        for value in [
            [],
            {"summary": "", "findings": []},
            {"summary": " ", "findings": []},
            {"summary": 4, "findings": []},
            {"summary": "x", "findings": {}},
        ]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                MODULE.extract_json(json.dumps(value))

    def test_rejects_duplicate_json_keys(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            MODULE.extract_json(
                '{"summary":"x","summary":"y","findings":[]}'
            )

    def test_rejects_non_finite_json_constants(self):
        with self.assertRaises(ValueError):
            MODULE.extract_json('{"summary":"x","findings":[NaN]}')

    def test_accepts_and_normalizes_literal_control_characters(self):
        text = (
            '{"summary":"Runtime'
            + "\n"
            + 'bug","findings":[{"severity":"high",'
            '"path":"src/example.py","line":3,'
            '"title":"Division'
            + "\t"
            + 'by zero","body":"Always fails."}]}'
        )
        review = MODULE.extract_json(text)
        payload, dropped = MODULE.build_payload(
            review, self.positions, "d" * 40
        )
        self.assertEqual(dropped, 0)
        self.assertIn("Runtime bug", payload["body"])
        self.assertIn(
            "**HIGH - Division by zero**", payload["comments"][0]["body"]
        )

    def test_drops_duplicate_and_unsafe_findings(self):
        payload, dropped = self.payload([
            self.finding,
            self.finding,
            {**self.finding, "path": "../src/example.py"},
            {**self.finding, "line": True},
            {**self.finding, "command": "ignored"},
        ])
        self.assertEqual(len(payload["comments"]), 1)
        self.assertEqual(dropped, 4)

    def test_drops_invalid_finding_fields(self):
        for finding in [
            None,
            "not an object",
            {**self.finding, "severity": "urgent"},
            {**self.finding, "severity": 1},
            {**self.finding, "line": 0},
            {**self.finding, "line": 3.0},
            {**self.finding, "line": "3"},
            {**self.finding, "title": 1},
            {**self.finding, "body": ""},
            {**self.finding, "path": "/src/example.py"},
            {**self.finding, "path": "C:\\src\\example.py"},
            {**self.finding, "path": "src/\x00example.py"},
        ]:
            with self.subTest(finding=finding):
                payload, dropped = self.payload([finding])
                self.assertEqual(payload["comments"], [])
                self.assertEqual(dropped, 1)

    def test_limits_to_eight_findings_and_counts_excess(self):
        positions = {("src/example.py", n): n for n in range(1, 11)}
        findings = [{**self.finding, "line": n} for n in range(1, 11)]
        payload, dropped = MODULE.build_payload(
            {"summary": "Review complete.", "findings": findings},
            positions,
            "e" * 40,
        )
        self.assertEqual(len(payload["comments"]), 8)
        self.assertEqual(dropped, 2)

    def test_cleans_controls_and_neutralizes_mentions(self):
        payload, _ = self.payload([
            {**self.finding, "body": "\x00Hi @reviewer\r\nCheck\tthis.\x7f"}
        ], summary="Notify @team\nnow")
        self.assertIn("@\u200bteam", payload["body"])
        self.assertIn("@\u200breviewer", payload["comments"][0]["body"])
        self.assertNotIn("\x00", payload["comments"][0]["body"])
        self.assertNotIn("\r", payload["comments"][0]["body"])

    def test_limits_text_lengths(self):
        self.assertEqual(len(MODULE.clean_text("x" * 5000, 4000)), 4000)
        self.assertEqual(len(MODULE.clean_text("x" * 200, 160)), 160)
        self.assertEqual(len(MODULE.clean_text("x" * 3000, 2500)), 2500)

    def test_empty_findings_produce_comment_only_review(self):
        payload, dropped = self.payload([])
        self.assertEqual(payload["comments"], [])
        self.assertEqual(dropped, 0)
        self.assertIn("No high-confidence inline findings", payload["body"])

    def test_rejects_summary_that_becomes_empty_after_cleaning(self):
        with self.assertRaisesRegex(ValueError, "summary"):
            self.payload([], summary="\x00")

    def test_rejects_invalid_commit_id(self):
        for sha in ["", "main", "a" * 39, "g" * 40, "a" * 40 + "\n"]:
            with self.subTest(sha=sha), self.assertRaisesRegex(
                ValueError, "head SHA"
            ):
                MODULE.build_payload(
                    {"summary": "x", "findings": []}, self.positions, sha
                )

    def test_input_limits_are_exact_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input.txt"
            for limit in [MODULE.MAX_DIFF_BYTES, MODULE.MAX_REVIEW_BYTES]:
                with self.subTest(limit=limit):
                    path.write_bytes(b"x" * limit)
                    self.assertEqual(
                        len(MODULE.read_limited(path, limit)), limit
                    )
                    path.write_bytes(b"x" * (limit + 1))
                    with self.assertRaisesRegex(ValueError, "limit"):
                        MODULE.read_limited(path, limit)

    def test_cli_writes_valid_utf8_payload(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            diff = root / "pull-request.diff"
            review = root / "review-model.json"
            output = root / "review-payload.json"
            diff.write_text(DIFF, encoding="utf-8")
            review.write_text(json.dumps({
                "summary": "Review complete.", "findings": [self.finding]
            }), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--diff", str(diff),
                 "--review", str(review), "--head-sha", "f" * 40,
                 "--output", str(output)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["commit_id"], "f" * 40)
            self.assertEqual(payload["comments"][0]["position"], 4)
            review.write_text("not json", encoding="utf-8")
            output.unlink()
            result = subprocess.run(result.args, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())
            self.assertIn("valid JSON", result.stderr)


if __name__ == "__main__":
    unittest.main()
