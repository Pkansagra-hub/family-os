#!/usr/bin/env python3
"""
Validate ADR Metadata - Check YAML frontmatter completeness and correctness

This script validates that all ADR files have proper YAML frontmatter with required fields.
Can be run as pre-commit hook to enforce metadata standards.

Usage:
    python scripts/validate_adr_metadata.py                # Validate all ADRs
    python scripts/validate_adr_metadata.py --folder 01-foundation  # Validate specific folder
    python scripts/validate_adr_metadata.py --file docs/architecture/decisions/01-foundation/0004-56-module-5-layer-architecture/0004.md
    python scripts/validate_adr_metadata.py --fix          # Auto-add missing frontmatter (interactive)
    python scripts/validate_adr_metadata.py --strict       # Fail on any warnings

Exit Codes:
    0 - All validations passed
    1 - Validation errors found
    2 - No ADR files found
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from datetime import datetime
import frontmatter
import re


# Required frontmatter fields
REQUIRED_FIELDS = {
    'adr_number': str,
    'title': str,
    'status': str,
}

# Optional but recommended fields
RECOMMENDED_FIELDS = {
    'date_created': str,
    'authors': list,
    'affected_layers': list,
    'concerns': list,
    'related_adrs': list,
    'implementation_status': str,
}

# Valid status values
VALID_STATUSES = {
    'PROPOSED', 'DRAFT', 'ACCEPTED', 'IMPLEMENTED',
    'SUPERSEDED', 'REJECTED', 'DEPRECATED', 'UNKNOWN'
}

# Valid layer values
VALID_LAYERS = {
    'layer1_input', 'layer2_orchestration', 'layer3_execution',
    'layer4_runtime', 'layer5_infrastructure', 'cross-cutting'
}

# Valid concern tags
VALID_CONCERNS = {
    'architecture', 'modularity', 'performance', 'maintainability',
    'testing', 'security', 'privacy', 'observability', 'cost',
    'scalability', 'reliability', 'usability', 'compatibility'
}


class ValidationError:
    """Represents a validation error."""

    def __init__(self, level: str, field: str, message: str, file_path: Path):
        self.level = level  # 'ERROR', 'WARNING', 'INFO'
        self.field = field
        self.message = message
        self.file_path = file_path

    def __str__(self):
        icon = {'ERROR': '❌', 'WARNING': '⚠️ ', 'INFO': 'ℹ️ '}[self.level]
        return f"{icon} {self.level}: {self.field} - {self.message}"


class ADRMetadataValidator:
    """Validate ADR YAML frontmatter."""

    def __init__(self, base_path: Path, strict: bool = False):
        self.base_path = base_path
        self.decisions_path = base_path / "docs" / "architecture" / "decisions"
        self.strict = strict
        self.errors: List[ValidationError] = []
        self.validated_count = 0
        self.error_count = 0
        self.warning_count = 0

    def validate_file(self, adr_file: Path) -> List[ValidationError]:
        """Validate a single ADR file."""
        file_errors = []

        try:
            with open(adr_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # Check if file has frontmatter
            if not content.startswith('---'):
                file_errors.append(ValidationError(
                    'ERROR', 'frontmatter', 'Missing YAML frontmatter', adr_file
                ))
                return file_errors

            # Parse frontmatter
            post = frontmatter.load(adr_file)
            metadata = post.metadata

            if not metadata:
                file_errors.append(ValidationError(
                    'ERROR', 'frontmatter', 'Empty YAML frontmatter', adr_file
                ))
                return file_errors

            # Validate required fields
            file_errors.extend(self._validate_required_fields(metadata, adr_file))

            # Validate field types
            file_errors.extend(self._validate_field_types(metadata, adr_file))

            # Validate field values
            file_errors.extend(self._validate_field_values(metadata, adr_file))

            # Validate recommended fields
            file_errors.extend(self._validate_recommended_fields(metadata, adr_file))

            # Validate consistency
            file_errors.extend(self._validate_consistency(metadata, adr_file, post.content))

        except Exception as e:
            file_errors.append(ValidationError(
                'ERROR', 'parse', f'Failed to parse file: {e}', adr_file
            ))

        return file_errors

    def _validate_required_fields(self, metadata: Dict, file_path: Path) -> List[ValidationError]:
        """Check required fields are present."""
        errors = []

        for field, expected_type in REQUIRED_FIELDS.items():
            if field not in metadata:
                errors.append(ValidationError(
                    'ERROR', field, f'Required field missing', file_path
                ))
            elif metadata[field] is None or metadata[field] == '':
                errors.append(ValidationError(
                    'ERROR', field, f'Required field is empty', file_path
                ))

        return errors

    def _validate_field_types(self, metadata: Dict, file_path: Path) -> List[ValidationError]:
        """Validate field types match expectations."""
        errors = []

        all_fields = {**REQUIRED_FIELDS, **RECOMMENDED_FIELDS}

        for field, expected_type in all_fields.items():
            if field not in metadata:
                continue

            value = metadata[field]
            if value is None:
                continue

            if expected_type == list and not isinstance(value, list):
                errors.append(ValidationError(
                    'ERROR', field,
                    f'Expected list, got {type(value).__name__}',
                    file_path
                ))
            elif expected_type == str and not isinstance(value, str):
                errors.append(ValidationError(
                    'ERROR', field,
                    f'Expected string, got {type(value).__name__}',
                    file_path
                ))

        return errors

    def _validate_field_values(self, metadata: Dict, file_path: Path) -> List[ValidationError]:
        """Validate field values are within allowed sets."""
        errors = []

        # Validate status
        if 'status' in metadata:
            status = metadata['status'].upper()
            if status not in VALID_STATUSES:
                errors.append(ValidationError(
                    'ERROR', 'status',
                    f'Invalid status "{status}". Must be one of: {", ".join(VALID_STATUSES)}',
                    file_path
                ))

        # Validate affected_layers
        if 'affected_layers' in metadata and isinstance(metadata['affected_layers'], list):
            for layer in metadata['affected_layers']:
                if layer not in VALID_LAYERS:
                    errors.append(ValidationError(
                        'WARNING', 'affected_layers',
                        f'Unknown layer "{layer}". Expected: {", ".join(VALID_LAYERS)}',
                        file_path
                    ))

        # Validate concerns
        if 'concerns' in metadata and isinstance(metadata['concerns'], list):
            for concern in metadata['concerns']:
                if concern not in VALID_CONCERNS:
                    errors.append(ValidationError(
                        'WARNING', 'concerns',
                        f'Unknown concern "{concern}". Expected: {", ".join(sorted(VALID_CONCERNS))}',
                        file_path
                    ))

        # Validate ADR number format
        if 'adr_number' in metadata:
            adr_num = str(metadata['adr_number'])
            if not re.match(r'^\d{4}[a-z]?$', adr_num):
                errors.append(ValidationError(
                    'WARNING', 'adr_number',
                    f'ADR number "{adr_num}" should match format: 0000 or 0000a',
                    file_path
                ))

        return errors

    def _validate_recommended_fields(self, metadata: Dict, file_path: Path) -> List[ValidationError]:
        """Check recommended fields are present."""
        errors = []

        for field in RECOMMENDED_FIELDS.keys():
            if field not in metadata:
                errors.append(ValidationError(
                    'WARNING', field,
                    f'Recommended field missing (improves searchability)',
                    file_path
                ))

        return errors

    def _validate_consistency(self, metadata: Dict, file_path: Path, content: str) -> List[ValidationError]:
        """Validate consistency between frontmatter and content."""
        errors = []

        # Check ADR number matches filename
        if 'adr_number' in metadata:
            adr_num = str(metadata['adr_number'])
            filename = file_path.name

            # Extract number from filename (0004.md or 0004-title.md)
            file_num_match = re.match(r'^(\d{4}[a-z]?)[-.]', filename)
            if file_num_match:
                file_num = file_num_match.group(1)
                if adr_num != file_num:
                    errors.append(ValidationError(
                        'ERROR', 'adr_number',
                        f'ADR number "{adr_num}" does not match filename "{file_num}"',
                        file_path
                    ))

        # Check title appears in content
        if 'title' in metadata and content:
            title = metadata['title']
            if title not in content[:500]:  # Check first 500 chars
                errors.append(ValidationError(
                    'WARNING', 'title',
                    'Title from frontmatter not found in document header',
                    file_path
                ))

        # Check status consistency
        if 'status' in metadata and content:
            frontmatter_status = metadata['status'].upper()
            # Look for status in content
            status_match = re.search(r'\*\*Status[:\*]+\s*(\w+)', content, re.IGNORECASE)
            if status_match:
                content_status = status_match.group(1).upper()
                if frontmatter_status != content_status:
                    errors.append(ValidationError(
                        'WARNING', 'status',
                        f'Frontmatter status "{frontmatter_status}" differs from content status "{content_status}"',
                        file_path
                    ))

        return errors

    def validate_directory(self, folder: Optional[str] = None) -> None:
        """Validate all ADRs in directory."""
        if folder:
            search_path = self.decisions_path / folder
            if not search_path.exists():
                print(f"❌ Folder not found: {folder}", file=sys.stderr)
                sys.exit(2)
        else:
            search_path = self.decisions_path

        print(f"🔍 Validating ADRs in {search_path}...\n")

        # Find all .md files except meta files
        adr_files = []
        for pattern in ['**/*.md', '*/*.md']:
            for file in search_path.glob(pattern):
                # Skip meta files
                if '00-meta' in str(file):
                    continue
                if file.name.lower() in ['readme.md', 'index.md', 'index.yml']:
                    continue

                adr_files.append(file)

        if not adr_files:
            print("⚠️  No ADR files found", file=sys.stderr)
            sys.exit(2)

        print(f"📄 Found {len(adr_files)} ADR files\n")

        # Validate each file
        for adr_file in sorted(adr_files):
            file_errors = self.validate_file(adr_file)

            if not file_errors:
                print(f"✅ {adr_file.relative_to(self.decisions_path)}")
            else:
                rel_path = adr_file.relative_to(self.decisions_path)
                print(f"\n📄 {rel_path}")

                for error in file_errors:
                    print(f"  {error}")
                    self.errors.append(error)

                    if error.level == 'ERROR':
                        self.error_count += 1
                    elif error.level == 'WARNING':
                        self.warning_count += 1

            self.validated_count += 1

    def print_summary(self) -> None:
        """Print validation summary."""
        print("\n" + "=" * 60)
        print("📊 Validation Summary")
        print("=" * 60)

        print(f"\n📈 Total ADRs Validated: {self.validated_count}")
        print(f"❌ Errors: {self.error_count}")
        print(f"⚠️  Warnings: {self.warning_count}")

        if self.error_count == 0 and self.warning_count == 0:
            print("\n✅ All validations passed!")
        elif self.error_count == 0:
            print("\n⚠️  No errors, but warnings present")
            print("💡 Consider fixing warnings for better searchability")
        else:
            print("\n❌ Validation failed")
            print("💡 Fix errors before committing")

        # Group errors by type
        if self.errors:
            print("\n📋 Errors by Type:")
            error_types: Dict[str, int] = {}
            for error in self.errors:
                key = f"{error.level}: {error.field}"
                error_types[key] = error_types.get(key, 0) + 1

            for error_type, count in sorted(error_types.items()):
                print(f"  {error_type}: {count}")

        print("\n" + "=" * 60)

    def suggest_fixes(self) -> None:
        """Suggest fixes for common issues."""
        if not self.errors:
            return

        print("\n💡 Suggested Fixes:\n")

        # Group by file
        errors_by_file: Dict[Path, List[ValidationError]] = {}
        for error in self.errors:
            if error.file_path not in errors_by_file:
                errors_by_file[error.file_path] = []
            errors_by_file[error.file_path].append(error)

        for file_path, file_errors in sorted(errors_by_file.items()):
            rel_path = file_path.relative_to(self.decisions_path)
            print(f"📄 {rel_path}")

            # Check for missing frontmatter
            if any(e.field == 'frontmatter' for e in file_errors):
                print("  → Add YAML frontmatter at top of file:")
                print("     ---")
                print("     adr_number: \"0000\"")
                print("     title: \"Your Title\"")
                print("     status: PROPOSED")
                print("     ---")

            # Check for missing required fields
            missing_required = [e.field for e in file_errors if e.level == 'ERROR' and e.field in REQUIRED_FIELDS]
            if missing_required:
                print(f"  → Add required fields to frontmatter: {', '.join(missing_required)}")

            # Check for invalid status
            if any(e.field == 'status' and 'Invalid status' in e.message for e in file_errors):
                print(f"  → Use valid status: {', '.join(sorted(VALID_STATUSES))}")

            print()


def main():
    parser = argparse.ArgumentParser(
        description='Validate ADR YAML frontmatter'
    )
    parser.add_argument(
        '--folder',
        help='Validate specific folder only',
        default=None
    )
    parser.add_argument(
        '--file',
        type=Path,
        help='Validate specific file only',
        default=None
    )
    parser.add_argument(
        '--strict',
        action='store_true',
        help='Treat warnings as errors (fail on warnings)'
    )
    parser.add_argument(
        '--fix',
        action='store_true',
        help='Interactive mode to fix issues (coming soon)'
    )
    parser.add_argument(
        '--base-path',
        type=Path,
        default=Path.cwd(),
        help='Base repository path (default: current directory)'
    )

    args = parser.parse_args()

    if args.fix:
        print("⚠️  Interactive fix mode not yet implemented")
        print("💡 Please fix issues manually based on suggestions")
        sys.exit(1)

    validator = ADRMetadataValidator(args.base_path, strict=args.strict)

    # Validate single file
    if args.file:
        if not args.file.exists():
            print(f"❌ File not found: {args.file}", file=sys.stderr)
            sys.exit(2)

        print(f"🔍 Validating {args.file}...\n")
        errors = validator.validate_file(args.file)

        if not errors:
            print("✅ Validation passed")
            sys.exit(0)
        else:
            for error in errors:
                print(f"  {error}")
            sys.exit(1)

    # Validate directory
    validator.validate_directory(args.folder)

    # Print summary
    validator.print_summary()

    # Print suggestions
    if validator.error_count > 0 or validator.warning_count > 0:
        validator.suggest_fixes()

    # Exit code
    if validator.error_count > 0:
        sys.exit(1)
    elif args.strict and validator.warning_count > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
