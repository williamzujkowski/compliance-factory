"""
FedRAMP constraint validation service.

Provides validation of OSCAL documents against FedRAMP 20x requirements
including baseline-specific constraints, control implementation requirements,
and compliance validation beyond basic OSCAL schema validation.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from datetime import datetime, timezone
import re

import structlog

logger = structlog.get_logger()


@dataclass
class FedRAMPValidationIssue:
    """Individual FedRAMP validation issue."""
    severity: str  # "error", "warning", "info"
    code: str  # FedRAMP-specific error code
    message: str
    location: Optional[str] = None  # JSONPath location
    requirement: Optional[str] = None  # FedRAMP requirement reference
    baseline: Optional[str] = None  # low, moderate, high
    suggested_fix: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


@dataclass 
class FedRAMPValidationResult:
    """Result of FedRAMP constraint validation."""
    is_compliant: bool
    baseline: str
    document_type: str
    issues: List[FedRAMPValidationIssue]
    validation_time_ms: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None
    
    @property
    def error_count(self) -> int:
        return len([i for i in self.issues if i.severity == "error"])
    
    @property
    def warning_count(self) -> int:
        return len([i for i in self.issues if i.severity == "warning"])


class FedRAMPConstraintValidator:
    """
    FedRAMP 20x constraint validator.
    
    Validates OSCAL documents against FedRAMP-specific requirements
    that go beyond the base OSCAL schema validation.
    """
    
    def __init__(self):
        self.logger = structlog.get_logger().bind(component="fedramp_validator")
        
        # Load FedRAMP baseline mappings and requirements
        self._load_baseline_requirements()
        self._load_control_mappings()
    
    def _load_baseline_requirements(self) -> None:
        """Load FedRAMP baseline requirements and constraints."""
        # These would typically be loaded from external files or registries
        self.baseline_requirements = {
            "low": {
                "required_controls": [
                    "ac-1", "ac-2", "ac-3", "ac-7", "ac-8", "ac-14", "ac-17", "ac-18", "ac-19", "ac-20", "ac-22",
                    "at-1", "at-2", "at-3", "at-4",
                    "au-1", "au-2", "au-3", "au-4", "au-5", "au-6", "au-8", "au-9", "au-11", "au-12",
                    "ca-1", "ca-2", "ca-3", "ca-5", "ca-6", "ca-7", "ca-9",
                    "cm-1", "cm-2", "cm-4", "cm-5", "cm-6", "cm-7", "cm-8", "cm-10", "cm-11",
                    "cp-1", "cp-2", "cp-3", "cp-4", "cp-9", "cp-10",
                    "ia-1", "ia-2", "ia-4", "ia-5", "ia-6", "ia-7", "ia-8",
                    "ir-1", "ir-2", "ir-4", "ir-5", "ir-6", "ir-7", "ir-8",
                    "ma-1", "ma-2", "ma-4", "ma-5",
                    "mp-1", "mp-2", "mp-6", "mp-7",
                    "pe-1", "pe-2", "pe-3", "pe-6", "pe-8", "pe-12", "pe-13", "pe-14", "pe-15", "pe-16",
                    "pl-1", "pl-2", "pl-4",
                    "ps-1", "ps-2", "ps-3", "ps-4", "ps-5", "ps-6", "ps-7", "ps-8",
                    "ra-1", "ra-2", "ra-3", "ra-5",
                    "sa-1", "sa-2", "sa-3", "sa-4", "sa-5", "sa-9",
                    "sc-1", "sc-2", "sc-4", "sc-5", "sc-7", "sc-12", "sc-13", "sc-15", "sc-20", "sc-21", "sc-22",
                    "si-1", "si-2", "si-3", "si-4", "si-5", "si-12"
                ],
                "min_controls": 108,
                "required_metadata": ["system_name", "system_id", "authorization_boundary"],
            },
            "moderate": {
                "required_controls": [
                    # All LOW controls plus additional MODERATE controls
                    "ac-1", "ac-2", "ac-3", "ac-4", "ac-5", "ac-6", "ac-7", "ac-8", "ac-11", "ac-12", 
                    "ac-14", "ac-17", "ac-18", "ac-19", "ac-20", "ac-22",
                    "at-1", "at-2", "at-3", "at-4",
                    "au-1", "au-2", "au-3", "au-4", "au-5", "au-6", "au-7", "au-8", "au-9", "au-10", 
                    "au-11", "au-12",
                    "ca-1", "ca-2", "ca-3", "ca-5", "ca-6", "ca-7", "ca-8", "ca-9",
                    "cm-1", "cm-2", "cm-3", "cm-4", "cm-5", "cm-6", "cm-7", "cm-8", "cm-9", "cm-10", 
                    "cm-11",
                    "cp-1", "cp-2", "cp-3", "cp-4", "cp-6", "cp-7", "cp-8", "cp-9", "cp-10",
                    "ia-1", "ia-2", "ia-3", "ia-4", "ia-5", "ia-6", "ia-7", "ia-8", "ia-11",
                    "ir-1", "ir-2", "ir-3", "ir-4", "ir-5", "ir-6", "ir-7", "ir-8",
                    "ma-1", "ma-2", "ma-3", "ma-4", "ma-5", "ma-6",
                    "mp-1", "mp-2", "mp-3", "mp-4", "mp-5", "mp-6", "mp-7",
                    "pe-1", "pe-2", "pe-3", "pe-4", "pe-5", "pe-6", "pe-8", "pe-9", "pe-10", 
                    "pe-11", "pe-12", "pe-13", "pe-14", "pe-15", "pe-16", "pe-17",
                    "pl-1", "pl-2", "pl-4", "pl-8",
                    "ps-1", "ps-2", "ps-3", "ps-4", "ps-5", "ps-6", "ps-7", "ps-8",
                    "ra-1", "ra-2", "ra-3", "ra-5",
                    "sa-1", "sa-2", "sa-3", "sa-4", "sa-5", "sa-8", "sa-9", "sa-10",
                    "sc-1", "sc-2", "sc-3", "sc-4", "sc-5", "sc-7", "sc-8", "sc-10", "sc-11", 
                    "sc-12", "sc-13", "sc-15", "sc-17", "sc-18", "sc-19", "sc-20", "sc-21", "sc-22", "sc-23",
                    "si-1", "si-2", "si-3", "si-4", "si-5", "si-6", "si-7", "si-8", "si-10", "si-11", "si-12"
                ],
                "min_controls": 325,
                "required_metadata": ["system_name", "system_id", "authorization_boundary", "data_types"],
            },
            "high": {
                "required_controls": [
                    # All MODERATE controls plus additional HIGH controls
                    # This would be the full set - truncated for brevity
                ],
                "min_controls": 421,
                "required_metadata": [
                    "system_name", "system_id", "authorization_boundary", "data_types", 
                    "system_categorization", "high_water_mark"
                ],
            }
        }
    
    def _load_control_mappings(self) -> None:
        """Load NIST 800-53 to FedRAMP control mappings."""
        self.control_mappings = {
            # Mapping from NIST control IDs to FedRAMP requirements
            "ac-2": {
                "fedramp_requirements": ["account_management", "user_identification"],
                "required_params": ["ac-2_prm_1", "ac-2_prm_2"],
                "required_parts": ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k"],
            },
            "ac-3": {
                "fedramp_requirements": ["access_enforcement"],
                "required_params": [],
                "required_parts": [],
            },
            # Additional mappings would be loaded from external sources
        }
    
    async def validate_ssp(
        self, 
        ssp_data: Dict[str, Any], 
        baseline: str = "moderate"
    ) -> FedRAMPValidationResult:
        """
        Validate a System Security Plan against FedRAMP requirements.
        
        Args:
            ssp_data: Parsed OSCAL SSP document
            baseline: FedRAMP baseline (low, moderate, high)
            
        Returns:
            FedRAMP validation result
        """
        start_time = datetime.now(timezone.utc)
        issues = []
        
        self.logger.info(
            "Starting FedRAMP SSP validation",
            baseline=baseline,
            document_type="system-security-plan"
        )
        
        try:
            # Validate document structure
            issues.extend(await self._validate_ssp_structure(ssp_data))
            
            # Validate system metadata
            issues.extend(await self._validate_system_metadata(ssp_data, baseline))
            
            # Validate control implementation
            issues.extend(await self._validate_control_implementation(ssp_data, baseline))
            
            # Validate responsible roles
            issues.extend(await self._validate_responsible_roles(ssp_data))
            
            # Validate component definitions
            issues.extend(await self._validate_components(ssp_data))
            
            # Validate authorization boundary
            issues.extend(await self._validate_authorization_boundary(ssp_data))
            
            # Validate data flow documentation
            issues.extend(await self._validate_data_flows(ssp_data, baseline))
            
            # Check for required attachments/artifacts
            issues.extend(await self._validate_required_artifacts(ssp_data, baseline))
            
        except Exception as e:
            self.logger.error("FedRAMP validation failed", error=str(e))
            issues.append(FedRAMPValidationIssue(
                severity="error",
                code="FEDRAMP_VALIDATION_ERROR",
                message=f"Validation process failed: {str(e)}",
                context={"exception_type": type(e).__name__}
            ))
        
        duration = datetime.now(timezone.utc) - start_time
        is_compliant = len([i for i in issues if i.severity == "error"]) == 0
        
        return FedRAMPValidationResult(
            is_compliant=is_compliant,
            baseline=baseline,
            document_type="system-security-plan",
            issues=issues,
            validation_time_ms=int(duration.total_seconds() * 1000),
            metadata={
                "total_issues": len(issues),
                "error_count": len([i for i in issues if i.severity == "error"]),
                "warning_count": len([i for i in issues if i.severity == "warning"]),
                "validation_date": start_time.isoformat(),
            }
        )
    
    async def _validate_ssp_structure(self, ssp_data: Dict[str, Any]) -> List[FedRAMPValidationIssue]:
        """Validate basic SSP document structure."""
        issues = []
        
        # Check for required top-level elements
        required_elements = [
            "system-security-plan",
            "uuid",
            "metadata", 
            "system-characteristics",
            "system-implementation",
            "control-implementation"
        ]
        
        ssp_root = ssp_data.get("system-security-plan", {})
        
        for element in required_elements:
            if element not in ssp_root:
                issues.append(FedRAMPValidationIssue(
                    severity="error",
                    code="FEDRAMP_MISSING_ELEMENT",
                    message=f"Required element '{element}' is missing from SSP",
                    location=f"system-security-plan.{element}",
                    requirement="FedRAMP SSP Template Requirements"
                ))
        
        # Validate UUID format
        uuid_pattern = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
        if "uuid" in ssp_root:
            if not uuid_pattern.match(ssp_root["uuid"]):
                issues.append(FedRAMPValidationIssue(
                    severity="error",
                    code="FEDRAMP_INVALID_UUID",
                    message="SSP UUID format is invalid",
                    location="system-security-plan.uuid",
                    suggested_fix="Ensure UUID follows RFC 4122 format"
                ))
        
        return issues
    
    async def _validate_system_metadata(self, ssp_data: Dict[str, Any], baseline: str) -> List[FedRAMPValidationIssue]:
        """Validate system metadata requirements."""
        issues = []
        
        ssp_root = ssp_data.get("system-security-plan", {})
        metadata = ssp_root.get("metadata", {})
        system_chars = ssp_root.get("system-characteristics", {})
        
        baseline_reqs = self.baseline_requirements.get(baseline, {})
        required_metadata = baseline_reqs.get("required_metadata", [])
        
        # Check required metadata fields
        for field in required_metadata:
            if field == "system_name":
                title = metadata.get("title", "")
                if not title or len(title.strip()) < 3:
                    issues.append(FedRAMPValidationIssue(
                        severity="error",
                        code="FEDRAMP_MISSING_SYSTEM_NAME",
                        message="System name (title) is required and must be at least 3 characters",
                        location="system-security-plan.metadata.title",
                        baseline=baseline
                    ))
            
            elif field == "system_id":
                # Check for system identification in system-characteristics
                system_id = system_chars.get("system-id")
                if not system_id:
                    issues.append(FedRAMPValidationIssue(
                        severity="error",
                        code="FEDRAMP_MISSING_SYSTEM_ID",
                        message="System identifier is required",
                        location="system-security-plan.system-characteristics.system-id",
                        baseline=baseline
                    ))
        
        # Validate version and last-modified
        if "version" not in metadata:
            issues.append(FedRAMPValidationIssue(
                severity="warning",
                code="FEDRAMP_MISSING_VERSION",
                message="Document version should be specified",
                location="system-security-plan.metadata.version"
            ))
        
        if "last-modified" not in metadata:
            issues.append(FedRAMPValidationIssue(
                severity="warning", 
                code="FEDRAMP_MISSING_LAST_MODIFIED",
                message="Last modified timestamp should be specified",
                location="system-security-plan.metadata.last-modified"
            ))
        
        return issues
    
    async def _validate_control_implementation(self, ssp_data: Dict[str, Any], baseline: str) -> List[FedRAMPValidationIssue]:
        """Validate control implementation requirements."""
        issues = []
        
        ssp_root = ssp_data.get("system-security-plan", {})
        control_impl = ssp_root.get("control-implementation", {})
        implemented_requirements = control_impl.get("implemented-requirements", [])
        
        # Get required controls for baseline
        baseline_reqs = self.baseline_requirements.get(baseline, {})
        required_controls = set(baseline_reqs.get("required_controls", []))
        
        # Track implemented controls
        implemented_controls = set()
        
        for req in implemented_requirements:
            control_id = req.get("control-id", "").lower()
            if control_id:
                implemented_controls.add(control_id)
                
                # Validate control implementation details
                statements = req.get("statements", [])
                if not statements:
                    issues.append(FedRAMPValidationIssue(
                        severity="error",
                        code="FEDRAMP_MISSING_CONTROL_STATEMENTS",
                        message=f"Control {control_id.upper()} is missing implementation statements",
                        location=f"control-implementation.implemented-requirements[control-id='{control_id}'].statements",
                        baseline=baseline
                    ))
                
                # Check for responsible roles
                responsible_roles = req.get("responsible-roles", [])
                if not responsible_roles:
                    issues.append(FedRAMPValidationIssue(
                        severity="warning",
                        code="FEDRAMP_MISSING_RESPONSIBLE_ROLES",
                        message=f"Control {control_id.upper()} should specify responsible roles",
                        location=f"control-implementation.implemented-requirements[control-id='{control_id}'].responsible-roles",
                        baseline=baseline
                    ))
        
        # Check for missing required controls
        missing_controls = required_controls - implemented_controls
        for missing_control in missing_controls:
            issues.append(FedRAMPValidationIssue(
                severity="error",
                code="FEDRAMP_MISSING_REQUIRED_CONTROL",
                message=f"Required control {missing_control.upper()} is not implemented",
                location="control-implementation.implemented-requirements",
                requirement=f"FedRAMP {baseline.title()} Baseline",
                baseline=baseline,
                suggested_fix=f"Add implementation for control {missing_control.upper()}"
            ))
        
        # Check minimum control count
        min_controls = baseline_reqs.get("min_controls", 0)
        if len(implemented_controls) < min_controls:
            issues.append(FedRAMPValidationIssue(
                severity="error",
                code="FEDRAMP_INSUFFICIENT_CONTROLS",
                message=f"Insufficient controls implemented. Expected at least {min_controls}, found {len(implemented_controls)}",
                location="control-implementation.implemented-requirements",
                baseline=baseline
            ))
        
        return issues
    
    async def _validate_responsible_roles(self, ssp_data: Dict[str, Any]) -> List[FedRAMPValidationIssue]:
        """Validate responsible roles and parties."""
        issues = []
        
        ssp_root = ssp_data.get("system-security-plan", {})
        metadata = ssp_root.get("metadata", {})
        
        # Check for required roles
        roles = metadata.get("roles", [])
        parties = metadata.get("parties", [])
        
        required_roles = [
            "system-owner", "authorizing-official", "system-administrator",
            "information-system-security-manager", "control-assessor"
        ]
        
        role_ids = {role.get("id") for role in roles}
        
        for required_role in required_roles:
            if required_role not in role_ids:
                issues.append(FedRAMPValidationIssue(
                    severity="error",
                    code="FEDRAMP_MISSING_ROLE",
                    message=f"Required role '{required_role}' is not defined",
                    location="system-security-plan.metadata.roles",
                    requirement="FedRAMP Required Roles"
                ))
        
        # Validate that roles have associated parties
        responsible_parties = metadata.get("responsible-parties", [])
        for responsible_party in responsible_parties:
            role_id = responsible_party.get("role-id")
            party_uuids = responsible_party.get("party-uuids", [])
            
            if not party_uuids:
                issues.append(FedRAMPValidationIssue(
                    severity="warning",
                    code="FEDRAMP_ROLE_WITHOUT_PARTY",
                    message=f"Role '{role_id}' has no assigned parties",
                    location="system-security-plan.metadata.responsible-parties"
                ))
        
        return issues
    
    async def _validate_components(self, ssp_data: Dict[str, Any]) -> List[FedRAMPValidationIssue]:
        """Validate system components and their relationships."""
        issues = []
        
        ssp_root = ssp_data.get("system-security-plan", {})
        system_impl = ssp_root.get("system-implementation", {})
        components = system_impl.get("components", [])
        
        if not components:
            issues.append(FedRAMPValidationIssue(
                severity="error",
                code="FEDRAMP_NO_COMPONENTS",
                message="System must define at least one component",
                location="system-security-plan.system-implementation.components",
                requirement="FedRAMP System Documentation Requirements"
            ))
            return issues
        
        for idx, component in enumerate(components):
            component_uuid = component.get("uuid")
            component_type = component.get("type")
            title = component.get("title", "")
            
            if not component_uuid:
                issues.append(FedRAMPValidationIssue(
                    severity="error",
                    code="FEDRAMP_COMPONENT_MISSING_UUID",
                    message=f"Component at index {idx} is missing UUID",
                    location=f"system-security-plan.system-implementation.components[{idx}].uuid"
                ))
            
            if not component_type:
                issues.append(FedRAMPValidationIssue(
                    severity="error",
                    code="FEDRAMP_COMPONENT_MISSING_TYPE",
                    message=f"Component '{title}' is missing type specification",
                    location=f"system-security-plan.system-implementation.components[{idx}].type"
                ))
            
            if not title or len(title.strip()) < 3:
                issues.append(FedRAMPValidationIssue(
                    severity="error",
                    code="FEDRAMP_COMPONENT_MISSING_TITLE",
                    message=f"Component at index {idx} needs a descriptive title (min 3 characters)",
                    location=f"system-security-plan.system-implementation.components[{idx}].title"
                ))
        
        return issues
    
    async def _validate_authorization_boundary(self, ssp_data: Dict[str, Any]) -> List[FedRAMPValidationIssue]:
        """Validate authorization boundary documentation."""
        issues = []
        
        ssp_root = ssp_data.get("system-security-plan", {})
        system_chars = ssp_root.get("system-characteristics", {})
        
        # Check for authorization boundary description
        auth_boundary = system_chars.get("authorization-boundary")
        if not auth_boundary:
            issues.append(FedRAMPValidationIssue(
                severity="error",
                code="FEDRAMP_MISSING_AUTH_BOUNDARY",
                message="Authorization boundary description is required",
                location="system-security-plan.system-characteristics.authorization-boundary",
                requirement="FedRAMP Authorization Boundary Requirements"
            ))
        else:
            description = auth_boundary.get("description", "")
            if not description or len(description.strip()) < 50:
                issues.append(FedRAMPValidationIssue(
                    severity="warning",
                    code="FEDRAMP_INSUFFICIENT_AUTH_BOUNDARY",
                    message="Authorization boundary description should be more detailed (min 50 characters)",
                    location="system-security-plan.system-characteristics.authorization-boundary.description"
                ))
        
        # Check for network architecture
        network_arch = system_chars.get("network-architecture")
        if not network_arch:
            issues.append(FedRAMPValidationIssue(
                severity="warning",
                code="FEDRAMP_MISSING_NETWORK_ARCH",
                message="Network architecture documentation is recommended",
                location="system-security-plan.system-characteristics.network-architecture"
            ))
        
        return issues
    
    async def _validate_data_flows(self, ssp_data: Dict[str, Any], baseline: str) -> List[FedRAMPValidationIssue]:
        """Validate data flow documentation for higher baselines."""
        issues = []
        
        if baseline == "low":
            return issues  # Data flow documentation less critical for low baseline
        
        ssp_root = ssp_data.get("system-security-plan", {})
        system_chars = ssp_root.get("system-characteristics", {})
        
        data_flow = system_chars.get("data-flow")
        if not data_flow:
            severity = "error" if baseline == "high" else "warning"
            issues.append(FedRAMPValidationIssue(
                severity=severity,
                code="FEDRAMP_MISSING_DATA_FLOW",
                message=f"Data flow documentation is {'required' if baseline == 'high' else 'recommended'} for {baseline.title()} baseline",
                location="system-security-plan.system-characteristics.data-flow",
                baseline=baseline
            ))
        
        return issues
    
    async def _validate_required_artifacts(self, ssp_data: Dict[str, Any], baseline: str) -> List[FedRAMPValidationIssue]:
        """Validate required attachments and artifacts."""
        issues = []
        
        ssp_root = ssp_data.get("system-security-plan", {})
        back_matter = ssp_root.get("back-matter", {})
        resources = back_matter.get("resources", [])
        
        # Define required artifacts by baseline
        required_artifacts = {
            "low": ["system-security-plan", "rules-of-behavior"],
            "moderate": [
                "system-security-plan", "rules-of-behavior", "privacy-impact-assessment",
                "contingency-plan", "configuration-management-plan"
            ],
            "high": [
                "system-security-plan", "rules-of-behavior", "privacy-impact-assessment", 
                "contingency-plan", "configuration-management-plan", "incident-response-plan",
                "system-security-architecture", "penetration-test-results"
            ]
        }
        
        baseline_artifacts = required_artifacts.get(baseline, [])
        
        # Extract resource titles/types from back-matter
        resource_types = set()
        for resource in resources:
            title = resource.get("title", "").lower()
            resource_types.add(title)
            
            # Also check props for document-type
            props = resource.get("props", [])
            for prop in props:
                if prop.get("name") == "document-type":
                    resource_types.add(prop.get("value", "").lower())
        
        # Check for missing required artifacts
        for artifact in baseline_artifacts:
            artifact_found = any(artifact.lower() in resource_type for resource_type in resource_types)
            if not artifact_found:
                issues.append(FedRAMPValidationIssue(
                    severity="warning",  # Warnings since artifacts might be referenced externally
                    code="FEDRAMP_MISSING_ARTIFACT",
                    message=f"Required artifact '{artifact}' not found in back-matter resources",
                    location="system-security-plan.back-matter.resources",
                    baseline=baseline,
                    suggested_fix=f"Add reference to {artifact} document in back-matter"
                ))
        
        return issues


class FedRAMPService:
    """
    Main FedRAMP validation service.
    
    Orchestrates FedRAMP constraint validation and integrates with
    the broader OSCAL validation pipeline.
    """
    
    def __init__(self):
        self.logger = structlog.get_logger().bind(component="fedramp_service")
        self.validator = FedRAMPConstraintValidator()
    
    async def validate_document(
        self,
        file_path: Union[str, Path],
        baseline: str = "moderate",
        document_type: Optional[str] = None
    ) -> FedRAMPValidationResult:
        """
        Validate an OSCAL document against FedRAMP constraints.
        
        Args:
            file_path: Path to OSCAL document (JSON or XML)
            baseline: FedRAMP baseline (low, moderate, high)
            document_type: OSCAL document type (auto-detected if None)
            
        Returns:
            FedRAMP validation result
        """
        file_path = Path(file_path)
        
        try:
            # Load and parse the document
            if file_path.suffix.lower() == '.json':
                with open(file_path, 'r', encoding='utf-8') as f:
                    document_data = json.load(f)
            else:
                # For XML, we'd need to convert to JSON first
                raise NotImplementedError("XML parsing not yet implemented")
            
            # Auto-detect document type if not provided
            if not document_type:
                document_type = self._detect_document_type(document_data)
            
            # Route to appropriate validator based on document type
            if document_type == "system-security-plan":
                return await self.validator.validate_ssp(document_data, baseline)
            else:
                # For other document types, return a basic result
                return FedRAMPValidationResult(
                    is_compliant=True,
                    baseline=baseline,
                    document_type=document_type,
                    issues=[FedRAMPValidationIssue(
                        severity="info",
                        code="FEDRAMP_UNSUPPORTED_DOCUMENT",
                        message=f"FedRAMP validation not yet implemented for {document_type} documents",
                    )],
                    metadata={"note": "Basic validation passed"}
                )
                
        except Exception as e:
            self.logger.error("FedRAMP validation failed", file_path=str(file_path), error=str(e))
            return FedRAMPValidationResult(
                is_compliant=False,
                baseline=baseline,
                document_type=document_type or "unknown",
                issues=[FedRAMPValidationIssue(
                    severity="error",
                    code="FEDRAMP_VALIDATION_FAILED",
                    message=f"FedRAMP validation failed: {str(e)}",
                    context={"exception_type": type(e).__name__}
                )]
            )
    
    def _detect_document_type(self, document_data: Dict[str, Any]) -> str:
        """Detect the OSCAL document type from document content."""
        
        # Check for top-level keys that indicate document type
        if "system-security-plan" in document_data:
            return "system-security-plan"
        elif "catalog" in document_data:
            return "catalog"
        elif "profile" in document_data:
            return "profile"
        elif "component-definition" in document_data:
            return "component-definition"
        elif "assessment-plan" in document_data:
            return "assessment-plan"
        elif "assessment-results" in document_data:
            return "assessment-results"
        elif "plan-of-action-and-milestones" in document_data:
            return "plan-of-action-and-milestones"
        else:
            return "unknown"
    
    async def get_baseline_requirements(self, baseline: str) -> Dict[str, Any]:
        """Get the requirements for a specific FedRAMP baseline."""
        return self.validator.baseline_requirements.get(baseline, {})