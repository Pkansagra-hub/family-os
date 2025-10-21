---
description: Documentation standards and templates for consistent project documentation.
applyTo: "**/README.md,docs/**/*.md,ADR/**/*.md"
---
# 📚 Documentation Standards

## 0) Documentation Principles
- **Clear purpose** - every document has specific goal
- **Consistent format** - follow established templates
- **Living documents** - updated with code changes
- **Discoverability** - easy to find and navigate

## 1) Required Documentation
- **Service README** - purpose, architecture, usage
- **API documentation** - endpoints, parameters, examples
- **Contract documentation** - schema definitions and examples
- **Deployment guides** - installation and configuration

## 2) Documentation Types
```
docs/
├── architecture/        # System architecture docs
├── api/                # API reference docs
├── deployment/         # Deployment and ops guides
├── development/        # Developer guides
└── user/              # End-user documentation
```

## 3) Format Standards
- **Markdown** for all documentation
- **Mermaid diagrams** for visualizations
- **Code examples** that actually work
- **Table of contents** for long documents

## 4) Content Requirements
- Clear purpose statement
- Prerequisites and dependencies
- Step-by-step procedures
- Examples and code snippets
- When changing JSON schemas, update the canonical samples in `k0/contracts/jsonschema/examples/` so documentation and artifacts stay aligned
- Troubleshooting guidance

## 5) Maintenance
- Update docs with code changes
- Review docs during pull requests
- Regular documentation audits
- Community feedback integration
	- Confirm that schema updates include refreshed entries in `k0/contracts/jsonschema/examples/`
