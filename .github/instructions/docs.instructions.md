---
description: Documentation, READMEs, and ADRs.
applyTo: "docs/**/*.md,**/README.md,ADR/**/*.md,.github/**/*.md"
---
# 📝 Docs & ADRs — Keep it Close to Contracts

## 1) Locations
- Module docs live beside code (`README.md`). Longform in `docs/`. Decisions in `ADR/`.

## 2) ADR Template
- Context → Decision → Consequences → Status → Links to contracts/tests.

## 3) Style
- Use clear headings, short paragraphs, and examples from `contracts/examples`.
- Link to code using relative paths. No stray Markdown in random directories.

## 4) Up-to-date
- Update docs **in the same PR** as code/contract changes.