---
adr_number: 'K005'
affected_modules: ['M05']
title: Space Resolver Architecture - ACL and Ownership Resolution
status: PROPOSED
date_created: '2025-11-16'
---

# K005: Space Resolver Architecture

**Status**: PROPOSED | **Module**: M05

## Context

SpaceResolver computes visibility (ACL) and ownership for episodic memories.

## Current Capabilities

- `visible_to` computation (intersect space defaults with envelope permissions)
- `owner_id` derivation from actor + space rules
- `co_owners` for shared memories
- `author_role` resolution (OWNER/CO_OWNER/VISITOR)
- Fast <3ms P95 performance

## Future Capabilities

- Space hierarchy and inheritance (workspace → household → family)
- Dynamic space rules (time-based visibility, conditional sharing)
- Spatial indexing for proximity-based ACLs
- Cross-space visibility (share memory to multiple spaces)

## Sub-ADRs

- [K005.1: ACL Resolution](k005.1-acl-resolution.md)
- [K005.2: Ownership Derivation](k005.2-ownership-derivation.md)
- [K005.3: Spatial Indexing](k005.3-spatial-indexing.md)

## Performance Budget

- P95: ≤3ms | P99: ≤5ms | Memory: <5MB

---
**Last Updated**: 2025-11-16
