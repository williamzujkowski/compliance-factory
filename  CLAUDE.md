# CLAUDE.md — Compliance Factory Router & Working Agreement

> This file instructs Claude Code (CLI) how to behave in this repo. Keep it **concise** and **actionable**. Update as the project evolves.

## 1) Mission & Context
- Build a local-first, containerized **OSCAL compliance factory** that ingests legacy SSPs, authors/edits in Markdown/GUI, validates with `oscal-cli` + FedRAMP constraints, generates printables, and publishes artifacts to S3-compatible storage. Target **cloud.gov** promotion with Concourse.
- **Source of truth** is **OSCAL** (1.1.3). Printables exist only for human review.

## 2) Standards Router (load required bundles)
Use my standards repository router + product matrix:

````

@load \[product\:api + CS\:python + TS\:pytest + SEC:\*]
@load \[product\:frontend-web + FE\:react]
@load \[CN\:containers + DOP\:concourse]
@load \[OBS\:monitoring + DOCS\:mkdocs]
@load \[NIST-IG\:base + LEG\:privacy]

```

When you propose code/changes, **explicitly reference** the loaded standards (filenames/sections) and keep outputs compliant.

## 3) Project Facts (single source of truth)
- **Models**: OSCAL **v1.1.3**; NIST SP 800-53 **Release 5.2.0** catalogs/profiles.
- **FedRAMP**: 20x-aligned outputs; use PMO templates/registry; generate printables.
- **Services**: `api` (FastAPI), `db` (Postgres), `minio` (S3), optional `ui` (React).
- **Tooling**: `uv` (Python env), `Ruff` (lint/format), `Task` (task runner), `Copier` (template).
- **Local endpoints**: API `http://localhost:8000`, MinIO console `http://localhost:9001`.

## Commands (Development Workflow)
Since no Taskfile.yml exists yet, these are the planned commands:
- `task up` - Start the Docker Compose stack
- `task down` - Stop all services  
- `task lint` - Run Ruff linting on Python code
- `task fmt` - Format Python code with Ruff
- `task test` - Run pytest test suite
- `task oscal-validate FILE=<path>` - Validate OSCAL file with oscal-cli
- `task oscal-convert-json IN=<xml> OUT=<json>` - Convert OSCAL XML to JSON
- `task printables FILE=<oscal> OUT=<dir>` - Generate PDF reports

## 4) What to Do (Claude)
When asked to _implement_:
1. **Scaffold** code and config matching the standards router bundles.
2. **Keep diffs small**; name files exactly as referenced in `project_plan.md`.
3. **Add tasks** to `Taskfile.yml` so humans can run the thing in one command.
4. **Write tests** (pytest) with coverage annotations and fixtures.
5. **Enforce gates**: add CI jobs (lint, tests, oscal-validate, trivy).
6. **Document** new commands in README/Taskfile comments.

When asked to _ingest_ a Word/PDF SSP:
- Create `services/api/app/mapping/<doc-id>/` with extracted MD fragments.
- Emit a **mapping report** listing fields that need SME input; block merge until resolved.

## 5) Do / Don’t
- **Do** keep `OSCAL` the source of truth; UI edits must write Markdown/Trestle and re-assemble.
- **Do** fail fast on FedRAMP registry/constraints violations.
- **Don’t** add non-deterministic print formatting; templates must render reproducibly.
- **Don’t** hardcode secrets; read from `.env` (local) and `VCAP_SERVICES` (cloud.gov).

## 6) Repo Map (Claude's compass)
**Current State**: Repository is in planning phase - no implementation files exist yet.

**Planned Structure**:
- `services/api/app/*.py` — API endpoints, `oscal-cli` wrappers, S3 I/O.
- `services/ui/` — Optional React frontend (if implemented)
- `content/` — catalogs/profiles/templates (pin to specific SHAs/versions).
- `Taskfile.yml` — canonical dev workflow (not created yet).
- `docker-compose.yml` — Service orchestration (not created yet).
- `.claude/commands/` — custom slash commands for frequent tasks.
- `docs/ADRs/` — decisions (versions, printables policy, profile lineage).

**Existing Files**:
- `project_plan.md` — Detailed technical specifications and architecture
- `agent.md` — Cross-platform LLM agent configuration template  
- ` CLAUDE.md` — This guidance file

## 7) Quality Gates (auto-enforce)
- **Ruff**: error on `E,F,B,UP,I`; line length `100`.
- **Tests**: coverage ≥ **85%** (raise post-MVP).
- **Compliance**: `oscal-cli validate` must pass; FedRAMP constraints/registry must pass.
- **Containers**: trivy **HIGH/CRITICAL = 0** allowed.

## 8) Slash Commands (project-scoped)
Create in `.claude/commands/`:

- `validate.md`  
  _“Run `oscal-cli validate` on $ARGUMENTS; show failing paths and suggested fixes; update Taskfile with a dedicated target if missing.”_
- `convert.md`  
  _“Convert OSCAL $ARGUMENTS (xml↔json) and upload to S3; return object key and SHA-256.”_
- `ingest.md`  
  _“Given a DOCX at $ARGUMENTS, generate Markdown fragments + a mapping report; list unresolved fields and propose UI forms.”_
- `printables.md`  
  _“Render SSP/SAP/SAR/POA&M using templates; save PDFs in /out and index in RDS.”_

## 9) Claude Code Settings Hints
- Prefer **project memory** for style & workflow; keep CLAUDE.md concise.
- If CLAUDE.md grows, split into subordinate docs and reference them.
- Use **Output Styles** only when we explicitly need to override defaults.

