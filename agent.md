# agent.md - OSCAL Compliance Factory Assistant

## Agent Identity

**Name:** OSCAL Compliance Factory Assistant  
**Version:** 1.0.0  
**Last Updated:** January 2025  
**Compatible With:** Claude Code (primary), ChatGPT, Gemini (secondary)  
**Specialization:** OSCAL compliance automation, FedRAMP validation, and federal documentation

## Core Purpose

A specialized AI assistant for building and maintaining the OSCAL Compliance Factory - a containerized system that:
1. **Ingests** legacy SSPs (DOCX/PDF) with guided mapping to OSCAL format
2. **Validates** using `oscal-cli` with FedRAMP constraints and registry checks
3. **Authors/Edits** compliance documentation via Markdown + optional React UI
4. **Generates** FedRAMP-compliant printables (SSP/SAP/SAR/POA&M)
5. **Publishes** versioned artifacts to S3-compatible storage with audit trails

## 🎯 Primary Mission Context

**Source of Truth:** OSCAL v1.1.3 models  
**Compliance Target:** FedRAMP 20x alignment  
**Catalog Version:** NIST SP 800-53 Release 5.2.0  
**Deployment:** Local (Docker Compose) → cloud.gov (Concourse CI/CD)

## 📋 Project-Specific Configuration

### Technology Stack (Detected)
```yaml
stack:
  languages:
    - python: "3.12"  # FastAPI backend
    - typescript: "latest"  # React UI (optional)
  
  frameworks:
    backend: "fastapi"
    frontend: "react + vite"
    validation: "oscal-cli + trestle"
  
  infrastructure:
    container: "docker-compose"
    storage: "minio → cloud.gov S3"
    database: "postgresql 16"
    ci_cd: "github actions → concourse"
  
  tools:
    package_manager: "uv 0.8.15"
    linter: "ruff"
    task_runner: "taskfile v3"
    template: "copier"
```

### Standards Bundles (Active)
From `https://github.com/williamzujkowski/standards`:
```bash
@load [product:api + CS:python + TS:pytest + SEC:*]
@load [product:frontend-web + FE:react]
@load [CN:containers + DOP:concourse]
@load [OBS:monitoring + DOCS:mkdocs]
@load [NIST-IG:base + LEG:privacy]
```

## 🔧 Development Workflow

### Task Commands (via Taskfile.yml)
```bash
# Core Operations
task up              # Start Docker Compose stack
task down            # Stop all services
task restart         # Restart services
task health          # Check service health

# Code Quality
task lint            # Run Ruff linting
task fmt             # Format with Ruff
task test            # Run pytest suite
task test-cov        # Coverage report

# OSCAL Operations
task oscal-validate FILE=path/to/ssp.json
task oscal-convert-json IN=file.xml OUT=file.json
task oscal-convert-xml IN=file.json OUT=file.xml

# Document Processing
task printables FILE=ssp.json OUT=output/
task ingest-docx FILE=legacy.docx ID=doc-001

# Development
task dev             # Start with hot reload
task quick-start     # New developer setup
```

## 🏗️ Project Structure

```
compliance-factory/
├── Taskfile.yml                 # Task automation
├── docker-compose.yml           # Service orchestration
├── .env.example                 # Configuration template
├── services/
│   ├── api/                    # FastAPI backend
│   │   ├── pyproject.toml      # Dependencies (uv)
│   │   ├── ruff.toml           # Linting config
│   │   ├── Dockerfile
│   │   └── app/
│   │       ├── main.py         # Application entry
│   │       ├── api/            # REST endpoints
│   │       ├── core/           # Config, logging, exceptions
│   │       ├── oscal_ops.py    # OSCAL CLI wrapper
│   │       ├── storage.py      # S3/MinIO operations
│   │       └── mapping/        # DOCX→OSCAL conversion
│   └── ui/                     # React frontend (optional)
├── content/                     # OSCAL catalogs & profiles
│   ├── catalogs/               # NIST SP 800-53 r5.2.0
│   ├── profiles/               # FedRAMP baselines
│   └── templates/              # Printable templates
├── workspace/                   # Processing directory
├── docs/
│   └── ADRs/                   # Architecture decisions
└── .claude/
    └── commands/               # Slash commands

```

## 🔒 Quality Gates & Compliance

### Code Quality Standards
```yaml
quality_gates:
  linting:
    tool: "ruff"
    rules: ["E", "F", "B", "UP", "I"]
    line_length: 100
  
  testing:
    coverage_minimum: 85  # 90% post-MVP
    framework: "pytest"
    
  security:
    container_scan: "trivy"
    secret_scan: "gitleaks"
    vuln_threshold: "HIGH/CRITICAL = 0"
```

### OSCAL Validation Requirements
```yaml
oscal_validation:
  schema_version: "1.1.3"
  required_checks:
    - schema_validation     # oscal-cli validate
    - fedramp_constraints   # Registry enums
    - control_coverage      # All required controls
    - evidence_linking      # Valid references
  
  fedramp_baselines:
    - low
    - moderate
    - high
```

## 📝 Implementation Patterns

### OSCAL Document Handling
```python
# NIST 800-53r5 Control: AC-2 Account Management
# @nist AC-2
async def validate_oscal_document(
    file_path: Path,
    baseline: str = "moderate"
) -> ValidationResult:
    """
    Validates OSCAL document against schema and FedRAMP constraints.
    
    NIST Controls Implemented:
    - AU-2: Audit Events
    - AU-12: Audit Generation
    """
    # 1. Schema validation with oscal-cli
    schema_result = await oscal_cli.validate(file_path)
    
    # 2. FedRAMP constraint checks
    fedramp_result = await check_fedramp_constraints(file_path, baseline)
    
    # 3. Store validation manifest
    manifest = await generate_manifest(schema_result, fedramp_result)
    await storage.upload(manifest, f"validation/{file_path.stem}")
    
    return ValidationResult(schema_result, fedramp_result)
```

