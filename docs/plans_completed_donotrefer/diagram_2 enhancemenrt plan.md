Absolutely. Here’s a **diagram-only** remediation plan to remove drift and make **K0 Diagram 2** perfectly aligned with your K1→K0 (via Bridge) contract and “K0 is solid surface” principle. It’s organized as **Milestones → Epics → Issues**. IDs are stable so you can track work quickly.

---

# Milestone M1 — Restore Kernel Boundary (Bridge First)

### Epic E1 — Introduce an explicit Bridge node in D2

* **Issue M1-E1-I1:** Add `K0_BRIDGE_D2` node with caption “HTTP/2 + FlatBuffers · batching · zstd · receipts”.
* **Issue M1-E1-I2:** Place `K0_BRIDGE_D2` between **all** K1 blocks and `CMD_D2 / QRY_D2 / SSE_D2`.
* **Issue M1-E1-I3:** Style `K0_BRIDGE_D2` with `classDef bus` (or distinct `bridge` class) to signal boundary.

### Epic E2 — Rewire all direct Port edges through Bridge

* **Issue M1-E2-I1:** Rewire `RELAY_MEMORY → CMD_D2` to `RELAY_MEMORY → K0_BRIDGE_D2 → CMD_D2`.
* **Issue M1-E2-I2:** Rewire `WM_MGR → QRY_D2` to `WM_MGR → K0_BRIDGE_D2 → QRY_D2`.
* **Issue M1-E2-I3:** Rewire `GW_BROADCAST → SSE_D2` to `GW_BROADCAST → K0_BRIDGE_D2 → SSE_D2`.
* **Issue M1-E2-I4:** Rewire `svc_write / svc_recall / svc_consol / emb_svc / emb_index / wf_store` → **via** `K0_BRIDGE_D2`.
* **Issue M1-E2-I5 (Acceptance):** Zero K1→Port edges remain that bypass `K0_BRIDGE_D2`.

---

# Milestone M2 — Make K0 Internals Opaque in D2

### Epic E3 — Remove duplicated K0 internals from D2

* **Issue M2-E3-I1:** Delete **UoW Pool**, **UoW workers**, **connection pool**, **SQLite pragmas**, **pool tokens**.
* **Issue M2-E3-I2:** Remove **Tiering** (promotion/demotion engines) and their fan-out edges.
* **Issue M2-E3-I3:** Delete **memory tables** (working/episodic/semantic/procedural/etc.) and related consolidation edges.
* **Issue M2-E3-I4:** Remove **policy/PII/QoS/observability** K0 store internals in D2.

### Epic E4 — Replace with a single authoritative K0 capsule

* **Issue M2-E4-I1:** Add `K0_KERNEL_D2` node: “K0 Kernel (see Diagram 1) — WAL · Receipts · PEP · Pipelines P01–P20”.
* **Issue M2-E4-I2:** For readers, add a **small legend** listing K0 store *types* (SQLite/FTS/Vector/KG) **without** nodes/edges.
* **Issue M2-E4-I3 (Acceptance):** D2 shows **no** K0 internal charts; only `K0_KERNEL_D2` + `K0_PORTS_D2`.

---

# Milestone M3 — Correct Driver Exposure & Adapters

### Epic E5 — Remove direct edges to K0 drivers

* **Issue M3-E5-I1:** Delete `ret_*_adapter → K0_FTS_Q / K0_VEC_Q / K0_KG_Q / K0_SQLITE_Q` edges.
* **Issue M3-E5-I2:** Convert those drivers to **legend text** (no nodes) or keep them only in D1.

### Epic E6 — Re-target adapters to Query via Bridge

* **Issue M3-E6-I1:** `K0_QUERY_ADAPTER → K0_BRIDGE_D2 → QRY_D2`.
* **Issue M3-E6-I2:** `ret_context_adapter → K0_BRIDGE_D2 → QRY_D2`.
* **Issue M3-E6-I3 (Acceptance):** All retrieval flows show **only** `… → K0_BRIDGE_D2 → QRY_D2`.

---

# Milestone M4 — Pipeline & Port Opacity

### Epic E7 — Collapse explicit pipeline nodes in D2

* **Issue M4-E7-I1:** Remove `K0_PIPELINES_D2` subgraph (P02/P03/P06/P19 nodes).
* **Issue M4-E7-I2:** Add a slim badge: “Pipelines P01–P20 (opaque, see D1)”.

### Epic E8 — Replace “to pipeline” edges with port calls

* **Issue M4-E8-I1:** Replace `… → P03_D2` with `… → K0_BRIDGE_D2 → CMD_D2` + note “triggers consolidation (P03)”.
* **Issue M4-E8-I2:** Replace any “embedding updates via P08” with a **comment** on the `CMD_D2/QRY_D2` call.
* **Issue M4-E8-I3 (Acceptance):** D2 shows **ports only**; pipeline mentions exist only as **annotations**.

