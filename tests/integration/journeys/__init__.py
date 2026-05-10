"""Epic 7.3 — User journey tests against the live K0 stack.

Each ``test_journey_<n>_<name>.py`` file is one end-to-end story that
exercises real K0 routes (no mocks, no in-memory shims). Journeys are
scoped to surfaces we have proven work against the running Docker K0:

* ``POST /k0/command.submit`` — real Ed25519-signed envelopes commit and
  return ``receipt_id``. Verified by 38 prior tests + Epic 7.2 matrix.
* ``POST /k0/query.recall`` — admits ``policy.abac.roles=["guest"]``
  (the dev manifest's permissive role) and returns a structured bundle
  with ``trace.policy.decision == "ADMIT"``.
* ``POST /k0/obs.emit`` (kind=``metrics``) — accepts a snapshot string
  and returns 204 No Content.
* Postgres ``st_receipts`` direct read via ``docker exec psql`` for
  partition/journey assertions.

The ``/k0/sse.subscribe``/``ack`` and ``/k0/admin/pipelines/*/trigger``
routes exist but are deferred to a later epic — they require Server-Sent
Events handling and admin-token plumbing, which is out of scope for the
foundational happy-path journeys here.
"""