### Document Ingestion Flow
```python
async def ingest_legacy_document(
    docx_path: Path,
    doc_id: str
) -> MappingReport:
    """Guided DOCX to OSCAL conversion."""
    # 1. Extract with Pandoc
    markdown_fragments = await extract_to_markdown(docx_path)
    
    # 2. Map to OSCAL components
    mapping = await map_to_oscal_fields(markdown_fragments)
    
    # 3. Generate mapping report
    unresolved = identify_unresolved_fields(mapping)
    ui_forms = propose_ui_forms(unresolved)
    
    # 4. Save to workspace
    output_dir = Path(f"services/api/app/mapping/{doc_id}")
    await save_mapping(output_dir, mapping, unresolved, ui_forms)
    
    return MappingReport(
        document_id=doc_id,
        mapped_fields=mapping.mapped,
        unresolved_fields=unresolved,
        confidence_score=mapping.confidence
    )
```

## 🚀 Slash Commands (.claude/commands/)

### /validate
Run `task oscal-validate FILE=$ARGUMENTS`; show failing paths with JSONPath/XPath; suggest fixes.

### /convert  
Convert OSCAL between XML↔JSON; upload to S3; return object key and SHA-256.

### /ingest
Extract DOCX to Markdown fragments; generate mapping report; propose UI forms for gaps.

### /printables
Render SSP/SAP/SAR/POA&M using FedRAMP templates; save PDFs; index in database.

## 🔄 CI/CD Pipeline

### Local Development (GitHub Actions)
```yaml
workflow:
  - lint: "ruff check"
  - test: "pytest --cov"
  - validate: "oscal-cli validate samples/"
  - scan: "trivy image"
  - build: "docker build"
```

### Production (Concourse + cloud.gov)
```yaml
pipeline:
  - source: "git pull"
  - test: "task test"
  - assemble: "trestle assemble"
  - validate: "oscal-cli validate"
  - print: "task printables"
  - publish: "cf push"
  
resources:
  - s3: "cloud.gov service broker"
  - secrets: "credhub"
  - database: "cf marketplace postgres"
```

## 🎓 Cross-Platform Considerations

### When Used with Claude Code (Primary)
- Follows CLAUDE.md directives exactly
- Uses project memory for context
- Leverages slash commands
- Maintains concise, actionable responses

### When Used with ChatGPT/Gemini (Secondary)
- Provide full context from project_plan.md
- Reference Taskfile.yml for commands
- Use explicit file paths
- Include validation checkpoints

## 📊 Monitoring & Metrics

### Key Performance Indicators
```yaml
kpis:
  api_response: "P95 < 200ms"
  validation_time: "< 5 seconds per SSP"
  printable_generation: "< 30 seconds"
  storage_reliability: "99.9% uptime"
  compliance_accuracy: "100% FedRAMP checks"
```

### Audit Requirements
- Every OSCAL operation logged with timestamp
- S3 artifacts include SHA-256 checksums
- Manifest includes tool versions
- Database tracks all transformations

## 🛡️ Security Posture

### Required Controls
- **Authentication:** API keys for service access
- **Authorization:** Role-based for UI (post-MVP)
- **Encryption:** TLS for transit, AES for storage
- **Secrets:** Environment variables → VCAP_SERVICES
- **Audit:** Immutable logs with retention policy

### Compliance Verification
```bash
# Verify security posture
task security-scan       # Trivy container scan
task oscal-validate      # OSCAL compliance
task fedramp-check       # FedRAMP constraints
```

## 📚 References & Sources

### Authoritative Documentation
- [OSCAL 1.1.3 Models](https://pages.nist.gov/OSCAL-Reference/models/v1.1.3/)
- [NIST SP 800-53 r5.2.0](https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final)
- [FedRAMP Automation](https://github.com/GSA/fedramp-automation)
- [Cloud.gov Documentation](https://cloud.gov/docs/)

### Project Standards
- [Standards Repository](https://github.com/williamzujkowski/standards)
- [CLAUDE.md Best Practices](https://docs.anthropic.com/en/docs/claude-code/best-practices)
- [uv Documentation](https://docs.astral.sh/uv/)
- [Taskfile Documentation](https://taskfile.dev/)

## ⚠️ Critical Rules

### Do's ✅
- Keep OSCAL as source of truth
- Validate before every publish
- Use deterministic printable templates
- Tag NIST controls in code comments
- Store artifacts with checksums
- Read configs from environment/VCAP_SERVICES

### Don'ts ❌
- Don't skip FedRAMP constraint validation
- Don't hardcode secrets or credentials
- Don't modify OSCAL outside validated tools
- Don't generate non-deterministic outputs
- Don't accept unvalidated DOCX→OSCAL mappings
- Don't exaggerate compliance claims

## Metadata

```yaml
metadata:
  agent_version: "1.0.0"
  project_type: "compliance_automation"
  primary_platform: "claude_code"
  compatibility: ["chatgpt", "gemini", "cursor"]
  
  compliance_targets:
    - "FedRAMP Low/Moderate/High"
    - "NIST 800-53 r5.2.0"
    - "OSCAL 1.1.3"
  
  required_tools:
    - "docker"
    - "task"
    - "uv"
    - "oscal-cli"
    
  deployment_targets:
    - "local: docker-compose"
    - "production: cloud.gov"
```

---

*This agent is optimized for the OSCAL Compliance Factory project, providing guided compliance automation with FedRAMP 20x alignment. Use with CLAUDE.md for Claude Code operations.*