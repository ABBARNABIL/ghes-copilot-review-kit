# GHES Copilot review setup kit

Install **custom, on-demand pull request reviews** in an existing GitHub
Enterprise Server repository using Actions, a dedicated Linux runner,
Copilot CLI, and a repository-scoped GitHub App.

This is **not native GHES Copilot code review**, a selectable Copilot reviewer,
or the Copilot coding agent. It does not edit code or approve/block merges.
The original lab baseline was **GHES 3.21.3, Linux x64, Copilot CLI 1.0.95**.
The packaged workflow has offline regression coverage, not a compatibility
guarantee for every GHES/CLI release or customer configuration.

> **Customer approval required:** the runner needs outbound GitHub.com
> Copilot connectivity. The diff and selected source context are sent to
> the cloud using the approved token owner's Copilot entitlement. This is
> **not an air-gapped solution**. Review policy, data handling, entitlement,
> and usage limits before enabling it.

## Quickstart

1. Complete the [installation checklist](docs/installation.md), including
   healthy GHES Actions/storage, a [dedicated runner](docs/runner.md),
   a GHES GitHub App, and the three repository secrets.
2. Clone/download this private distribution repository on your workstation.
   From its root, preview and install into an **existing local client checkout**:

   ```powershell
   python .\tools\install.py --target "C:\work\client-repo" --dry-run
   python .\tools\install.py --target "C:\work\client-repo"
   ```

   On Linux:

   ```bash
   python3 tools/install.py --target /work/client-repo --dry-run
   python3 tools/install.py --target /work/client-repo
   ```

3. Review the two copied files and merge them into the client's default branch
   and any other trusted PR base branches you intend to review.
4. Open a small test PR and request a review using one of these entry points:

| Request | Behavior |
| --- | --- |
| Add the **`copilot-review` PR label** | Runs `pull_request_target: labeled`; a successful review removes the label so it can be added again. This is a label, not a Git tag. |
| Comment exactly **`/copilot review`** in the PR conversation | Runs only for `OWNER`, `MEMBER`, or `COLLABORATOR` author associations. Extra text/whitespace and issue-only comments do not qualify. |
| Actions > **Copilot Review App** > Run workflow | Provide a positive PR number and select a trusted workflow branch. |

Opening or pushing to a PR alone does **not** request a review. A new accepted
request cancels an older run for the same repository/PR. Unrelated comments
do not cancel a review. The result is a `COMMENT` review and up to eight
validated inline findings, posted by `copilot-review[bot]` or your App's slug.

## What is installed

```text
templates/ghes/
  .github/workflows/copilot-review.yml
  .github/scripts/build_review_payload.py
tools/install.py
tests/
docs/
```

The installer copies only the **two files beneath `templates/ghes`**. It never
contacts GHES, configures infrastructure, creates credentials, commits, or
pushes. It preflights all collisions, leaves identical files unchanged, refuses
different existing files and linked destination paths, and has no force option.
For an export, point it at an existing empty staging directory. See
[upgrades and rollback](docs/installation.md#upgrades-and-rollback).

The distribution repository's own `.github/workflows/ci.yml` runs offline
checks on GitHub.com. It does not queue the GHES review workflow or call Copilot.

## Credentials

| Credential | Used for |
| --- | --- |
| GHES-generated `GITHUB_TOKEN` | GHES repository/PR reads only: `contents: read`, `pull-requests: read`. No secret to create. |
| `COPILOT_GITHUB_TOKEN` repository secret | GitHub.com Copilot inference only; a customer-approved, user-owned fine-grained token with **Copilot Requests**. |
| `COPILOT_REVIEW_APP_ID` and `COPILOT_REVIEW_APP_PRIVATE_KEY` repository secrets | GHES App JWT and short-lived repository installation token, used only by deterministic publication. |

The GHES App needs **Metadata: read** and **Pull requests: read/write**.
It is not the inference identity and needs no Contents permission.
[Label removal also accepts Pull requests: write](docs/installation.md#github-app-permissions);
do not grant broad Issues permissions by default.

## Guides and checks

| Guide | Contents |
| --- | --- |
| [Installation](docs/installation.md) | Client-specific checklist, App/secrets, copy/merge, first review, upgrades |
| [Linux runner](docs/runner.md) | Official registration, tools, pinned CLI, service PATH, CA/TLS, connectivity |
| [Architecture and security](docs/architecture-security.md) | Trust boundaries, data flow, restrictions, limitations |
| [Troubleshooting](docs/troubleshooting.md) | Trigger, runner, authentication, payload, and publication failures |

Kit contributors can run the same offline checks as CI:

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
git diff --check
```

Runtime Python code uses only the standard library; PyYAML is a **test-only**
dependency. Tests cover canonical diff positions, JSON/control normalization,
input limits, installer dry runs/collisions/idempotence, YAML contracts, Bash
syntax, request validation, and scoped cleanup. They do not prove live GHES
compatibility, Copilot entitlement, or model quality.

If you have `actionlint` 1.7.7 installed, the checked-in custom-runner label
configuration also supports linting both workflows:

```powershell
actionlint -config-file .github\actionlint.yml .github\workflows\ci.yml templates\ghes\.github\workflows\copilot-review.yml
```

No Azure, Foundry, `azd`, MinIO deployment, external webhook server, or coding-agent
workflow is included. GHES Actions infrastructure is a separate prerequisite,
whether hosted on-premises, on VMware, or in a cloud. No license has been selected.
