# Dedicated Linux x64 runner

The original integration was exercised with GHES 3.21.3 and Copilot CLI 1.0.95.
Use a supported Linux x64 image for your GHES runner release. Validate the
customer's actual release and image; this guide does not provision a VM,
container platform, storage service, or any cloud resources.

## Isolation and tools

Use a dedicated, non-root service account and a runner assigned only to the
approved customer/repository trust boundary. Do not reuse your workstation,
GHES appliance, or a runner with unrelated workloads or stored developer
credentials. Restrict runner groups and who can schedule jobs on them.
An ephemeral/reimaged runner is preferable where operationally possible.

Required tools on the runner service's PATH:

| Tool | Requirement |
| --- | --- |
| Bash and coreutils | Bash 4+, `install`, `mkdir`, `chmod`, `rm`, `wc`, `date`, `tr`, `cat`, `grep` |
| Git | Supported Git 2.x; HTTPS and PR-ref fetch support |
| curl | 7.76+ with `--fail-with-body`, working CA trust |
| jq | 1.6+ |
| Python | `python3`, version 3.10+; standard library only |
| OpenSSL | Supported version with RSA SHA-256 signing and `pkey` |
| Copilot CLI | **Exactly 1.0.95**, checked before inference |
| Node/npm | Node 22+ if using the npm installation below |

For a Debian/Ubuntu image, an administrator can install the system tools using
the organization's approved repositories:

```bash
sudo apt-get update
sudo apt-get install --yes ca-certificates git curl jq python3 openssl
```

Install an approved Node 22+ build separately if needed; do not assume the
distribution's default `nodejs` package is new enough. Other distributions
must use equivalent supported packages.

## Pin Copilot CLI

Use the official **`@github/copilot`** package, not the retired `gh copilot`
extension. After approving the package and its install scripts, an administrator
can install a versioned prefix:

```bash
sudo npm install --global --prefix /opt/copilot-cli-1.0.95 @github/copilot@1.0.95
export PATH="/opt/copilot-cli-1.0.95/bin:$PATH"
COPILOT_AUTO_UPDATE=false copilot --no-auto-update --version
copilot --no-auto-update --help
```

Expect version **1.0.95**. Do not replace the exact npm version with `latest`
or a prerelease tag. If organizational npm policy disables install scripts,
follow the official package instructions with security approval rather than
silently ending up without the executable.

For reproducible provisioning, retain the approved package/integrity metadata,
Node build, OS image, and dependencies in the customer's approved artifact
mirror/image. An exact CLI version alone does not pin the entire OS/dependency
environment. Official release executables are an alternative; select the exact
release/platform and verify the published checksum through your normal
software-supply-chain process.

Make this PATH persistent in the **runner service environment**, not only your
interactive shell, and restart the service through the approved procedure.
Keep the installed tools read-only to workloads where practical. Do not run a
live prompt as a version/authentication test: `--version`/`--help` need no model
request. No persistent `copilot login` is necessary; inference receives the
repository secret for that step.

