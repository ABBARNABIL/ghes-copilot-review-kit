# Installing into an existing GHES repository

Use this guide per customer/repository. The kit does not change a live GHES
instance, register runners, create Apps, set secrets, or provision storage.
Those actions remain with the customer's authorized administrators.

## Client checklist

Record real values in the customer's approved operations system, **not in this
distribution repository**. The examples below are deliberately fictitious.

| Item | Example or required decision |
| --- | --- |
| GHES HTTPS origin and release | `https://ghes.example.com`; assess against the original 3.21.3 lab baseline |
| Target repository and trusted base branches | `client-org/service`, default branch plus any release branches to review |
| GHES Actions and external storage | Enabled, healthy, and authorized for this repository |
| Runner ownership and placement | Dedicated Linux x64 runner/service account, label `copilot-ghes`, one customer trust boundary |
| Runner tools and CLI | See [runner setup](runner.md); CLI pinned to `1.0.95` |
| Trust/network | Approved enterprise CA chain, GHES/API/storage reachability, outbound Copilot access |
| Cloud/data approval | Approval to send diff and selected source context to GitHub.com Copilot; approved identity, plan, policy, retention, and budgets |
| GHES App | Client-owned App ID, installation on this repository, key custodian/rotation process |
| Secrets | Three names below, expiry/rotation owners recorded without their values |
| Workflow protections | Trusted maintainers review workflow/validator changes; restrict runner groups and repository write access |
| Rollout evidence | Kit commit deployed, customer smoke PR, App review URL, tested GHES/runner/CLI versions |

### GHES Actions is an infrastructure prerequisite

