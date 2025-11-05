# Milestone 0 — Baseline & Guardrails

## Epic 0.1 — Freeze the current artifact

* **Issue 0.1.1**: Snapshot current `Diagram 1` (`.mmd`) as `diagram1_drifted.mmd`.
* **Issue 0.1.2**: Add a top-block comment: version, date, “K0 ready / Bridge+Pipelines not”.
* **Acceptance**: Baseline committed, untouched for reference.

## Epic 0.2 — Diagram lint rules (structural, not code)

* **Issue 0.2.1**: Add a “Diagram Rules” section at top (comments) with these hard rules:

  * R1: **All external ingress must terminate at `K0_BRIDGE`** (no direct `ING→CMD/QRY/SSE/OBS`).
  * R2: **P01–P20 must be inside `K0_KERNEL`** (no external “Facade→K0 Bus”).
  * R3: **No user-space edges to `st_*` drivers/aliases**.
  * R4: **K0_PEP@syscall = only authority** (user-space PEP = hints).
  * R5: **SSE subscriptions terminate at Bridge**, not directly at `K0.SSE`.
* **Issue 0.2.2**: Add “visual legend keys” for **Bridge** vs **Kernel** borders and **fast/smart lane** glyphs.
* **Acceptance**: Rules appear in header; legend keys listed.

---

# Milestone 1 — Re-establish the K0/K1/Bridge boundary

## Epic 1.1 — Insert first-class **K0_BRIDGE** subgraph (diagram only)

* **Issue 1.1.1**: Create `subgraph K0_BRIDGE["K0 Bridge (contract choke-point)"]` (user-space).
* **Issue 1.1.2**: Inside K0_BRIDGE add nodes (names only; **no code**):

  * `bridge_command_client`, `bridge_query_client`, `bridge_sse_client`, `bridge_obs_client`
  * `bridge_planes_agent/family/control`
  * `bridge_identity_user_device`
  * `bridge_contracts_flatbuffers`, `bridge_batching_compress`, `bridge_retry_cb`, `bridge_idempotency_keying`
* **Acceptance**: Bridge appears as the **only** hop to K0 ports.

## Epic 1.2 — Rewire ingress through Bridge

* **Issue 1.2.1**: Replace all `ING→CMD/QRY/SSE/OBS` with:

  * `ING→K0_BRIDGE` and from Bridge to `CMD/QRY/SSE/OBS`.
* **Issue 1.2.2**: Delete any residual direct client/app → K0 port edges.
* **Acceptance**: No direct edges to K0 ports exist outside Bridge.

---

# Milestone 2 — Pipeline ownership clarity (inside K0)

## Epic 2.1 — Move **P01–P20** into `K0_KERNEL`

* **Issue 2.1.1**: Relocate the `PIPELINES` subgraph **inside** `K0_KERNEL`.
* **Issue 2.1.2**: Wire `K0_BUS → P01…P20 → K0_DRIVERS` (fan-out backpressure preserved).
* **Issue 2.1.3**: Remove “Facade→K0 Bus” boxes; keep a single `K0_BUS` in kernel.
* **Acceptance**: All P01–P20 visually and structurally live inside K0.

## Epic 2.2 — Fast/Smart lane labels (diagram only)

* **Issue 2.2.1**: Keep **fast** vs **smart** lane labels, but the **entry point** to K0 is **always via Bridge**.
* **Acceptance**: Lanes shown conceptually; no lane bypass of Bridge.

---

# Milestone 3 — Storage/driver decoupling

## Epic 3.1 — Remove user-space → `st_*` edges

* **Issue 3.1.1**: Delete all edges from user-space blocks (cognition, retrieval, services, embeddings) to `st_sem/st_epi/st_vec/st_fts/st_kg_dom/st_ws/st_emb/st_hipp_store`.
* **Issue 3.1.2**: Replace each with:

  * **Writes**: `<module> → K0_BRIDGE → CMD`
  * **Reads**: `<module> → K0_BRIDGE → QRY`
* **Acceptance**: No user-space → driver/store edges remain.

## Epic 3.2 — Keep alias notes as comments only

* **Issue 3.2.1**: Turn `st_* (alias)` callouts into **commented legend lines**, not live edges.
* **Acceptance**: Drivers only touched by pipelines in K0.

---

# Milestone 4 — Policy authority & hints

## Epic 4.1 — Emphasize PEP@syscall as single authority

* **Issue 4.1.1**: Re-position `K0_PEP` between `CMD/QRY/SSE/OBS` and any kernel internals, with a bold “AUTHORITY” label.
* **Issue 4.1.2**: Move user-space PEP/QoS/Safety under **K0_BRIDGE** and mark “hints only”.
* **Acceptance**: Visual authority line is unambiguous.

---

# Milestone 5 — SSE & topics termination

## Epic 5.1 — Terminate SSE at Bridge