Reference: [official install methods](https://docs.github.com/en/copilot/how-tos/copilot-cli/set-up-copilot-cli/install-copilot-cli).

## Trust the enterprise CA

Use a valid HTTPS GHES certificate with the complete approved chain. If the
customer uses a private enterprise root, install the **public CA certificate**
in the runner's OS trust store. Never transfer a CA private key into this kit.
A Debian/Ubuntu example, after verifying the certificate's provenance:

```bash
sudo install -m 0644 /path/to/approved-enterprise-root.crt \
  /usr/local/share/ca-certificates/enterprise-root.crt
sudo update-ca-certificates
```

Ensure the runner, Git, curl, and Node/Copilot all trust the relevant CA chains.
For an approved TLS-inspecting proxy, Node may also need
`NODE_EXTRA_CA_CERTS=/path/to/approved-ca-bundle.pem`. Where needed, set
`GIT_SSL_CAINFO` and `CURL_CA_BUNDLE` to the approved PEM bundle, such as the
OS bundle `/etc/ssl/certs/ca-certificates.crt`, in the service environment.

The checkout step intentionally ignores system/global Git configuration, so
`git config --global http.sslCAInfo ...` alone is **not sufficient**; use OS
trust or `GIT_SSL_CAINFO`. It also disables credential helpers and checkout
hooks and uses an empty Git template directory. Submodules, LFS smudge filters,
builds, tests, and package installation from the PR are not run.

Never use `curl -k`, `GIT_SSL_NO_VERIFY`, `NODE_TLS_REJECT_UNAUTHORIZED=0`, or
runner TLS verification bypasses. Restart the runner service after approved
environment/trust changes.

## Network reachability

Allow the service account/runner to reach:

| Destination | Purpose |
| --- | --- |
| Customer GHES HTTPS origin and `/api/v3` | Actions control plane, Git clone/fetch, PR metadata/diff, App authentication and review APIs |
| Configured Actions storage/log endpoints | Normal GHES Actions operation |
| GitHub.com authentication/API and Copilot service endpoints | GitHub.com token validation and Copilot inference |
| Approved npm/Node/release artifact sources | Provisioning only; omit from runtime access if preinstalled |

Use the [current Copilot allowlist](https://docs.github.com/en/copilot/reference/copilot-allowlist-reference)
and the customer's plan-specific routing policy. It includes more than
`github.com` alone; Copilot APIs use `*.githubcopilot.com` and other documented
hosts. DNS, TLS/SNI, proxy behavior, and the actual selected model's endpoints
must work. Do not treat a static two-host list as complete.

Configure supported `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY` settings for the
runner service as required, without committing credentials in proxy URLs.
Follow the GHES and Copilot proxy documentation for each component; they do
not necessarily have identical proxy/CA behavior. No inbound public webhook
receiver is required.

These checks make no inference request and send no repository source:

```bash
git --version
curl --version
jq --version
python3 --version
openssl version
COPILOT_AUTO_UPDATE=false copilot --no-auto-update --version
curl --silent --show-error --output /dev/null --write-out 'GHES HTTP %{http_code}\n' \
  https://ghes.example.com/api/v3/meta
curl --silent --show-error --output /dev/null --write-out 'GitHub HTTP %{http_code}\n' \
  https://api.github.com/meta
```

An unauthenticated GHES 401/403 may be expected in private mode; it is not a
successful authorization test. These probes check basic reachability/TLS,
**not** Copilot entitlement, all inference endpoints, or App publication.
The [approved customer smoke review](installation.md#first-review-and-acceptance)
checks those live boundaries.

## Official runner registration

In the target GHES repository, navigate to Settings > Actions > Runners >
New self-hosted runner, then choose **Linux / x64**. Follow the generated
download, checksum verification, extraction, and registration instructions
for that GHES release. Do not hardcode a runner release copied from another
server or use a GitHub.com registration token.

Run registration as the dedicated service account, not root. Add the
`copilot-ghes` custom label and retain the default `self-hosted`, `linux`, and
`x64` labels. A schematic registration command, after the official download:

```bash
./config.sh --url https://ghes.example.com/OWNER/REPO \
  --token "$REGISTRATION_TOKEN" --labels copilot-ghes --unattended
unset REGISTRATION_TOKEN
```

Obtain that short-lived token from the authorized GHES registration page/API;
never save it in this repository or logs. Use the generated instructions if
your enterprise requires an organization runner group or other registration
options. Confirm it connects and appears **Idle** before continuing.

Follow the official Linux service procedure to install/start it under the
dedicated account. For example, from the registered runner directory:

```bash
sudo ./svc.sh install RUNNER_SERVICE_USER
sudo ./svc.sh start
sudo ./svc.sh status
```

Replace `RUNNER_SERVICE_USER` with the approved local account. Make the CLI PATH,
proxy, and public CA environment available to this service. After configuration,
add the three [GHES repository secrets](installation.md#repository-secrets);
do not keep them in the runner account's shell profile.

References:
[adding self-hosted runners](https://docs.github.com/en/enterprise-server@3.21/actions/how-tos/manage-runners/self-hosted-runners/add-runners),
[running as a service](https://docs.github.com/en/enterprise-server@3.21/actions/how-tos/manage-runners/self-hosted-runners/configure-the-application),
[self-hosted runner security](https://docs.github.com/en/enterprise-server@3.21/actions/reference/security/secure-use).
