import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "templates" / "ghes" / ".github" / "workflows" / "copilot-review.yml"
BASH = shutil.which("bash")


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")
        cls.workflow = yaml.safe_load(cls.text)
        cls.job = cls.workflow["jobs"]["review"]
        cls.steps = {step["name"]: step for step in cls.job["steps"]}

    def test_only_explicit_review_requests_trigger_the_template(self):
        triggers = self.workflow["on"]
        self.assertEqual(
            set(triggers), {"workflow_dispatch", "issue_comment", "pull_request_target"}
        )
        self.assertEqual(triggers["issue_comment"]["types"], ["created"])
        self.assertEqual(triggers["pull_request_target"]["types"], ["labeled"])
        self.assertEqual(
            triggers["workflow_dispatch"]["inputs"]["pr_number"]["type"], "number"
        )
        gate = self.job["if"]
        for required in [
            "github.event.issue.pull_request",
            "github.event.comment.body == '/copilot review'",
            "OWNER", "MEMBER", "COLLABORATOR",
            "github.event.label.name == 'copilot-review'",
        ]:
            self.assertIn(required, gate)

    def test_concurrency_applies_only_after_request_authorization(self):
        self.assertNotIn("concurrency", self.workflow)
        self.assertTrue(self.job["concurrency"]["cancel-in-progress"])
        self.assertIn("github.repository", self.job["concurrency"]["group"])
        self.assertIn("github.event.issue.number", self.job["concurrency"]["group"])

    def test_workflow_token_is_read_only_and_no_marketplace_actions_are_needed(self):
        self.assertEqual(
            self.workflow["permissions"],
            {"contents": "read", "pull-requests": "read"},
        )
        self.assertTrue(all("uses" not in step for step in self.job["steps"]))
        self.assertEqual(
            self.job["runs-on"], ["self-hosted", "linux", "x64", "copilot-ghes"]
        )
        self.assertEqual(self.job["timeout-minutes"], 30)

    def test_credentials_are_scoped_to_separate_steps(self):
        env = {name: step.get("env", {}) for name, step in self.steps.items()}
        self.assertEqual(
            env["Clone pull request safely"]["GHES_TOKEN"], "${{ github.token }}"
        )
        for name, values in env.items():
            if name != "Generate and validate inline review":
                self.assertNotIn("COPILOT_GITHUB_TOKEN", values)
            if name != "Publish review as Copilot Review App":
                self.assertNotIn("APP_PRIVATE_KEY", values)
                self.assertNotIn("APP_ID", values)
            if name != "Clone pull request safely":
                self.assertNotIn("GHES_TOKEN", values)

    def test_clones_trusted_base_and_preserves_validator_before_pr_checkout(self):
        script = self.steps["Clone pull request safely"]["run"]
        base_checkout = script.index('git checkout --detach "${base_sha}"')
        validator_copy = script.index('install -m 0700')
        head_checkout = script.index('git checkout --detach "${head_sha}"')
        self.assertLess(base_checkout, validator_copy)
        self.assertLess(validator_copy, head_checkout)
        self.assertIn("refs/pull/${PR_NUMBER}/head", script)
        self.assertIn("git-askpass.sh", script)
        self.assertIn('test ! -L "${validator}"', script)
        self.assertIn('test ! -L "${repo_dir}/.github"', script)
        self.assertIn('test ! -L "${repo_dir}/.github/scripts"', script)

    def test_rejects_reserved_context_paths_and_stale_snapshots(self):
        script = self.steps["Clone pull request safely"]["run"]
        self.assertIn('[ -e "${context_dir}" ] || [ -L "${context_dir}" ]', script)
        self.assertIn("pull-request-after-diff.json", script)
        publish = self.steps["Publish review as Copilot Review App"]["run"]
        self.assertIn("pull-request-before-publish.json", publish)
        self.assertIn(".head.sha == $head", publish)
        self.assertIn(".base.sha == $base", publish)

    def test_cli_has_only_read_tools_and_pinned_version(self):
        self.assertEqual(self.job["env"]["COPILOT_CLI_VERSION"], "1.0.95")
        self.assertEqual(self.job["env"]["COPILOT_AUTO_UPDATE"], "false")
        script = self.steps["Generate and validate inline review"]["run"]
        for option in [
            "--available-tools='view,grep,glob'",
            "--no-ask-user", "--no-custom-instructions",
            "--disable-builtin-mcps", "--no-remote-export",
            "--no-auto-update", "--no-color", "--stream off",
        ]:
            self.assertIn(option, script)
        self.assertNotIn("--allow-all", script)
        self.assertIn("100000", script)
        self.assertIn("1000000", self.steps["Clone pull request safely"]["run"])

    def test_headers_are_real_environment_expansions_not_redacted_placeholders(self):
        self.assertNotIn("******", self.text)
        clone = self.steps["Clone pull request safely"]["run"]
        publish = self.steps["Publish review as Copilot Review App"]["run"]
        self.assertIn('Authorization: Bearer ${GHES_TOKEN}', clone)
        self.assertIn('Authorization: Bearer ${app_jwt}', publish)
        self.assertIn('Authorization: Bearer ${installation_token}', publish)
        self.assertIn('::add-mask::${app_jwt}', publish)
        self.assertIn('::add-mask::${installation_token}', publish)
        self.assertIn('repository_ids: [$repository_id]', publish)
        self.assertIn('pull_requests: "write"', publish)

    def test_publication_checks_bot_review_and_does_not_retry_post(self):
        script = self.steps["Publish review as Copilot Review App"]["run"]
        self.assertIn('.state == "COMMENTED"', script)
        self.assertIn('.user.type == "Bot"', script)
        self.assertIn("issues/${PR_NUMBER}/labels/copilot-review", script)
        self.assertIn("::warning::", script)
        self.assertNotIn("--retry", script)
        self.assertNotIn("upload-artifact", self.text)

    def test_shell_blocks_do_not_interpolate_actions_expressions(self):
        self.assertEqual(self.job["defaults"]["run"]["shell"], "bash")
        for name, step in self.steps.items():
            with self.subTest(step=name):
                self.assertNotIn("${{", step["run"])

    @unittest.skipUnless(BASH, "Bash is required for shell syntax checks")
    def test_all_shell_blocks_parse(self):
        for name, step in self.steps.items():
            with self.subTest(step=name):
                result = subprocess.run(
                    [BASH, "-n"], input=step["run"],
                    text=True, capture_output=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(BASH, "Bash is required for input execution checks")
    def test_pr_number_validation_executes_offline(self):
        script = self.steps["Validate pull request number"]["run"]
        for number, valid in [
            ("1", True), ("42", True), ("0", False), ("-1", False),
            ("1.5", False), ("01", False), ("", False), ("1; exit 0", False),
        ]:
            with self.subTest(number=number):
                result = subprocess.run(
                    [BASH, "-c", script], text=True, capture_output=True,
                    env={**os.environ, "PR_NUMBER": number},
                )
                self.assertEqual(result.returncode == 0, valid, result.stderr)

    @unittest.skipUnless(BASH, "Bash is required for cleanup execution checks")
    def test_cleanup_removes_only_the_exact_job_workspace(self):
        step = self.steps["Remove review workspace"]
        self.assertEqual(step["if"], "always()")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "copilot-review-123-1"
            target.mkdir()
            (target / "temporary.txt").write_text("synthetic", encoding="utf-8")
            sibling = root / "copilot-review-123-2"
            sibling.mkdir()
            env = {
                **os.environ, "RUNNER_TEMP": root.as_posix(),
                "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1",
            }
            result = subprocess.run(
                [BASH, "-c", step["run"]], env=env,
                text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(target.exists())
            self.assertTrue(sibling.exists())
            self.assertTrue(root.exists())
            env["GITHUB_RUN_ID"] = "../"
            result = subprocess.run(
                [BASH, "-c", step["run"]], env=env,
                text=True, capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(sibling.exists())

    def test_distribution_repository_only_runs_offline_ci(self):
        paths = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual([path.name for path in paths], ["ci.yml"])
        ci = yaml.safe_load(paths[0].read_text(encoding="utf-8"))
        self.assertEqual(ci["permissions"], {"contents": "read"})
        self.assertNotIn("copilot -p", paths[0].read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