A GHES site administrator must first enable Actions and configure supported
external blob storage. This includes workflow logs even if the kit does not
upload artifacts. Use the
[GHES Actions getting-started guide](https://docs.github.com/en/enterprise-server@3.21/admin/managing-github-actions-for-your-enterprise/getting-started-with-github-actions-for-your-enterprise/getting-started-with-github-actions-for-github-enterprise-server)
and the procedure for the customer's storage provider.

An existing supported MinIO deployment is one possible storage choice; it is
not a dependency to deploy from this repository. Azure, VMware, and on-premises
placement do not change the review workflow's credential boundaries.

## GitHub App permissions

Create a **GitHub App on the customer's GHES host**, under the appropriate
customer user/organization account. A GitHub.com App registration cannot
publish to a separate GHES instance.

1. In GHES account/organization settings, open Developer settings > GitHub Apps
   and create an App. A name such as `Copilot Review` is fine if available.
   Use a customer-approved homepage URL.
2. Disable **Active** webhooks. No webhook receiver, subscribed events, OAuth
   callback, or external server is required: Actions events trigger the job.
3. Set repository permissions to **Metadata: read** (implicit/required) and
   **Pull requests: read and write**. Leave other permissions unset.
4. Install the App on **only the target repository**. Prefer separate
   customer-owned registrations/keys rather than sharing a key across clients.
5. Record the numeric **App ID**, not the OAuth Client ID. Generate/download
   a private key into approved secret storage and keep its complete multiline
   PEM content for the repository secret.

For label removal, the
[current REST endpoint documentation](https://docs.github.com/en/rest/issues/labels#remove-a-label-from-an-issue)
explicitly accepts **either Issues: write or Pull requests: write**, including
GitHub App installation tokens. The
[GHES 3.21 endpoint](https://docs.github.com/en/enterprise-server@3.21/rest/issues/labels#remove-a-label-from-an-issue)
is App-enabled. Therefore this kit uses the already-required PR permission
and **does not request Issues: write**. Verify this on the deployed GHES release.
If cleanup returns 403, first confirm installation permissions/approvals and
the version-specific endpoint requirements. Do not add broader permissions
unless the customer's actual release requires them and the customer approves.

The workflow explicitly scopes each installation token down to this repository
and `pull_requests: write`; metadata access is implicit. The App is a publishing
identity, **not a native selectable Copilot reviewer**.

References:
[registering an App](https://docs.github.com/en/enterprise-server@3.21/apps/creating-github-apps/registering-a-github-app/registering-a-github-app),
[App JWT authentication](https://docs.github.com/en/enterprise-server@3.21/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-json-web-token-jwt-for-a-github-app),
[installation tokens](https://docs.github.com/en/enterprise-server@3.21/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app).

## Repository secrets

In the **GHES target repository**, use Settings > Secrets and variables >
Actions > Repository secrets:

| Name | Value |
| --- | --- |
| `COPILOT_GITHUB_TOKEN` | Customer-approved GitHub.com **user-owned fine-grained PAT** with the **Copilot Requests** account permission |
| `COPILOT_REVIEW_APP_ID` | Numeric App ID of the GHES App above |
| `COPILOT_REVIEW_APP_PRIVATE_KEY` | Entire multiline PEM private key for that App, including BEGIN/END lines; not a base64 wrapper |

For the Copilot token, choose the approved **personal account** as resource
owner; the Copilot Requests permission is not available on organization-owned
fine-grained tokens. The kit needs no access to private GitHub.com repositories:
the source is cloned independently from GHES. Do not add private GitHub.com
repository permissions just to run this local review.

The token owner needs an active Copilot entitlement and policy permission to use
CLI. Confirm the customer's approved authentication and usage arrangement;
do not assume your own account is approved for every customer's source.
Classic PATs and the GHES workflow token are not substitutes. See
[official CLI installation/authentication](https://docs.github.com/en/copilot/how-tos/copilot-cli/set-up-copilot-cli/install-copilot-cli)
and [Copilot policies](https://docs.github.com/en/copilot/how-tos/administer-copilot/manage-for-organization/manage-policies).

`GITHUB_TOKEN` is generated by GHES for each workflow run. **Do not create a
fourth secret for it** and do not increase its read-only workflow permissions.
Do not put any token, key, CA private key, or client-specific configuration
in the copied files or commit history.

## Copy the templates

Use Python 3.10 or newer on the administrator workstation. You can clone this
private kit using your authorized GitHub.com account or download an approved
snapshot. An authorized GitHub CLI example is:

```powershell
gh repo clone https://github.com/ABBARNABIL/ghes-copilot-review-kit
Set-Location .\ghes-copilot-review-kit
python .\tools\install.py --target "C:\work\client-repo" --dry-run
python .\tools\install.py --target "C:\work\client-repo"
```

Linux equivalent, from the kit root:

```bash
python3 tools/install.py --target /work/client-repo --dry-run
python3 tools/install.py --target /work/client-repo
```

The target must already exist. It may be an existing checkout/worktree or an
empty staging directory for an offline file transfer. The command does not
require Git metadata and **does not run any code from the target**.

Only these paths are installed, byte for byte:

```text
.github/workflows/copilot-review.yml
.github/scripts/build_review_payload.py
```

The installer preflights both files before writing. Identical files are
`UNCHANGED`; different files, symlink/junction destinations, and non-directory
parents cause a nonzero exit without overwriting. A concurrent filesystem
change or I/O error can leave newly created files, but exclusive creation
prevents replacing existing files. Rerun after resolving the error.
Do not concurrently edit the destination while installing.

No hostname is hardcoded into the templates: `GITHUB_SERVER_URL`,
`GITHUB_API_URL` (GHES `/api/v3`), and `GITHUB_REPOSITORY` come from Actions.
Change `runs-on` only if the customer uses a different approved runner label.
The `.copilot-review-context` path is reserved and must not exist in PR code.

Review and commit the two files through the customer's normal change process.
Merge them into the **default branch and each trusted PR base branch** to be
reviewed: the validator is deliberately read from the PR's exact base commit.
Leaving the installation only on an open setup PR is not enough.

Protect both files as privileged automation. For comment requests the workflow
comes from the default branch; for `pull_request_target`, it comes from the
trusted PR base context. Manual dispatch must select a reviewed, trusted workflow
branch. Protect runner access from other workflows too; this template cannot
make arbitrary workflows in the same repository safe.

## First review and acceptance

Create the repository label **`copilot-review`** using the GHES UI. Do not
create a Git tag. Then use an approved small test PR:

1. Confirm the runner is online, idle, and has `self-hosted`, `linux`, `x64`,
   and `copilot-ghes` labels.
2. As a trusted collaborator, comment exactly `/copilot review` in the PR
   conversation, or use Actions > Copilot Review App > Run workflow with its
   positive PR number.
3. Check that the review is posted as the **App bot**, not the PAT owner or
   `github-actions[bot]`, with `COMMENTED` state and the reviewed head commit.
   A no-finding review is still a comment, not an approval.
4. Add `copilot-review` to request another review. Verify it is removed after
   successful publication. A warning about removal does not undo a posted review.
5. Confirm ordinary issue comments, unauthorized slash comments, PR opening,
   and subsequent pushes do not cause inference. Verify a second accepted
   request for the same PR cancels an older pending/in-progress job.

This customer smoke test **does consume Copilot usage**. It is not performed
by this kit's offline tests or distribution CI. Test each customer version,
fork policy, runner isolation, App permissions, and data policy before rollout.
If the PR changes during a run, the job refuses a stale snapshot; request a new
review. There remains a narrow API race immediately after the last check, but
the published review is always anchored with the exact reviewed `commit_id`.

## Upgrades and rollback

Record the kit commit used for each deployment. Export a newer version to a
separate, existing empty directory, compare both files, and merge reviewed
updates through the client's normal process. There is intentionally no
`--force`, overwrite, automatic patch, or remote deployment option.

The CLI version is pinned in the workflow and runner guide. To change it,
review the release/flag behavior, update the pin and documentation together,
run offline checks, and repeat the customer's live smoke test. Automatic CLI
updates are disabled during reviews. Model selection follows the approved
CLI/account default and is not pinned; model responses are not deterministic.

For rollback, cancel active review jobs and revert the two installed files
through the customer's approved Git process, or disable this workflow. Retire
the App installation/key and secrets only if they are no longer used. Runner
de-registration and credential revocation remain authorized customer actions.
