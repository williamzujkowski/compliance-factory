# Document Ingest Command

Given a DOCX at $ARGUMENTS, call the importer to extract Markdown fragments into `services/api/app/mapping/<doc-id>/`.

Generate a mapping report with unresolved OSCAL fields and propose exact UI form controls to collect missing data.

## Usage

```bash
/ingest path/to/legacy-ssp.docx doc-id-001
/ingest workspace/system-plan.docx my-system-001
```

## Process

1. **Extract**: Use Pandoc to convert DOCX to structured Markdown
2. **Map**: Apply heuristics to identify OSCAL components
3. **Report**: Generate mapping report with unresolved fields
4. **Propose**: Suggest UI forms for manual data entry

## Output

The command creates:
- `services/api/app/mapping/<doc-id>/` directory
- Extracted Markdown fragments organized by OSCAL components
- `mapping-report.json` with unresolved fields
- `ui-forms-proposal.json` with suggested form controls

## Mapping Report Format

```json
{
  "document_id": "doc-id-001",
  "extraction_status": "partial",
  "mapped_fields": [...],
  "unresolved_fields": [
    {
      "oscal_path": "system-security-plan.system-implementation.leveraged-authorizations",
      "description": "Leveraged authorization details",
      "suggested_ui": "multi-select with authorization search",
      "required": true
    }
  ],
  "confidence_score": 0.85
}
```