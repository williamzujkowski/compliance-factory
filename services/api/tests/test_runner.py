"""
Test runner for the OSCAL Compliance Factory API.

Provides utilities for running tests, generating coverage reports,
and organizing test execution.
"""

import sys
import subprocess
import argparse
from pathlib import Path
from typing import List, Optional


class TestRunner:
    """Test runner and orchestrator."""
    
    def __init__(self, test_dir: Path = None):
        """Initialize test runner."""
        self.test_dir = test_dir or Path(__file__).parent
        self.api_dir = self.test_dir.parent
        
    def run_unit_tests(self, verbose: bool = False, coverage: bool = True) -> int:
        """Run unit tests."""
        print("🧪 Running unit tests...")
        
        cmd = ["python", "-m", "pytest"]
        cmd.extend([str(self.test_dir / "unit")])
        
        if verbose:
            cmd.append("-v")
        
        if coverage:
            cmd.extend([
                "--cov=app",
                "--cov-report=term-missing",
                "--cov-report=html:htmlcov/unit"
            ])
        
        cmd.extend([
            "--tb=short",
            "-x"  # Stop on first failure
        ])
        
        return subprocess.run(cmd, cwd=self.api_dir).returncode
    
    def run_integration_tests(self, verbose: bool = False, coverage: bool = True) -> int:
        """Run integration tests."""
        print("🔧 Running integration tests...")
        
        cmd = ["python", "-m", "pytest"]
        cmd.extend([str(self.test_dir / "integration")])
        
        if verbose:
            cmd.append("-v")
        
        if coverage:
            cmd.extend([
                "--cov=app",
                "--cov-append",
                "--cov-report=term-missing",
                "--cov-report=html:htmlcov/integration"
            ])
        
        cmd.extend([
            "--tb=short",
            "-x"  # Stop on first failure
        ])
        
        return subprocess.run(cmd, cwd=self.api_dir).returncode
    
    def run_all_tests(self, verbose: bool = False, coverage: bool = True, fail_fast: bool = True) -> int:
        """Run all tests."""
        print("🚀 Running comprehensive test suite...")
        
        cmd = ["python", "-m", "pytest"]
        cmd.append(str(self.test_dir))
        
        if verbose:
            cmd.append("-v")
        
        if coverage:
            cmd.extend([
                "--cov=app",
                "--cov-report=term-missing:skip-covered",
                "--cov-report=html:htmlcov",
                "--cov-report=xml",
                "--cov-fail-under=75"  # Minimum coverage requirement
            ])
        
        cmd.extend([
            "--tb=short",
            "--durations=10"  # Show 10 slowest tests
        ])
        
        if fail_fast:
            cmd.append("-x")
        
        # Add markers for better test organization
        cmd.extend([
            "-m", "not slow"  # Skip slow tests by default
        ])
        
        return subprocess.run(cmd, cwd=self.api_dir).returncode
    
    def run_specific_test(self, test_path: str, verbose: bool = True) -> int:
        """Run a specific test file or test function."""
        print(f"🎯 Running specific test: {test_path}")
        
        cmd = ["python", "-m", "pytest"]
        cmd.append(test_path)
        
        if verbose:
            cmd.extend(["-v", "-s"])
        
        cmd.extend([
            "--tb=long",
            "--capture=no"
        ])
        
        return subprocess.run(cmd, cwd=self.api_dir).returncode
    
    def run_security_tests(self) -> int:
        """Run security-focused tests."""
        print("🔒 Running security tests...")
        
        cmd = ["python", "-m", "pytest"]
        cmd.extend([
            str(self.test_dir),
            "-m", "security",
            "-v",
            "--tb=short"
        ])
        
        return subprocess.run(cmd, cwd=self.api_dir).returncode
    
    def run_performance_tests(self) -> int:
        """Run performance benchmarks."""
        print("⚡ Running performance tests...")
        
        cmd = ["python", "-m", "pytest"]
        cmd.extend([
            str(self.test_dir),
            "-m", "slow",
            "-v", 
            "--tb=short",
            "--durations=0"
        ])
        
        return subprocess.run(cmd, cwd=self.api_dir).returncode
    
    def lint_code(self) -> int:
        """Run code linting."""
        print("📝 Running code linting...")
        
        # Run ruff for linting
        lint_result = subprocess.run([
            "python", "-m", "ruff", "check", "app/", "tests/"
        ], cwd=self.api_dir).returncode
        
        if lint_result != 0:
            print("❌ Linting failed")
            return lint_result
        
        # Run ruff for formatting check
        format_result = subprocess.run([
            "python", "-m", "ruff", "format", "--check", "app/", "tests/"
        ], cwd=self.api_dir).returncode
        
        if format_result != 0:
            print("❌ Code formatting issues found")
            return format_result
        
        print("✅ Code linting passed")
        return 0
    
    def type_check(self) -> int:
        """Run type checking with mypy."""
        print("🔍 Running type checks...")
        
        result = subprocess.run([
            "python", "-m", "mypy", "app/"
        ], cwd=self.api_dir).returncode
        
        if result == 0:
            print("✅ Type checking passed")
        else:
            print("❌ Type checking failed")
        
        return result
    
    def generate_test_report(self) -> None:
        """Generate comprehensive test report."""
        print("📊 Generating test report...")
        
        # Run tests with detailed reporting
        cmd = [
            "python", "-m", "pytest",
            str(self.test_dir),
            "--html=test-report.html",
            "--self-contained-html",
            "--cov=app",
            "--cov-report=html:htmlcov",
            "--cov-report=xml",
            "--junit-xml=test-results.xml"
        ]
        
        subprocess.run(cmd, cwd=self.api_dir)
        
        print("✅ Test report generated:")
        print(f"  - HTML Report: {self.api_dir}/test-report.html")
        print(f"  - Coverage Report: {self.api_dir}/htmlcov/index.html")
        print(f"  - JUnit XML: {self.api_dir}/test-results.xml")
    
    def clean_test_artifacts(self) -> None:
        """Clean up test artifacts and cache files."""
        print("🧹 Cleaning test artifacts...")
        
        import shutil
        
        artifacts_to_clean = [
            ".pytest_cache",
            "__pycache__", 
            "htmlcov",
            "test-report.html",
            "test-results.xml",
            "coverage.xml",
            ".coverage"
        ]
        
        for artifact in artifacts_to_clean:
            artifact_path = self.api_dir / artifact
            if artifact_path.exists():
                if artifact_path.is_dir():
                    shutil.rmtree(artifact_path)
                else:
                    artifact_path.unlink()
        
        # Clean pycache recursively
        for pycache_dir in self.api_dir.rglob("__pycache__"):
            shutil.rmtree(pycache_dir)
        
        print("✅ Test artifacts cleaned")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="OSCAL Compliance Factory Test Runner")
    parser.add_argument("command", choices=[
        "unit", "integration", "all", "specific", "security", "performance",
        "lint", "type-check", "report", "clean"
    ], help="Test command to run")
    
    parser.add_argument("--test-path", help="Specific test path (for 'specific' command)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--no-coverage", action="store_true", help="Skip coverage reporting")
    parser.add_argument("--no-fail-fast", action="store_true", help="Continue on test failures")
    
    args = parser.parse_args()
    
    runner = TestRunner()
    
    try:
        if args.command == "unit":
            return runner.run_unit_tests(args.verbose, not args.no_coverage)
        
        elif args.command == "integration":
            return runner.run_integration_tests(args.verbose, not args.no_coverage)
        
        elif args.command == "all":
            return runner.run_all_tests(
                args.verbose, 
                not args.no_coverage, 
                not args.no_fail_fast
            )
        
        elif args.command == "specific":
            if not args.test_path:
                print("❌ --test-path required for 'specific' command")
                return 1
            return runner.run_specific_test(args.test_path, args.verbose)
        
        elif args.command == "security":
            return runner.run_security_tests()
        
        elif args.command == "performance":
            return runner.run_performance_tests()
        
        elif args.command == "lint":
            return runner.lint_code()
        
        elif args.command == "type-check":
            return runner.type_check()
        
        elif args.command == "report":
            runner.generate_test_report()
            return 0
        
        elif args.command == "clean":
            runner.clean_test_artifacts()
            return 0
        
        else:
            print(f"❌ Unknown command: {args.command}")
            return 1
            
    except KeyboardInterrupt:
        print("\n⏹️ Tests interrupted by user")
        return 130
    except Exception as e:
        print(f"❌ Test runner error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())