## 10) Security Posture (what to enforce in code reviews)
- Secrets only via env/`VCAP_SERVICES`; no credentials in repo.
- S3 objects written with content hash + immutability flags (where supported).
- Audit trail: each publish emits a signed manifest (artifact list + checksums + tool versions).

## 11) “Ask Me” Triggers
- If a DOCX section lacks a deterministic mapping to OSCAL, produce a **mapping question list** instead of guessing.
- If content drifts from pinned OSCAL/SP800-53 versions, propose an ADR and version bump PR.

## 12) Done Criteria (MVP)
- `task up` brings the stack online.
- `/healthz` returns ok; `/validate` & `/convert` work on sample SSP.
- One end-to-end run: Markdown → OSCAL → validate → printables → S3 publish with manifest.
```

---

## Optional but useful

* **.claude/commands/** skeletons (copy these into your repo):

```markdown
# .claude/commands/validate.md
Run `task oscal-validate FILE=$ARGUMENTS`. If Taskfile lacks this target, modify it. Summarize failures and point to exact JSONPath/XPath with suggested diffs.
```

```markdown
# .claude/commands/ingest.md
Given a DOCX at $ARGUMENTS, call the importer to extract Markdown fragments into `services/api/app/mapping/<doc-id>/`. Generate a mapping report with unresolved OSCAL fields and propose exact UI form controls to collect missing data.
```

---

## How to use this with Claude CLI (TL;DR)

1. Drop **both files** at repo root.
2. Ensure your **standards** repo is referenced in the plan and available to Claude (you can add it as a Project source or link it).
3. In your terminal, run Claude Code in the repo and paste your **Universal Project Kickstart Prompt** with the **project\_plan.md** content.
4. Use the provided slash commands or ask Claude to scaffold the Docker/Taskfile/Trestle bits per the plan.

---

## Citations (key sources & versions)

* **CLAUDE.md best practices & behavior**

  * Anthropic engineering: *Create `CLAUDE.md` files* and what to include. ([Anthropic][1])
  * Claude Code docs: CLI reference; common workflows; settings; memory; output styles vs CLAUDE.md; slash commands. ([Anthropic][2])
  * Community patterns on structuring and keeping CLAUDE.md lean/hierarchical. ([maxitect.blog][3], [Sid Bharath][4])

* **OSCAL / NIST / FedRAMP**

  * OSCAL 1.1.3 release + model references. ([GitHub][5], [NIST Pages][6])
  * NIST SP 800-53 **Release 5.2.0** announcement & planning note; summary of changes (software update/patch integrity). ([NIST Computer Security Resource Center][7])
  * FedRAMP 20x overview/pilot and FedRAMP automation repo (templates/registry). ([fedramp.gov][8], [demo.fedramp.gov][9], [GitHub][10])

* **Tooling (versions & docs)**

  * **uv** docs + latest release info. ([Astral Docs][11], [GitHub][12])
  * **Taskfile** docs (modern task runner). ([Task][13])
  * **Ruff** docs. ([Astral Docs][14])
  * **MinIO** container/compose docs. ([AIStor Object Store Documentation][15])

* **Your standards repo**

  * Router, product matrix, NIST implementation guide & examples live here. ([GitHub][16])

---

If you want, I can also spit out a minimal **Taskfile.yml**, **docker-compose.yml**, and a Copier template skeleton aligned to the plan — ready for Claude to start generating code from.

[1]: https://www.anthropic.com/engineering/claude-code-best-practices "Claude Code: Best practices for agentic coding"
[2]: https://docs.anthropic.com/en/docs/claude-code/cli-reference "CLI reference"
[3]: https://www.maxitect.blog/posts/maximising-claude-code-building-an-effective-claudemd "Maximising Claude Code: Building an Effective CLAUDE.md"
[4]: https://www.siddharthbharath.com/claude-code-the-complete-guide/ "Cooking with Claude Code: The Complete Guide"
[5]: https://github.com/usnistgov/OSCAL/releases "Releases · usnistgov/OSCAL"
[6]: https://pages.nist.gov/OSCAL-Reference/models/v1.1.3/complete/ "System Security Plan Model v1.1.3 Reference - NIST Pages"
[7]: https://csrc.nist.gov/News/2025/nist-releases-revision-to-sp-800-53-controls "NIST Releases Revision to SP 800-53 Controls | CSRC"
[8]: https://www.fedramp.gov/ "FedRAMP | FedRAMP.gov"
[9]: https://demo.fedramp.gov/20x/phase-one/ "FedRAMP 20x - Phase One Pilot"
[10]: https://github.com/GSA/fedramp-automation "GSA/fedramp-automation"
[11]: https://docs.astral.sh/uv/ "uv - Astral Docs"
[12]: https://github.com/astral-sh/uv?tab=readme-ov-file&utm_source=chatgpt.com "GitHub - astral-sh/uv"
[13]: https://taskfile.dev/ "Taskfile.dev"
[14]: https://docs.astral.sh/ruff/ "Ruff - Astral Docs"
[15]: https://docs.min.io/community/minio-object-store/operations/deployments/baremetal-deploy-minio-as-a-container.html "Deploy MinIO as a Container — MinIO Object Storage (AGPLv3)"
[16]: https://github.com/williamzujkowski/standards "GitHub - williamzujkowski/standards: LLM Software Development Standards Start any project right in 30 seconds. Battle-tested standards from real production systems."