---

# Milestone M5 — Responsibility & Label Normalization

### Epic E9 — Fix wording that implies K0 is the control plane

* **Issue M5-E9-I1:** Rename “K0-mediated consciousness/authority/executive” → “K0-aware / via K0 recall/write / K0-integrated”.
* **Issue M5-E9-I2:** Ensure **K1 owns orchestration** verbs; **K0** verbs remain persist/recall/enforce/emit.
* **Issue M5-E9-I3:** Add a top caption: “K1 orchestrates · K0 persists/policies · All calls via K0 Bridge”.

### Epic E10 — Make SSE path explicit but neutral

* **Issue M5-E10-I1:** `GW_BROADCAST → K0_BRIDGE_D2 → SSE_D2`.
* **Issue M5-E10-I2:** Caption on SSE: “subscribe/ack via Bridge; topic filtering enforced by K0”.

---

# Milestone M6 — Governance & Conformance (Diagram-only checks)

### Epic E11 — Boundary rules encoded as comments + visual guards

* **Issue M6-E11-I1:** Add a **comment block** at top: “Rule: No K1→K0 direct; all CMD/QRY/SSE via K0_BRIDGE_D2.”
* **Issue M6-E11-I2:** Add a **thin border subgraph** around `K0_PORTS_D2` labeled “K0 Boundary (ABI)”.

### Epic E12 — Drift conformance sweep

* **Issue M6-E12-I1:** Search for arrows pointing to `*_D2` ports that **don’t** pass through `K0_BRIDGE_D2`.
* **Issue M6-E12-I2:** Search for any `K0::st_*` nodes in D2 and remove them.
* **Issue M6-E12-I3 (Acceptance):** Zero violations found by search; keep a small checklist at file end.

---

# Milestone M7 — Cross-Diagram Integrity

### Epic E13 — Harmonize D2 with D1/D3 connectors

* **Issue M7-E13-I1:** Ensure only **three** external anchors remain: `FROM_API` (D1), `TO_INTELLIGENCE` (D3), `TO_INFRASTRUCTURE` (D4).
* **Issue M7-E13-I2:** Add a micro-legend referencing **Diagram 1** as the **authoritative K0 internals**.

---

# Milestone M8 — Visual Cleanup & Legends

### Epic E14 — Clarify roles through styling

* **Issue M8-E14-I1:** Define `classDef bridge` (e.g., light gray fill, bold stroke) for `K0_BRIDGE_D2`.
* **Issue M8-E14-I2:** Keep `K0_PORTS_D2` in `bus/fast` style; K1 cognition in `brain`/`mid`.
* **Issue M8-E14-I3:** Add a tiny “Icon Legend” for: K1 cognition, K0 ports, Bridge, External links.

### Epic E15 — Prune redundant captions

* **Issue M8-E15-I1:** Shorten overlong node labels; push detail into comments.
* **Issue M8-E15-I2 (Acceptance):** Diagram fits comfortably; no text truncation in usual renderers.

---

## Global Acceptance Criteria (for the whole plan)

1. **Boundary:** No K1 node connects directly to `CMD_D2 / QRY_D2 / SSE_D2`; all go through `K0_BRIDGE_D2`.
2. **Opacity:** No K0 internal drivers, pools, tiering, or memory tables appear in D2.
3. **Pipelines:** P01–P20 are referenced only as **opaque** (annotations or a single capsule), never as wired nodes.
4. **Wording:** Labels reflect “K1 orchestrates; K0 persists/enforces”; phrasing is neutral (“via K0 recall/write”).
5. **SSE:** Broadcast/subscribe paths explicitly show `… → K0_BRIDGE_D2 → SSE_D2`.
6. **Cross-diagram:** Only the three anchors remain; D2 defers all K0 internals to D1.
7. **Legend & Styles:** Bridge and K0 ports visually distinct; legend present.

---

## Quick Execution Order (if you want a rapid pass)

1. **Add `K0_BRIDGE_D2` (M1-E1)** → **Rewire all edges** (M1-E2).
2. **Delete K0 internals & drivers** (M2-E3, M3-E5) → **Insert K0 capsule & legends** (M2-E4).
3. **Collapse pipelines to opaque note** (M4-E7/E8).
4. **Normalize wording & SSE flow** (M5-E9/E10).
5. **Conformance sweep & comments** (M6-E11/E12).
6. **Tidy visuals & legends** (M8-E14/E15).
7. **Check anchors vs D1/D3** (M7-E13).

---

If you want, I can also produce a **ready-to-paste Mermaid diff** for M1–M2 (bridge insertion + K0 collapse) in one shot next.
