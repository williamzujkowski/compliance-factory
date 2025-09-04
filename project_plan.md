# Compliance Factory — Project Plan
_Last updated: 2025-09-04_

## 0) Executive Summary
We’re shipping a local-first, containerized **OSCAL compliance factory** that:
- **Ingests** legacy SSPs (DOCX/PDF) → guided mapping → **OSCAL**.
- **Authors/edits** via Markdown + (optional) GUI; **OSCAL is the source of truth**.
- **Validates** with `oscal-cli` (schema) + FedRAMP constraints/registry.
- **Generates** SSP/SAP/SAR/POA&M printables.
- **Publishes** versioned artifacts to S3-compatible storage (MinIO locally; cloud.gov S3 in prod).
The stack is built with **Docker Compose**, **Taskfile**, **uv**, **Ruff**, and **Copier** templates.

---

## 1) Scope & Non-Goals
**In scope**
- Authoring + validation for OSCAL 1.1.3 models; SP 800-53 **Release 5.2.0** catalogs/profiles.
- FedRAMP 20x-aligned outputs using PMO templates/registry.
- Local infra parity: MinIO (S3), Postgres metadata, FastAPI API, optional React UI.
- Conversion & printables: `oscal-cli` + Pandoc flow; guided DOCX→OSCAL mapping.

**Non-goals (MVP)**
- Fully automated DOCX→OSCAL (won’t be robust; we do guided import).
- Full-blown workflow engine or enterprise RBAC (post-MVP).
- Direct agency submission tooling (stick to validated OSCAL + printables).

---

## 2) Architecture
### Services (docker-compose)
- **api**: FastAPI (Python 3.12) wrapping `oscal-cli`, Trestle, FedRAMP checks; `uv` env; `Ruff` lint.
- **db**: Postgres 16 (metadata: versions, evidence pointers, run logs).
- **minio**: S3-compatible object storage for artifacts/evidence (maps 1:1 to cloud.gov S3).
- **ui** (optional): React/Vite console editing per-control Markdown + diff/validation UX.
- **pandoc** (sidecar or baked into api image): DOCX↔MD extraction for importer wizard.

### Data Flow
DOCX/PDF → (pandoc extract) → mapping hints → Markdown fragments (Trestle) → assemble SSP → `oscal-cli validate` → FedRAMP constraints/registry checks → printables → S3 publish (+ checksums + manifest) → RDS index.

### Promotion to cloud.gov
- Replace MinIO with cloud.gov **S3 service broker**; read creds from `VCAP_SERVICES`.
- Concourse pipeline: _lint → assemble → validate → print → publish_.
- Secrets via **CredHub**; optional UAA for GUI auth.

---

## 3) Technology & Tooling
- **Languages**: Python 3.12 (FastAPI), TypeScript (React UI).
- **OSCAL tooling**: `oscal-cli` (NIST), IBM **Compliance Trestle** (+ FedRAMP plugin).
- **Dev tools**: **uv** (package & project manager), **Ruff** (linter/formatter), **Taskfile** (task runner).
- **Templates/Scaffolding**: **Copier** for reproducible project skeletons and variants.
- **Storage**: MinIO locally; S3 in cloud.gov.
- **CI/CD**: GitHub Actions locally; Concourse for cloud.gov.

> Version pins (as of 2025-09-04):  
> - **uv** latest stable `0.8.15`  
> - **Task** v3.44.x stable  
> - **Ruff** current stable (use Astral docs for rules & Rust LSP)  
> - **OSCAL models** v1.1.3; **SP 800-53 Release 5.2.0** catalogs/profiles

---

## 4) Standards Router (from your `standards` repo)
Use your product matrix and router to load standards bundles for this stack:

```

@load \[product\:api + CS\:python + TS\:pytest + SEC:\*]
@load \[product\:frontend-web + FE\:react]
@load \[CN\:containers + DOP\:concourse]
@load \[OBS\:monitoring + DOCS\:mkdocs]
@load \[NIST-IG\:base + LEG\:privacy]

```

- **CS/TS** give language conventions + pytest config, coverage, structure.
- **SEC:\*** expands to all security standards + **NIST-IG:base** controls tagging.
- **CN/DOP** apply container & pipeline standards; **OBS** adds logging/metrics.
- The router reads `config/product-matrix.yaml` at repo root and resolves the bundles.

---

## 5) Security & Compliance (authoritative content)
- **OSCAL 1.1.3** for models/validation; `oscal-cli` for convert/validate/profile resolve.
- **NIST SP 800-53 Release 5.2.0** catalogs/profiles (software update & patch integrity focus).
- **FedRAMP 20x** alignment: OSCAL-first artifacts, registry-constrained values, printable outputs for human review.

