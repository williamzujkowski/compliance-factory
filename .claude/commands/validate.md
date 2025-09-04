# OSCAL Validate Command

Run `task oscal-validate FILE=$ARGUMENTS` to validate an OSCAL file using oscal-cli.

If the Taskfile lacks this target, modify it to include OSCAL validation.

The command will:
1. Validate the file against OSCAL 1.1.3 schemas
2. Check FedRAMP constraints if applicable  
3. Report validation errors with JSONPath/XPath locations
4. Provide suggested fixes for common issues

## Usage

```bash
/validate path/to/ssp.json
/validate workspace/system-security-plan.xml
```

## Output

- Shows validation status (PASS/FAIL)
- Lists all validation errors with precise locations
- Suggests fixes for schema violations
- Reports FedRAMP baseline compliance issues