* **Issue 5.1.1**: Change `SSE_ACL↔UI/AGENTS/...` connections to **`UI/AGENTS → K0_BRIDGE → SSE`**.
* **Issue 5.1.2**: Keep ACL node **inside K0** but show consumption via Bridge’s `bridge_sse_client`.
* **Acceptance**: No app subscribes directly to K0.SSE.

---

# Milestone 6 — Identity, devices, and planes relocation

## Epic 6.1 — Move planes/identity into Bridge

* **Issue 6.1.1**: Relabel `API_TIERS`+`API_INGRESS` as client/edge and route them into **K0_BRIDGE**, not K0.
* **Issue 6.1.2**: Add explicit nodes in Bridge for:

  * `bridge_identity_user_device` (user creation, device add/pair)
  * `bridge_planes_agent/family/control` (adapters)
* **Acceptance**: Identity/planes visually reside in Bridge; K0 only persists facts via commands.

---

# Milestone 7 — Cognition/WM/Retrieval re-wiring (no store coupling)

## Epic 7.1 — Replace direct storage calls with command/query flows

* **Issue 7.1.1**: For **write** paths (e.g., hippocampus encode, steward commit), change edges to `… → K0_BRIDGE → CMD`.
* **Issue 7.1.2**: For **recall** paths (context builder, retrieval), change to `… → K0_BRIDGE → QRY`.
* **Issue 7.1.3**: Preserve existing **event topic** lines, but show them **originating in K0** and **consumed via Bridge SSE** if needed.
* **Acceptance**: Cognition remains rich but only touches K0 through the Bridge.

---

# Milestone 8 — Legends, styles, and boundary cosmetics

## Epic 8.1 — Clarify visual grammar

* **Issue 8.1.1**: Add a **distinct classDef** for `bridge` (e.g., `classDef bridge fill:#eef7ff,stroke:#2f54eb,stroke-width:3px,rx:8,ry:8`).
* **Issue 8.1.2**: Kernel boundary gets thicker, dashed red (`privileged_boundary`) around **K0 only**.
* **Issue 8.1.3**: One **K0_BUS** instance; demote any duplicate buses.
* **Acceptance**: A quick glance shows: Clients → Bridge → K0; Drivers live behind K0.

---

# Milestone 9 — Consistency pass & acceptance checks

## Epic 9.1 — Structural acceptance checklist

* **Issue 9.1.1**: Verify rules:

  * ✅ No `ING→CMD/QRY/SSE/OBS`
  * ✅ No user-space `→ st_*`
  * ✅ P01–P20 **inside** K0
  * ✅ `K0_PEP` is a choke-point before any kernel internals
  * ✅ SSE consumption via Bridge only
  * ✅ Identity/planes in Bridge
* **Acceptance**: All six checks pass.

## Epic 9.2 — Label & naming normalization

* **Issue 9.2.1**: Normalize node names: `K0_BRIDGE`, `bridge_*`, `K0_*`, `st_*`.
* **Issue 9.2.2**: Add “(diagram only, not code)” to any node that’s illustrative.
* **Acceptance**: No ambiguous or code-suggestive mislabels.

---

# Milestone 10 — Deliverables & versioning

## Epic 10.1 — Produce final diagram artifacts

* **Issue 10.1.1**: Export corrected Mermaid as `k0_architecture_diagram_v1.1.mmd`.
* **Issue 10.1.2**: Add a short CHANGELOG block at top of the file summarizing rewires (1–2 dozen bullets).
* **Issue 10.1.3**: Add a small “Drift Heatmap → Resolved” table in comments (boundary/ownership/wiring/policy/SSE/identity).
* **Acceptance**: Single, clean `.mmd` with embedded change notes.

---

## “What changes will actually appear on the page?” (Summary of edits you’ll make to the drawing)

* **Insert** a big **K0_BRIDGE** box in user-space; run **all** client/plane/identity edges **into it**.
* **Move** **P01–P20** **inside** `K0_KERNEL`; wire `K0_BUS` → pipelines → drivers.
* **Delete** **every** user-space → `st_*` edge; replace with `…→K0_BRIDGE→CMD/QRY`.
* **Make** `K0_PEP` the bold choke-point just after Ports; mark user-space PEP/QoS/Safety as **hints** under Bridge.
* **Terminate** SSE through **Bridge SSE client**; no direct app subscriptions to `K0.SSE`.
* **Relocate** user creation/device add/plane adapters into **Bridge**; K0 only persists via commands.
* **Tighten** borders/styles so **K0** (privileged) vs **Bridge** (user-space) is unmistakable.

---

## Notes aligned to your constraints

* We **do not** change K0 internals; K0 is **ready**.
* This plan is **diagram-only** (no code/impl tasks).
* Bridge reference you provided informs **naming and boxes** in K0_BRIDGE, but remains **purely representational** in the diagram.
* The result will be “Diagram 1 (K0) — **aligned**, no drift,” keeping your original cognitive richness, now **properly routed** via the Bridge.