**Acceptance checks (MVP)**
- `oscal-cli validate` passes for SSP/SAP/SAR/POA&M.
- FedRAMP registry/constraints checks pass (block on invalid enums/IDs).
- Printables generated deterministically (SSP/SAP/SAR/POA&M).
- Artifacts stored with SHA-256 digest + manifest in S3; RDS index updated.

---

## 6) Project Structure
```

compliance-factory/
Taskfile.yml
docker-compose.yml
.env.example
services/
api/
pyproject.toml
uv.lock
ruff.toml
Dockerfile
app/
main.py
oscal\_ops.py          # wraps oscal-cli validate/convert
storage.py            # S3/MinIO I/O
mapping/word\_to\_oscal.py   # importer heuristics (guided)
ui/                        # optional React/Vite app
content/
catalogs/                  # NIST SP 800-53 r5.2.0 (resolved)
profiles/                  # FedRAMP baselines (resolved)
templates/                 # FedRAMP templates + print templates
docs/
ADRs/                      # decisions (version matrix, etc.)
.claude/
commands/                  # custom slash commands for Claude Code

````

---

## 7) Development Workflow
- **Install & run locally**
  ```bash
  cp .env.example .env
  task up            # build & start stack
  open http://localhost:8000/docs
````

* **Lint & format**
  `task lint` / `task fmt` (Ruff)
* **Validate an OSCAL file**
  `task oscal-validate FILE=/data/ssp.json`
* **Convert XML→JSON**
  `task oscal-convert-json IN=/data/ssp.xml OUT=/data/ssp.json`

**Git branching**

* `main` (release), `dev` (integration), feature branches with conventional commits.

**Pre-commit**

* ruff check/format, yaml/md lint, gitleaks (secrets), trivy (containers) on PR.

---

## 8) Testing Strategy & Quality Gates

* **pytest** with coverage target **≥85%** (raise to 90% post-MVP).
* **Ruff** rule sets: `E,F,B,UP,I` + `pyproject.toml` strict import order.
* **Security scans**: gitleaks (pre-commit), trivy (image CI), semgrep (app logic) optional.
* **Compliance gates**: `oscal-cli validate` + FedRAMP registry/constraints (fail-fast).
* **Performance**: API endpoints P95 < 200ms on local dev workloads.

---

## 9) CI/CD

**Local CI (GitHub Actions)**

* Job matrix: lint → unit tests → oscal-validate (sample) → trivy → build images → publish artifacts.

**cloud.gov promotion (Concourse)**

* Pipeline: *lint → assemble → validate → print → publish*. Secrets via **CredHub**. S3 via broker.

---

## 10) Import & Printables

* **Import (guided)**: Pandoc extracts structure; mapper aligns sections to OSCAL fields; human approves in UI; Trestle assembles.
* **Printables**: render SSP/SAP/SAR/POA\&M from OSCAL for reviewers; keep deterministic templates.

---

## 11) Roadmap

* **MVP (2–3 weeks)**: API + validation/convert + MinIO + Taskfile + Copier template.
* **Beta**: FedRAMP constraints integration, importer wizard, printables, sample baselines.
* **GA**: GUI hardening, audit trails, profile resolution UX, Concourse pipeline, cloud.gov manifest.

---

## 12) Copier Template (distribution)

* Publish `gh:your-org/copier-compliance-factory` with variables:

  * `project_name`, `org_slug`, `include_ui` (bool), `include_pandoc` (bool), `default_bucket`.
* End-user flow:

  ```bash
  uv tool install copier
  copier copy gh:your-org/copier-compliance-factory my-compliance-factory
  ```

---

## 13) Quick Start (commands)

```bash
# Start stack
task up

# API docs
open http://localhost:8000/docs

# Validate sample SSP
task oscal-validate FILE=/workspace/samples/ssp.json

# Generate printables (when templates wired)
task printables FILE=/workspace/samples/ssp.json OUT=/workspace/out/
```

---

## 14) References (pin these in README/ADRs)

* Claude Code + CLAUDE.md best practices; CLI & workflows; memory; output styles.
* OSCAL 1.1.3 release; model reference; oscal-cli usage.
* NIST SP 800-53 **Release 5.2.0** news/planning note; changes summary.
* FedRAMP 20x overview/pilot; FedRAMP automation repo/templates/registry.
* uv docs & latest release; Taskfile docs; Ruff docs.
* Your **standards** repo (router + product matrix).

````

---
