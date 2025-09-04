# Printables Generation Command

Render SSP/SAP/SAR/POA&M using templates; save PDFs in /out and index in RDS.

## Usage

```bash
/printables workspace/ssp.json ssp ./output/
/printables workspace/assessment-plan.json sap s3://bucket/reports/
```

## Process

1. **Load**: Read OSCAL document and validate structure
2. **Template**: Apply appropriate FedRAMP-aligned template
3. **Render**: Generate PDF using template engine
4. **Quality Check**: Verify PDF completeness and formatting
5. **Store**: Save to specified location (local or S3)
6. **Index**: Record in database with metadata

## Document Types

- **SSP**: System Security Plan
- **SAP**: Security Assessment Plan  
- **SAR**: Security Assessment Report
- **POA&M**: Plan of Action & Milestones

## Template Features

- FedRAMP-compliant formatting
- Consistent branding and layout
- Automated table of contents
- Control implementation tables
- Risk assessment matrices
- Signature pages

## Output

Returns generation result:

```json
{
  "printable_id": "print-67890",
  "source": {
    "path": "workspace/ssp.json",
    "type": "system-security-plan"
  },
  "generated": {
    "path": "output/ssp-system-001.pdf",
    "pages": 245,
    "size_bytes": 2048576,
    "sha256": "xyz789..."
  },
  "template": {
    "name": "fedramp-ssp-template",
    "version": "2.0.1"
  },
  "metadata": {
    "generated_at": "2025-01-04T12:34:56Z",
    "system_name": "Example System",
    "baseline": "FedRAMP Moderate"
  }
}
```