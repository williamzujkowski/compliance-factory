# OSCAL Content Directory

This directory contains OSCAL catalogs, profiles, and templates used by the Compliance Factory.

## Structure

```
content/
├── catalogs/           # NIST SP 800-53 and other control catalogs
│   ├── nist-sp800-53/  # NIST SP 800-53 Release 5.2.0 catalogs
│   ├── fedramp/        # FedRAMP overlays and baselines
│   └── custom/         # Organization-specific catalogs
├── profiles/           # Control profiles and baselines
│   ├── fedramp/        # FedRAMP Low/Moderate/High baselines  
│   ├── nist/           # NIST baseline profiles
│   └── custom/         # Organization-specific profiles
└── templates/          # Document templates for printables
    ├── ssp/            # System Security Plan templates
    ├── sap/            # Security Assessment Plan templates
    ├── sar/            # Security Assessment Report templates
    └── poam/           # Plan of Action & Milestones templates
```

## Version Management

All OSCAL content is version-pinned to ensure reproducible compliance checks:

- **OSCAL Models**: v1.1.3
- **NIST SP 800-53**: Release 5.2.0 
- **FedRAMP Baselines**: Latest from FedRAMP Automation Repository

## Content Sources

Content is sourced from authoritative repositories:

1. **NIST OSCAL Repository**: https://github.com/usnistgov/OSCAL
2. **FedRAMP Automation**: https://github.com/GSA/fedramp-automation
3. **NIST SP 800-53**: https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final

## Usage

The API service automatically loads content from this directory on startup.
Content files are read-only at runtime and should be updated through
proper change management processes.

## Content Validation

All OSCAL content in this directory must:
- Validate against OSCAL 1.1.3 schemas
- Pass FedRAMP constraint validation
- Include proper metadata and version information
- Use consistent identifier patterns

## Updating Content

To update OSCAL content:

1. Download new versions from authoritative sources
2. Validate with `task oscal-validate FILE=<path>`
3. Test with existing SSPs to ensure compatibility
4. Update version references in configuration
5. Document changes in ADRs (Architecture Decision Records)