---
description: Documentation standards and templates for consistent project documentation.
applyTo: "**/README.md,docs/**/*.md,docs/architecture/decisions/**/*.md"
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
├── architecture/
│   ├── decisions/       # ADRs (Architecture Decision Records)
│   ├── patterns/        # Design patterns and principles
│   ├── diagrams/        # Architecture diagrams (reference)
│   ├── tables/          # Architecture tables and matrices
│   └── README.md
├── api/                 # API reference documentation
├── deployment/          # Deployment and operations guides
├── development/         # Developer guides and tutorials
│   ├── getting-started.md
│   ├── contribution-guide.md
│   ├── testing-guide.md
│   └── contracts-playbook.md
└── user/               # End-user documentation
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
- **Contract Examples**: When updating API/data contracts, refresh examples in `k1/contracts/jsonschema/examples/` to keep documentation and artifacts aligned
- Troubleshooting guidance

## 5) Documentation by Type

### ADRs (Architecture Decision Records)
- **Location**: `docs/architecture/decisions/XXXX-<title>.md`
- **Format**: Use template from `docs/architecture/decisions/0000-template.md`
- **Content**: Context, Decision, Alternatives, Consequences
- **Updates**: Whenever architectural changes are made

### API Documentation
- **Location**: `docs/api/<component>_api.md`
- **Format**: OpenAPI specification examples, endpoint descriptions
- **Content**: Endpoints, parameters, request/response examples
- **Updates**: With contract changes (keep synced with `k1/contracts/api/`)

### Contract Examples
- **Location**: `k1/contracts/jsonschema/examples/`
- **Format**: JSON files matching contract schemas
- **Content**: Valid example payloads for each schema
- **Updates**: Required whenever schemas change

### Architecture Diagrams
- **Location**: `architecture_diagrams/` (source files)
- **Reference in docs**: `docs/architecture/diagrams/README.md` (references)
- **Format**: Mermaid (.mmd) files
- **Updates**: Validate with `mmd_validate()` before committing

### Deployment Guides
- **Location**: `docs/deployment/<component>_deployment.md`
- **Format**: Step-by-step procedures
- **Content**: Prerequisites, installation, configuration, troubleshooting
- **Updates**: When deployment process changes

## 6) Maintenance
- Update docs with code changes
- Review docs during pull requests
- Regular documentation audits
- Community feedback integration
- **Contract Sync**: Confirm schema updates include refreshed examples in `k1/contracts/jsonschema/examples/`
- **ADR Updates**: When decisions change, create new ADR (don't modify accepted ones)
- **Diagram Updates**: After architecture changes, validate and update diagrams, then reference in docs/architecture/diagrams/

## 7) Documentation Checklist (5-Step Workflow Integration)

When implementing new code (per service-design.instructions.md 5-step workflow):

- [ ] **GATE 1 (ADR)**: ADR created in `docs/architecture/decisions/XXXX-<title>.md`
- [ ] **GATE 2 (Contracts)**: Contract examples added to `k1/contracts/jsonschema/examples/`
- [ ] **GATE 3 (Implementation)**: Code comments reference ADR numbers
- [ ] **GATE 4 (Tests)**: Test documentation in relevant README
- [ ] **GATE 5 (Memory)**: Memory entry created with decisions and file references
- [ ] **Final**: API docs updated in `docs/api/` if endpoints changed
- [ ] **Final**: README updated with new features/components
- [ ] **Final**: Architecture diagrams updated in `architecture_diagrams/` if structure changed
