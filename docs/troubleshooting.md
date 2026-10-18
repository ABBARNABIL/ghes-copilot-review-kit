# Troubleshooting

Start with the Actions job/step that failed and its exit message. Check the
review conversation before retrying publication. Never paste tokens, private
keys, raw CLI homes/transcripts, or confidential source into diagnostics.

| Symptom | Checks and action |
| --- | --- |
| No review after opening/pushing a PR | Expected: the template has no `opened`, `synchronize`, or push trigger. Add the `copilot-review` **label**, use the exact trusted slash comment, or dispatch manually. |
| Comment-triggered job is skipped | Must be a PR conversation comment exactly `/copilot review`, with `OWNER`, `MEMBER`, or `COLLABORATOR` association. Whitespace, issue-only comments, and edited comments do not qualify. |
| Workflow absent from Actions/manual dispatch | Merge the workflow into the default branch. Choose a reviewed/trusted branch for dispatch and provide a positive integer PR number. Check repository Actions policy. |
| Job queued indefinitely | Confirm an online, idle Linux x64 runner with all labels `self-hosted`, `linux`, `x64`, `copilot-ghes`, and that its runner group permits this repo. Check GHES Actions/storage health. |
| CLI/tools missing or version check fails | Install the exact `@github/copilot@1.0.95`, Python 3.10+, curl 7.76+, jq, Git, OpenSSL, and coreutils. Check the **service** PATH, not only the administrator shell. See [runner setup](runner.md). |
| TLS, certificate, or proxy failure | Fix DNS/SNI, certificate chain, approved OS/Node CA bundles and service proxy variables. Checkout ignores global/system Git config, so use OS trust or `GIT_SSL_CAINFO`. Never disable verification. |
| GHES API 401/403/404 during clone | Check GHES `GITHUB_TOKEN` permissions, target repository/PR existence, Actions/fork policy, and the correct GHES `/api/v3` origin. A GitHub.com inference token must not be used for GHES reads. |
| Missing trusted validator | Install `.github/scripts/build_review_payload.py` in the PR's **base branch/commit**, not merely in its head or the default branch. It and its parent directories must not be symlinks. |
| Reserved `.copilot-review-context` path | Remove that path from PR code or use a separately reviewed, consistently renamed workflow context path. The kit refuses both real directories/files and dangling symlinks there. |
| PR head/base changed | The snapshot check intentionally failed. Wait for pushes/base changes to settle and request a new review. Pushes alone do not request one. |
| Copilot authentication/entitlement denied | Check the GitHub.com user-owned fine-grained token, **Copilot Requests** account permission, expiry/revocation, active entitlement, and organization/enterprise CLI policy. A GHES token, classic PAT, or App token is not a substitute. |
| Copilot network or rate/usage limit error | Check the [current allowlist](https://docs.github.com/en/copilot/reference/copilot-allowlist-reference), plan/model routes, service proxy and CA trust, request limits, and approved usage budget. Do not widen network/policy permissions blindly. |
| Diff exceeds 1 MB | Split/reduce the PR. The limit is 1,000,000 bytes, not a model truncation setting. The workflow refuses instead of silently reviewing only part of it. |
| Empty/invalid/oversized model JSON | No review is published. Inspect failure metadata without exporting source/secrets. A new approved request may resolve a transient model format failure; output is limited to 100,000 bytes. Literal string control normalization is intentional, but Markdown fences/extra schema fields are not accepted. |
| Finding was discarded or no inline comments | Check paths, integer RIGHT-side line numbers, supported severity/text, duplicate locations, and the canonical API diff. Visible context is allowed; deleted/off-diff/binary-only lines are not. Inspect the explicit discarded count. |
| App JWT/private key failure | Use the numeric **GHES App ID**, not Client ID; keep the entire matching PEM key with real newlines. Check key rotation, runner clock/NTP, and GHES TLS. JWT signing uses RS256 and a lifetime under ten minutes. |
| Installation lookup/token request 401/403/404 | App must be registered on this GHES host, installed on this exact repository, with approved PR read/write permission. Confirm the key/App pair and installation scope. No external webhook server is needed. |
| Review POST 403/422 or unexpected author/state | Confirm App PR write access, PR/commit state, exact head SHA and canonical positions. A successful result must be `COMMENTED`, Bot-authored, for that commit. Do not replace App publication with the inference user's PAT. |
| Label remains after a successful review | Read the warning. Label cleanup uses the App token and is best effort. Verify PR write permission and version-specific label endpoint behavior before requesting any extra permissions. Remove/re-add it manually through the approved UI, or use a new slash/manual request. |
| Run cancelled, timed out, or failed after POST | A review may already exist. Inspect the PR before rerunning. Accepted requests for the same PR cancel previous jobs, but cancellation cannot retract a completed POST. |
| Workspace remains after runner failure | Normal cleanup runs with `always()`, but host loss/forced termination can prevent it. Authorized ops should inspect only the exact affected `RUNNER_TEMP/copilot-review-RUNID-ATTEMPT` directory and follow retention/reimaging policy. Never delete the runner temp root indiscriminately. |
| Installer reports a collision | Nothing is overwritten. Export into an existing empty staging directory and compare/merge the two files manually. Identical files are safe to rerun. |
| Installer reports a link/junction or invalid parent | Use a normal directory tree inside the intended checkout; do not bypass the path guard or install through links to another location. |

## Safe diagnostic checklist

Record the kit commit, GHES release, runner OS/runner version, CLI version,
failed step, timestamp/run URL, HTTP status, and whether an App review already
exists. Do not collect the App key, installation token/JWT, inference token,
private CA keys, or raw customer source. A review URL may itself identify a
private customer repository; share it only within the approved audience.

For a copy/install issue, run `--dry-run` from the kit root and inspect the
two destination paths. For workflow behavior, run the offline tests from the
kit root; they cannot validate live entitlement, GHES compatibility, or
customer authorization.
