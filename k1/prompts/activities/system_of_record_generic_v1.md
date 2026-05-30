# System-of-record activity profile v1

Use this profile as procedural guidance only. The resolved capability contract, input schema, safety band, HIL policy, tool grants, and caller role remain authoritative.

- Treat reads and writes as interactions with authoritative structured records. Inspect the schema before choosing params.
- Read existing state before mutation when identity, current version, or conflict status is unclear.
- Preserve idempotency, optimistic concurrency, visibility, and provenance fields when the selected contract exposes them.
- Never invent identifiers, versions, or prior state. Ask for clarification or perform an allowed read instead.
- Keep prompt/profile metadata out of business params; only schema-declared fields belong in the operation payload.
