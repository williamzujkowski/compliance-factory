# OSCAL Convert Command

Convert OSCAL $ARGUMENTS (xml↔json) and upload to S3; return object key and SHA-256.

## Usage

```bash
/convert workspace/ssp.xml json s3://bucket/converted/
/convert workspace/profile.json xml ./output/
```

## Process

1. **Validate**: Check source file is valid OSCAL
2. **Convert**: Use oscal-cli to convert between formats
3. **Verify**: Validate converted file maintains integrity  
4. **Upload**: Store converted file to S3-compatible storage
5. **Index**: Record conversion in database with metadata

## Output

Returns conversion result with:
- Source file path and format
- Converted file path and format
- S3 object key and URL
- SHA-256 checksums for both files
- Conversion timestamp and tool version

## Example Response

```json
{
  "conversion_id": "conv-12345",
  "source": {
    "path": "workspace/ssp.xml",
    "format": "xml",
    "sha256": "abc123..."
  },
  "converted": {
    "path": "converted/ssp.json", 
    "format": "json",
    "sha256": "def456...",
    "s3_key": "conversions/2025/01/04/ssp-abc123.json",
    "s3_url": "https://s3.amazonaws.com/bucket/conversions/2025/01/04/ssp-abc123.json"
  },
  "metadata": {
    "oscal_version": "1.1.3",
    "tool_version": "1.0.4",
    "converted_at": "2025-01-04T12:34:56Z"
  }
}
```