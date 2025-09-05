"""
Printable generation service for OSCAL documents.

Generates human-readable printable documents (PDF, HTML, DOCX) from OSCAL
documents using templates. Supports SSP, SAP, SAR, and POA&M generation.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Literal
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4
import tempfile
import asyncio
import subprocess

import structlog
from jinja2 import Environment, FileSystemLoader, Template, select_autoescape
from markdown import markdown
import weasyprint

logger = structlog.get_logger()


@dataclass
class PrintableGenerationResult:
    """Result of printable document generation."""
    success: bool
    document_type: str  # "ssp", "sap", "sar", "poam"
    output_format: str  # "pdf", "html", "docx"
    output_file_path: Optional[Path] = None
    file_size_bytes: Optional[int] = None
    generation_time_ms: Optional[int] = None
    issues: List[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.issues is None:
            self.issues = []


@dataclass
class TemplateContext:
    """Context data for template rendering."""
    document: Dict[str, Any]
    metadata: Dict[str, Any]
    controls: List[Dict[str, Any]] = None
    components: List[Dict[str, Any]] = None
    roles: List[Dict[str, Any]] = None
    parties: List[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.controls is None:
            self.controls = []
        if self.components is None:
            self.components = []
        if self.roles is None:
            self.roles = []
        if self.parties is None:
            self.parties = []


class OSCALTemplateProcessor:
    """
    Processes OSCAL documents into template-friendly data structures.
    
    Extracts and organizes OSCAL content for use in Jinja2 templates.
    """
    
    def __init__(self):
        self.logger = structlog.get_logger().bind(component="template_processor")
    
    def process_ssp(self, ssp_data: Dict[str, Any]) -> TemplateContext:
        """Process SSP document for template rendering."""
        ssp = ssp_data.get("system-security-plan", {})
        
        # Extract basic metadata
        metadata = ssp.get("metadata", {})
        system_chars = ssp.get("system-characteristics", {})
        
        # Process controls
        controls = self._extract_controls(ssp.get("control-implementation", {}))
        
        # Process components
        components = self._extract_components(ssp.get("system-implementation", {}))
        
        # Process roles and parties
        roles = metadata.get("roles", [])
        parties = metadata.get("parties", [])
        
        return TemplateContext(
            document=ssp,
            metadata={
                "title": metadata.get("title", "System Security Plan"),
                "version": metadata.get("version", "1.0"),
                "last_modified": metadata.get("last-modified"),
                "oscal_version": metadata.get("oscal-version", "1.1.3"),
                "system_name": system_chars.get("system-name", "Unknown System"),
                "system_id": system_chars.get("system-id", "unknown"),
                "authorization_boundary": self._extract_auth_boundary(system_chars),
                "system_description": system_chars.get("description", ""),
            },
            controls=controls,
            components=components,
            roles=roles,
            parties=parties
        )
    
    def _extract_controls(self, control_impl: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract control implementations with formatted data."""
        controls = []
        
        implemented_reqs = control_impl.get("implemented-requirements", [])
        
        for req in implemented_reqs:
            control_id = req.get("control-id", "").upper()
            
            # Combine all statements into implementation description
            statements = req.get("statements", [])
            implementation_description = []
            
            for stmt in statements:
                description = stmt.get("description", "")
                if description:
                    implementation_description.append(description)
            
            # Extract responsible roles
            responsible_roles = req.get("responsible-roles", [])
            role_ids = [role.get("role-id", "") for role in responsible_roles]
            
            controls.append({
                "control_id": control_id,
                "implementation_description": " ".join(implementation_description),
                "responsible_roles": role_ids,
                "control_origination": req.get("control-origination", []),
                "implementation_status": req.get("implementation-status", "implemented"),
                "remarks": req.get("remarks", ""),
                "uuid": req.get("uuid", str(uuid4())),
            })
        
        # Sort controls by ID
        controls.sort(key=lambda x: x["control_id"])
        
        return controls
    
    def _extract_components(self, system_impl: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract system components with formatted data."""
        components = []
        
        component_list = system_impl.get("components", [])
        
        for comp in component_list:
            components.append({
                "uuid": comp.get("uuid", str(uuid4())),
                "title": comp.get("title", "Unnamed Component"),
                "description": comp.get("description", ""),
                "type": comp.get("type", "system"),
                "status": comp.get("status", {}).get("state", "operational"),
                "responsible_roles": [
                    role.get("role-id", "") 
                    for role in comp.get("responsible-roles", [])
                ],
                "protocols": [
                    {
                        "name": proto.get("name", ""),
                        "title": proto.get("title", ""),
                        "port_ranges": [
                            {
                                "start": port.get("start"),
                                "end": port.get("end"),
                                "transport": port.get("transport", "TCP")
                            }
                            for port in proto.get("port-ranges", [])
                        ]
                    }
                    for proto in comp.get("protocols", [])
                ]
            })
        
        return components
    
    def _extract_auth_boundary(self, system_chars: Dict[str, Any]) -> Dict[str, Any]:
        """Extract authorization boundary information."""
        auth_boundary = system_chars.get("authorization-boundary", {})
        
        return {
            "description": auth_boundary.get("description", ""),
            "diagrams": [
                {
                    "uuid": diag.get("uuid", str(uuid4())),
                    "description": diag.get("description", ""),
                    "caption": diag.get("caption", ""),
                    "links": diag.get("links", [])
                }
                for diag in auth_boundary.get("diagrams", [])
            ]
        }


class PrintableTemplateEngine:
    """
    Template engine for generating printable documents.
    
    Manages Jinja2 templates and rendering for different document types
    and output formats.
    """
    
    def __init__(self, template_dir: Optional[Path] = None):
        self.logger = structlog.get_logger().bind(component="template_engine")
        
        # Set up template directory
        if template_dir is None:
            # Default to templates directory relative to this file
            template_dir = Path(__file__).parent.parent / "templates" / "printables"
        
        self.template_dir = template_dir
        self.template_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize Jinja2 environment
        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(['html', 'xml']),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        
        # Add custom filters
        self.env.filters['markdown'] = self._markdown_filter
        self.env.filters['format_date'] = self._format_date_filter
        self.env.filters['format_control_id'] = self._format_control_id_filter
        self.env.filters['format_list'] = self._format_list_filter
        
        # Ensure default templates exist
        self._ensure_default_templates()
    
    def render_html(self, document_type: str, context: TemplateContext) -> str:
        """Render document as HTML."""
        template_name = f"{document_type}.html"
        
        try:
            template = self.env.get_template(template_name)
            return template.render(
                metadata=context.metadata,
                document=context.document,
                controls=context.controls,
                components=context.components,
                roles=context.roles,
                parties=context.parties,
                generated_at=datetime.now(timezone.utc),
                generation_tool="OSCAL Compliance Factory"
            )
        except Exception as e:
            self.logger.error("HTML template rendering failed", template=template_name, error=str(e))
            raise
    
    def generate_pdf(self, html_content: str, output_path: Path) -> None:
        """Generate PDF from HTML content using WeasyPrint."""
        try:
            # Configure WeasyPrint with custom CSS for better PDF layout
            css_content = self._get_pdf_css()
            
            document = weasyprint.HTML(string=html_content)
            css = weasyprint.CSS(string=css_content)
            
            document.write_pdf(str(output_path), stylesheets=[css])
            
        except Exception as e:
            self.logger.error("PDF generation failed", output_path=str(output_path), error=str(e))
            raise
    
    def _markdown_filter(self, text: str) -> str:
        """Jinja2 filter to convert markdown to HTML."""
        if not text:
            return ""
        return markdown(text, extensions=['tables', 'fenced_code'])
    
    def _format_date_filter(self, date_str: str) -> str:
        """Jinja2 filter to format ISO date strings."""
        if not date_str:
            return "N/A"
        
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.strftime("%B %d, %Y")
        except Exception:
            return date_str
    
    def _format_control_id_filter(self, control_id: str) -> str:
        """Jinja2 filter to format control IDs consistently."""
        if not control_id:
            return ""
        return control_id.upper().strip()
    
    def _format_list_filter(self, items: List[Any], separator: str = ", ") -> str:
        """Jinja2 filter to format lists as strings."""
        if not items:
            return "None"
        return separator.join(str(item) for item in items)
    
    def _get_pdf_css(self) -> str:
        """Get CSS styles for PDF generation."""
        return """
        @page {
            size: Letter;
            margin: 1in;
            @bottom-center {
                content: "Page " counter(page) " of " counter(pages);
                font-size: 10pt;
                color: #666;
            }
        }
        
        body {
            font-family: 'Times New Roman', serif;
            font-size: 11pt;
            line-height: 1.4;
            color: #000;
        }
        
        h1, h2, h3, h4, h5, h6 {
            font-family: 'Arial', sans-serif;
            color: #1a365d;
            margin-top: 1.5em;
            margin-bottom: 0.5em;
            page-break-after: avoid;
        }
        
        h1 {
            font-size: 18pt;
            border-bottom: 2px solid #1a365d;
            padding-bottom: 0.2em;
        }
        
        h2 {
            font-size: 16pt;
        }
        
        h3 {
            font-size: 14pt;
        }
        
        .control {
            margin-bottom: 1.5em;
            page-break-inside: avoid;
        }
        
        .control-id {
            font-weight: bold;
            font-size: 12pt;
            color: #2d3748;
        }
        
        .implementation {
            margin-left: 0.5in;
            text-align: justify;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 1em 0;
            page-break-inside: avoid;
        }
        
        th, td {
            border: 1px solid #ccc;
            padding: 0.3em;
            text-align: left;
            vertical-align: top;
        }
        
        th {
            background-color: #f7fafc;
            font-weight: bold;
        }
        
        .metadata-table {
            width: 100%;
            margin-bottom: 2em;
        }
        
        .metadata-table th {
            width: 25%;
            background-color: #edf2f7;
        }
        
        .page-break {
            page-break-before: always;
        }
        
        .no-break {
            page-break-inside: avoid;
        }
        
        .toc {
            margin: 2em 0;
        }
        
        .toc-entry {
            margin-bottom: 0.5em;
        }
        
        .toc-entry a {
            text-decoration: none;
            color: #1a365d;
        }
        """
    
    def _ensure_default_templates(self) -> None:
        """Ensure default templates exist."""
        templates = {
            "ssp.html": self._get_ssp_template(),
            "sap.html": self._get_sap_template(),
            "sar.html": self._get_sar_template(),
            "poam.html": self._get_poam_template(),
        }
        
        for template_name, template_content in templates.items():
            template_path = self.template_dir / template_name
            if not template_path.exists():
                template_path.write_text(template_content, encoding='utf-8')
                self.logger.info("Created default template", template=template_name)
    
    def _get_ssp_template(self) -> str:
        """Get default SSP template."""
        return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ metadata.title }}</title>
</head>
<body>
    <div class="header">
        <h1>{{ metadata.title }}</h1>
        <div class="metadata-table">
            <table>
                <tr>
                    <th>System Name</th>
                    <td>{{ metadata.system_name }}</td>
                    <th>System ID</th>
                    <td>{{ metadata.system_id }}</td>
                </tr>
                <tr>
                    <th>Version</th>
                    <td>{{ metadata.version }}</td>
                    <th>Last Modified</th>
                    <td>{{ metadata.last_modified | format_date }}</td>
                </tr>
                <tr>
                    <th>OSCAL Version</th>
                    <td>{{ metadata.oscal_version }}</td>
                    <th>Generated</th>
                    <td>{{ generated_at | format_date }}</td>
                </tr>
            </table>
        </div>
    </div>

    <div class="page-break"></div>

    <h2>Table of Contents</h2>
    <div class="toc">
        <div class="toc-entry"><a href="#system-description">1. System Description</a></div>
        <div class="toc-entry"><a href="#authorization-boundary">2. Authorization Boundary</a></div>
        <div class="toc-entry"><a href="#system-components">3. System Components</a></div>
        <div class="toc-entry"><a href="#control-implementation">4. Control Implementation</a></div>
        <div class="toc-entry"><a href="#responsible-roles">5. Responsible Roles and Parties</a></div>
    </div>

    <div class="page-break"></div>

    <section id="system-description">
        <h2>1. System Description</h2>
        <div class="no-break">
            {% if metadata.system_description %}
                {{ metadata.system_description | markdown | safe }}
            {% else %}
                <p>No system description provided.</p>
            {% endif %}
        </div>
    </section>

    <section id="authorization-boundary">
        <h2>2. Authorization Boundary</h2>
        <div class="no-break">
            {% if metadata.authorization_boundary.description %}
                {{ metadata.authorization_boundary.description | markdown | safe }}
            {% else %}
                <p>No authorization boundary description provided.</p>
            {% endif %}
        </div>
    </section>

    <section id="system-components">
        <h2>3. System Components</h2>
        {% if components %}
            {% for component in components %}
                <div class="component no-break">
                    <h3>{{ component.title }}</h3>
                    <table>
                        <tr>
                            <th>Component Type</th>
                            <td>{{ component.type }}</td>
                        </tr>
                        <tr>
                            <th>Status</th>
                            <td>{{ component.status }}</td>
                        </tr>
                        <tr>
                            <th>Responsible Roles</th>
                            <td>{{ component.responsible_roles | format_list }}</td>
                        </tr>
                        <tr>
                            <th>Description</th>
                            <td>{{ component.description | markdown | safe }}</td>
                        </tr>
                    </table>
                </div>
            {% endfor %}
        {% else %}
            <p>No system components defined.</p>
        {% endif %}
    </section>

    <div class="page-break"></div>

    <section id="control-implementation">
        <h2>4. Control Implementation</h2>
        {% if controls %}
            {% for control in controls %}
                <div class="control">
                    <h3 class="control-id">{{ control.control_id | format_control_id }}</h3>
                    <div class="implementation">
                        {% if control.implementation_description %}
                            {{ control.implementation_description | markdown | safe }}
                        {% else %}
                            <p><em>No implementation description provided.</em></p>
                        {% endif %}
                        
                        {% if control.responsible_roles %}
                            <p><strong>Responsible Roles:</strong> {{ control.responsible_roles | format_list }}</p>
                        {% endif %}
                        
                        {% if control.control_origination %}
                            <p><strong>Control Origination:</strong> {{ control.control_origination | format_list }}</p>
                        {% endif %}
                        
                        <p><strong>Implementation Status:</strong> {{ control.implementation_status }}</p>
                    </div>
                </div>
            {% endfor %}
        {% else %}
            <p>No control implementations defined.</p>
        {% endif %}
    </section>

    <section id="responsible-roles">
        <h2>5. Responsible Roles and Parties</h2>
        
        <h3>Roles</h3>
        {% if roles %}
            <table>
                <thead>
                    <tr>
                        <th>Role ID</th>
                        <th>Title</th>
                        <th>Description</th>
                    </tr>
                </thead>
                <tbody>
                    {% for role in roles %}
                        <tr>
                            <td>{{ role.id }}</td>
                            <td>{{ role.title or 'N/A' }}</td>
                            <td>{{ role.description or 'N/A' }}</td>
                        </tr>
                    {% endfor %}
                </tbody>
            </table>
        {% else %}
            <p>No roles defined.</p>
        {% endif %}

        <h3>Parties</h3>
        {% if parties %}
            <table>
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Type</th>
                        <th>Email</th>
                        <th>Phone</th>
                    </tr>
                </thead>
                <tbody>
                    {% for party in parties %}
                        <tr>
                            <td>{{ party.name or 'N/A' }}</td>
                            <td>{{ party.type or 'N/A' }}</td>
                            <td>
                                {% for email in party.get('email-addresses', []) %}
                                    {{ email.addr }}{% if not loop.last %}, {% endif %}
                                {% endfor %}
                            </td>
                            <td>
                                {% for phone in party.get('telephone-numbers', []) %}
                                    {{ phone.number }}{% if not loop.last %}, {% endif %}
                                {% endfor %}
                            </td>
                        </tr>
                    {% endfor %}
                </tbody>
            </table>
        {% else %}
            <p>No parties defined.</p>
        {% endif %}
    </section>

    <footer>
        <p><em>Generated by {{ generation_tool }} on {{ generated_at | format_date }}</em></p>
    </footer>
</body>
</html>
        """
    
    def _get_sap_template(self) -> str:
        """Get default SAP template."""
        return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Security Assessment Plan</title>
</head>
<body>
    <h1>Security Assessment Plan</h1>
    <p>SAP template - To be implemented</p>
</body>
</html>
        """
    
    def _get_sar_template(self) -> str:
        """Get default SAR template."""
        return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Security Assessment Report</title>
</head>
<body>
    <h1>Security Assessment Report</h1>
    <p>SAR template - To be implemented</p>
</body>
</html>
        """
    
    def _get_poam_template(self) -> str:
        """Get default POA&M template."""
        return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Plan of Action and Milestones</title>
</head>
<body>
    <h1>Plan of Action and Milestones</h1>
    <p>POA&M template - To be implemented</p>
</body>
</html>
        """


class PrintableGenerationService:
    """
    Main printable generation service.
    
    Orchestrates the generation of printable documents from OSCAL content.
    """
    
    def __init__(self, template_dir: Optional[Path] = None):
        self.logger = structlog.get_logger().bind(component="printable_service")
        self.processor = OSCALTemplateProcessor()
        self.template_engine = PrintableTemplateEngine(template_dir)
    
    async def generate_printable(
        self,
        oscal_document: Dict[str, Any],
        output_format: Literal["pdf", "html"] = "pdf",
        output_path: Optional[Path] = None
    ) -> PrintableGenerationResult:
        """
        Generate a printable document from OSCAL content.
        
        Args:
            oscal_document: OSCAL document data
            output_format: Output format (pdf, html)
            output_path: Output file path (generated if not provided)
            
        Returns:
            Generation result with file path and metadata
        """
        start_time = datetime.now(timezone.utc)
        
        try:
            # Determine document type
            document_type = self._detect_document_type(oscal_document)
            
            if document_type == "unknown":
                return PrintableGenerationResult(
                    success=False,
                    document_type=document_type,
                    output_format=output_format,
                    issues=["Unable to determine OSCAL document type"]
                )
            
            # Currently only SSP is fully implemented
            if document_type != "ssp":
                return PrintableGenerationResult(
                    success=False,
                    document_type=document_type,
                    output_format=output_format,
                    issues=[f"Printable generation for {document_type} not yet implemented"]
                )
            
            # Process document into template context
            if document_type == "ssp":
                context = self.processor.process_ssp(oscal_document)
            else:
                # Placeholder for other document types
                context = TemplateContext(
                    document=oscal_document,
                    metadata={"title": f"Generated {document_type.upper()}"}
                )
            
            # Generate output file path if not provided
            if output_path is None:
                suffix = f".{output_format}"
                timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                filename = f"{document_type}_{timestamp}{suffix}"
                output_path = Path(tempfile.gettempdir()) / filename
            
            # Render HTML
            html_content = self.template_engine.render_html(document_type, context)
            
            if output_format == "html":
                # Save HTML directly
                output_path.write_text(html_content, encoding='utf-8')
            
            elif output_format == "pdf":
                # Generate PDF from HTML
                self.template_engine.generate_pdf(html_content, output_path)
            
            else:
                return PrintableGenerationResult(
                    success=False,
                    document_type=document_type,
                    output_format=output_format,
                    issues=[f"Output format '{output_format}' not supported"]
                )
            
            # Calculate file size
            file_size = output_path.stat().st_size if output_path.exists() else 0
            
            duration = datetime.now(timezone.utc) - start_time
            
            return PrintableGenerationResult(
                success=True,
                document_type=document_type,
                output_format=output_format,
                output_file_path=output_path,
                file_size_bytes=file_size,
                generation_time_ms=int(duration.total_seconds() * 1000),
                metadata={
                    "system_name": context.metadata.get("system_name", "Unknown"),
                    "document_title": context.metadata.get("title", "Generated Document"),
                    "controls_count": len(context.controls),
                    "components_count": len(context.components),
                    "template_version": "1.0",
                    "generated_at": start_time.isoformat(),
                }
            )
            
        except Exception as e:
            self.logger.error("Printable generation failed", error=str(e))
            duration = datetime.now(timezone.utc) - start_time
            
            return PrintableGenerationResult(
                success=False,
                document_type=self._detect_document_type(oscal_document),
                output_format=output_format,
                issues=[f"Generation failed: {str(e)}"],
                generation_time_ms=int(duration.total_seconds() * 1000)
            )
    
    def _detect_document_type(self, oscal_document: Dict[str, Any]) -> str:
        """Detect OSCAL document type from content."""
        if "system-security-plan" in oscal_document:
            return "ssp"
        elif "assessment-plan" in oscal_document:
            return "sap"
        elif "assessment-results" in oscal_document:
            return "sar"
        elif "plan-of-action-and-milestones" in oscal_document:
            return "poam"
        else:
            return "unknown"