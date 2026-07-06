# Web Search Tool — Contract-First, Additive Architecture

## Design Principle

This is NOT a feature spec. It is a **contract surface** — a set of interfaces,
registries, and extension points that define *what* web search looks like in K1,
not *where* the code lives. The architecture is **additive**: you add a new
content block type, a new search backend, or a new interaction mode by
registering it against an existing contract — never by taking the whole thing
apart.

Three invariants govern every decision:

1. **Contract-first.** Every surface is a typed contract before it is an
   implementation. Contracts live in the same plane as existing K1 tool
   contracts (`ToolDefinition` → `ActionSpec` → `CapabilityContract`).

2. **Additive, not invasive.** New content block types, search backends, and
   interaction handlers register against extension points. Nothing subclasses a
   god object or patches a dispatch loop.

3. **Separation of concerns.** The tool contract (what can be searched), the
   content block registry (what can be rendered), and the UI component catalog
   (how things look) are three independent surfaces. Each evolves independently.

---

## What "Interactive" Actually Means

When a user asks "best restaurants in Rome?", the experience should be:

```text
┌─────────────────────────────────────────────────────────────────┐
│  🗣️ LLM: "I found 8 top-rated restaurants in Rome!            │
│          Here they are on a map — tap any pin for              │
│          details, or use the filters below."                   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │               🗺️ INTERACTIVE MAP                         │   │
│  │   ┌──────┐                  ┌──────┐                    │   │
│  │   │ 📍   │  La Pergola     │ 📍   │  Roscioli          │   │
│  │   │ ★4.8 │  €€€€          │ ★4.6 │  €€                │   │
│  │   └──────┘                  └──────┘                    │   │
│  │              ┌──────┐                                   │   │
│  │              │ 📍   │  Armando al Pantheon              │   │
│  │              │ ★4.5 │  €€€                              │   │
│  │              └──────┘                                   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  🔽 Filter:  [All]  [€€]  [€€€]  [€€€€]    ★4.5+              │
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                     │
│  │🍝Roscioli│  │🍷LaPergo│  │🍕Armando │  ← swipeable cards   │
│  │ ★4.6  €€ │  │ ★4.8€€€€│  │ ★4.5 €€€ │                     │
│  └──────────┘  └──────────┘  └──────────┘                     │
│                                                                 │
│  USER TAPS "La Pergola" →                                       │
│  🗣️ LLM: "La Pergola is Rome's only 3-star Michelin            │
│          restaurant. Would you like me to check                 │
│          availability for June 15th?"                           │
└─────────────────────────────────────────────────────────────────┘
```

The user **interacts with the map** (zoom, pan, tap pins), **swipes through cards**,
**applies filters**, and their actions **feed back into the conversation**. The LLM
adapts its response based on what the user engaged with. This is a two-way
interaction, not a one-way read pipeline.

---

## Contract Surface 1: The Web Search Tool Contract

Following the K1 pattern (`k1/contracts/tools/*.yaml` → `ToolDefinition` →
`ActionSpec` → `CapabilityContract`), the web search tool exposes a typed
contract surface with exactly **four actions**, each mapping to one Fabric
capability.

### Tool-Level Contract

| Field | Value |
| --- | --- |
| Contract name | `tool.interactive.web_search` |
| Version | `1.0.0` |
| Domain | `SEARCH`, `WEB`, `INTERACTIVE` |
| Kind | `read` (search/browse/refine are reads; close is lifecycle) |
| Safety band | `GREEN` (no system-of-record mutation) |
| Capabilities | `web_search`, `content_rendering`, `user_interaction_feedback` |
| Limitations | `read_only`, `no_state_mutation`, `session_scoped_to_turn` |

### Action Contracts

Each action is an independent `ActionSpec`. Adding a new action (e.g.,
`action="translate"` for translating browsed pages) means adding one
`ActionSpec` to the definition — nothing else changes.

| Action | Kind | Key Inputs | Output |
| --- | --- | --- | --- |
| `search` | `read` | `query` (required), `max_results`, `freshness`, `search_domain`, `content_types`, `interaction_hints` | `{ text_summary, content_blocks[], search_session_id, continuation }` |
| `browse` | `read` | `result_index`, `search_session_id`, `extract_mode` | `{ text_summary, page_content, content_blocks[], continuation }` |
| `refine` | `read` | `query`, `search_session_id`, `content_types` | `{ text_summary, content_blocks[], continuation }` |
| `close` | `compute` | `search_session_id` | `{ summary, sessions_closed }` |

### The Continuation Protocol

The tool uses the existing `ToolResult` envelope's `status` field. It returns
`status: "partial"` when more actions are available, and `status: "ok"` only
on `close`. Each response carries a `continuation` block that tells the caller
what it can do next:

```json
{
  "continuation": {
    "available_actions": ["browse", "refine", "close"],
    "content_block_ids": ["map_abc123", "cards_def456"],
    "hint": "Content blocks are rendering in the UI."
  }
}
```

This is the same protocol family as `BackResultFrame`'s `suggested_next_action`
and the Weave system's `future_weave.triggers`. No new machinery — the
`ToolResult` envelope already supports `"partial"`.

---

## Contract Surface 2: The Content Block Type Registry

This is the **additive extension point**. Content block types are not a static
enum inside the web search tool. They are a **registry** — you add a new type by
registering it. The web search tool asks the registry "what blocks can you build
from these results?" and the registry returns the matching builders.

### The `ContentBlockType` Contract

Every content block type declares:

| Field | Meaning | Example (`"map"`) |
| --- | --- | --- |
| `type_id` | Unique identifier string | `"map"` |
| `schema_version` | Contract version | `"1.0.0"` |
| **Detection** | | |
| `detect_fn` | Given raw results, returns `True` if this block type applies | `has_geolocated_results(results)` → `True` if >50% have lat/lng |
| **Data contract** | | |
| `input_schema` | What raw result fields this block type consumes | `{lat, lng, title, subtitle, rating, price, image_url, address}` |
| `output_schema` | The structured payload the UI receives | `{ center: (lat,lng), zoom: int, markers: [...] }` |
| **Interaction contract** | | |
| `supported_interactions` | What user actions this block emits | `["tap_marker", "pan_map", "zoom_map"]` |
| `interaction_payload_schema` | The shape of each interaction event | `{ marker_id: str, lat: float, lng: float }` for tap_marker |
| **UI contract** | | |
| `default_render_hints` | Default layout/behavior hints the UI component consumes | `{ cluster: true, show_traffic: false }` |

### Pre-Registered Types (M1)

These five types ship registered. Adding a sixth (e.g., `"timeline"` for
chronological results) means defining one contract + one UI component —
nothing in the web search tool changes.

| `type_id` | Detects | Produces | Interactions |
| --- | --- | --- | --- |
| `"map"` | Results with geolocation data | Interactive map with markers, clustering, heatmap layer | `tap_marker`, `pan_map`, `zoom_map` |
| `"cards"` | Listable results with structured fields | Swipeable card list with auto-detected filters | `tap_card`, `filter`, `sort` |
| `"table"` | Comparable results with consistent fields | Sortable comparison table with column types | `tap_row`, `sort_column` |
| `"gallery"` | Image-heavy results | Grid/carousel/masonry layout with lightbox | `tap_image`, `swipe_gallery` |
| `"link_preview"` | Single URL result (typically from `browse`) | Rich link card with thumbnail, site name, description | `tap_link`, `dismiss_preview` |

### How Registration Works (Pattern)

This follows the exact same additive pattern as `FAMILY_TOOL_DEFINITIONS`
in `k1/tools/family/catalog.py`. The web search tool does not know about
individual block types. It iterates the registry:

```text
for block_type in ContentBlockTypeRegistry.list():
    if block_type.detects(raw_results):
        blocks.append(block_type.build(raw_results))
```

Adding a new type is a one-line register. Removing a type is a one-line
unregister. The tool itself never changes.

---

## Contract Surface 3: The Search Backend Provider Interface

The web search tool does not call a search API directly. It delegates to a
**provider** — a pluggable backend that implements the `SearchBackend`
contract. This is the same pattern as `ILLMPort` (ModelHub adapters) and
`IDispatchPort` (Fabric/Orchestrator adapters) in the concierge.

### The `SearchBackend` Contract

| Method | Input | Output | Purpose |
| --- | --- | --- | --- |
| `search(query, max_results, freshness, domain)` | Search parameters | `SearchResultSet` with ranked results + metadata | Execute a web query |
| `fetch_page(url, extract_mode)` | URL + extraction mode (`full`/`summary`/`snippet`) | `PageContent` with text, title, metadata | Fetch and parse a web page |
| `capabilities()` | — | `SearchBackendCapabilities` (max_results, supported_freshness, content_types_supported) | Declare what this backend can do |

### Why a Provider Interface?

- **Testability**: Swap in a mock backend that returns canned results for
  deterministic E2E tests.
- **Multi-vendor**: Register a Brave Search backend for family-safe results,
  a Google backend for general search, and a local knowledge-base backend
  for offline-first operation.
- **Graceful degradation**: If the primary backend is rate-limited, fall
  back to a secondary backend transparently.
- **Privacy**: A child-safe backend can filter results before they reach
  the LLM or UI.

This is the same hexagonal-port pattern used throughout K1. The tool
depends on the contract, not the implementation.

---

## Dual-Channel Output: Text Path + Rich Path

The web search tool produces **two outputs in parallel** from a single call:

```text
                         ┌─→ text_summary → LLM narrates → UI chat bubble
web_search tool ────────┤
                         └─→ content_blocks → rich channel → UI widgets (map, cards, gallery)
                                                               │
                         ┌─← user taps pin / filters ←────────┘
                         │
                         └─→ interaction event → synthetic message → LLM adapts
```

- **Text path**: A plain-language summary (`text_summary`) flows through the
  normal ReAct loop. The LLM reads it and generates narration.
- **Rich path**: `content_blocks[]` (built by the Content Block Type Registry
  from raw search results) bypass the LLM and emit on a structured content
  channel that the UI subscribes to.
- **Feedback path**: User interactions with rendered widgets emit typed
  interaction events. The Interaction Handler converts these into
  natural-language messages injected into the conversation context —
  the same pattern as `[ASYNC RESULT ARRIVED]` weave injection.

---

## User Interaction Feedback Loop

When the user interacts with a content block, the interaction feeds back
into the conversation as a **synthetic user message**:

| User Action | Synthetic Message Injected |
| --- | --- |
| Taps map pin | `"[USER INTERACTION] The user tapped on 'La Pergola' on the map. Rating: ★4.8, Address: Via Alberto Cadlolo, 101. Price: €€€€. Provide details about this selection and offer contextually relevant next steps."` |
| Applies filter | `"[USER INTERACTION] The user applied filter: price_level = €€€. Update your recommendations based on the filtered results."` |
| Selects a card | `"[USER INTERACTION] The user selected 'Roscioli' from the results. Rating: ★4.6. Provide a detailed summary and suggest related options."` |
| Sorts results | `"[USER INTERACTION] The user sorted results by rating (highest first). Acknowledge the reordering and highlight the top result."` |
| Browses gallery image | `"[USER INTERACTION] The user opened image #3 in the gallery. Caption: 'Interior of La Pergola dining room.' Describe what the user is looking at and provide context."` |

This is the same architectural pattern as the existing Weave system's
`[ASYNC RESULT ARRIVED]` prompt injection. User interactions are just
another form of asynchronous context injection — no new LLM infrastructure
required.

---

## End-to-End Flow

```text
USER: "Best restaurants in Rome?"
  │
  ▼
FRONT LLM calls: web_search(action="search",
                            query="best restaurants Rome 2025",
                            content_types=["map", "cards"])
  │
  ├─→ TEXT PATH ──────────────────────────────────────┐
  │   text_summary: "Found 8 top-rated restaurants.   │
  │   1. La Pergola (★4.8, €€€€) — 3 Michelin stars  │
  │   2. Roscioli (★4.6, €€) — legendary carbonara   │
  │   3. Armando al Pantheon (★4.5, €€€) — classic..."│
  │                                                    │
  │   LLM narrates: "I found 8 top-rated spots!        │
  │   Check the map below — tap any pin for details,   │
  │   or use the filters to narrow by price/rating."   │
  │                                                    │
  └─→ UI chat bubble shows text ───────────────────────┤
                                                       │
  └─→ RICH PATH ───────────────────────────────────────┤
      content_blocks: [                                │
        { type:"map", center:(41.9,12.5), markers:[    │
          {id:"pin_0", lat:41.92, lng:12.45,           │
           title:"La Pergola", subtitle:"★4.8 · €€€€", │
           color:"#gold", data:{...}},                  │
          ...                                          │
        ]},                                            │
        { type:"card_list", cards:[...], filters:[     │
          {key:"price", label:"Price", type:"select"}, │
          {key:"rating", label:"Min Rating", ...}      │
        ]}                                             │
      ]                                                │
                                                       │
  └─→ UI renders interactive map + swipeable cards ────┘
  │
  │   ═══════ USER INTERACTS ═══════
  │
  ▼
USER taps "La Pergola" pin on map
  │
  ▼
INTERACTION HANDLER builds synthetic message:
  "[USER INTERACTION] User tapped 'La Pergola' on map.
   Rating: ★4.8, Price: €€€€, Address: Via Alberto Cadlolo, 101.
   Provide details and suggest next steps."
  │
  ▼
FRONT LLM (new ReAct loop iteration):
  → calls web_search(action="browse", search_session_id="ss_X7k2M",
                     result_index=0, extract_mode="summary")
  → gets detailed info + rich link preview block
  → "La Pergola is Rome's only 3-Michelin-star restaurant,
     located at the Rome Cavalieri Waldorf Astoria. The tasting
     menu is €290/person. Would you like me to check table
     availability for your June trip?"
```

---

## Content Block Lifecycle

```text
CREATED          web_search tool builds blocks via ContentBlockTypeRegistry
  │
  ▼
PUBLISHED        blocks emitted on structured content channel
  │
  ▼
RENDERED         UI resolves block type → renders matching component
  │
  ├─→ INTERACTION   user taps/filters/sorts → synthetic message → LLM
  │
  ├─→ UPDATED       LLM calls web_search again → new blocks supersede old
  │
  └─→ DISMISSED     session closed or turn ended → blocks removed from UI
```

Blocks are scoped to the **turn**. If the LLM calls `web_search` again in
the same turn, new blocks (identified by new block IDs) supersede the
previous ones in the UI.

---

## Design Rationale

### Why NOT route through Back for interactive search?

Through Back (`dispatch_task` → Back worker → `submit_result` → weave →
Front → UI) adds **2–5 seconds** before the user sees anything. Direct
Front tool execution gives **sub-second** time to first widget render.

Reserve the Back path for **deep research** (multi-source analysis,
10+ pages browsed, cross-referencing) where latency is acceptable.

### Why dual output (text + content_blocks)?

The LLM needs text to narrate. The UI needs structured data to render
widgets. These happen **simultaneously** — the user sees the map appear
while the LLM streams narration. Both channels serve different consumers
(LLM vs. human). The text summary is always the fallback for text-only UIs.

### Why user interactions as synthetic messages?

Raw interaction data (`{lat: 41.92, lng: 12.45, type: "tap"}`) is not
useful to an LLM. Converting to natural language (`"User tapped 'La
Pergola' on the map..."`) lets the LLM reason about user intent using
capabilities it already has. Same pattern as Weave's `[ASYNC RESULT
ARRIVED]` prompt injection.

### Why a separate rich content channel?

The existing text output channel carries plain strings. Embedding
structured JSON there would break existing consumers. A parallel channel
lets the UI subscribe independently. Text-only UIs ignore the rich
channel and display the text summary.

### Why action-based sub-commands?

Following the existing `update_narrative` pattern (`action: "switch" |
"resume" | "close"`) means the tool integrates into the ReAct loop with
zero new routing infrastructure. One tool contract, four action contracts,
one registration.

### Why a Content Block Type Registry instead of a static enum?

Because the set of renderable content types is **unbounded**. Today it's
map + cards + table + gallery + link_preview. Tomorrow it's timeline,
chart, 3D model, video player, PDF viewer. Each new type means one new
contract + one new UI component — the web search tool itself never changes.
This is the same additive pattern as `FAMILY_TOOL_DEFINITIONS`.

### Why a Search Backend Provider instead of hardcoded API calls?

Because search backends change. Today it's Brave Search. Tomorrow it's
Google, a local knowledge graph, or a family-private index. The provider
contract is the same hexagonal-port pattern as `ILLMPort` and
`IDispatchPort`. Swap implementations without touching tool logic.

---

## What This Enables Beyond Restaurants

The same three contracts (tool + content block types + search backend)
generalize to any domain where structured results benefit from interactive
rendering:

| Domain | Query Example | Content Blocks |
| --- | --- | --- |
| Travel | "Hotels in Napa under $400" | Map + cards + table |
| Shopping | "Best noise-cancelling headphones" | Cards + table |
| Real Estate | "3BR houses in Austin under $600k" | Map + cards + gallery |
| Events | "Concerts in Chicago this weekend" | Cards + map + link_preview |
| Recipes | "Easy pasta recipes" | Cards + gallery |
| News | "Latest on AI regulation" | Cards + link_preview |
| Local Services | "Plumbers near me with good reviews" | Map + cards |
| Image Search | "Modern living room design ideas" | Gallery + cards |

---

## How This Fits Into Existing K1 Patterns

| Existing Pattern | How `web_search` Uses It |
| --- | --- |
| `ToolDefinition` → `ActionSpec` → `CapabilityContract` | Each action (`search`, `browse`, `refine`, `close`) is an `ActionSpec` that auto-registers as a Fabric capability |
| `FAMILY_TOOL_DEFINITIONS` catalog | `ContentBlockTypeRegistry` is the same additive list pattern — one register per type |
| `ILLMPort` / `IDispatchPort` hexagonal contracts | `SearchBackend` is the same port pattern — the tool depends on the contract, not the implementation |
| Weave `[ASYNC RESULT ARRIVED]` injection | User interactions inject `[USER INTERACTION]` blocks using the same mechanism |
| `ToolResult` envelope with `status: "partial"` | Continuation protocol reuses the existing envelope — `"partial"` already exists |
| `BackResultFrame.suggested_next_action` | `continuation.available_actions` is the same pattern — tells the caller what it can do next |
| `k1/contracts/tools/*.yaml` | Web search gets a YAML contract in the same plane as `discover_capabilities.yaml` and `date_calc.yaml` |


# Web Search Tool — Concrete Specification

> This is the implementation-level spec built on the contract surfaces defined
> in `websearch_tool.md`. It defines **what** gets built, **how** the Front LLM
> interacts with it, and **what stays outside** the LLM's view.

---

## 1. Front LLM ReAct Loop — Keep It Simple

### The Rule

> The Front LLM sees `web_search` as **just another tool** — no different from
> `recall_memory` or `discover_capabilities`. The LLM prompt must NOT describe
> content blocks, rendering logic, UI widgets, or interaction handling.

### What the LLM Sees

The LLM receives a tool declaration in its function catalog. The declaration
fits in ~600 characters — comparable to existing tools:

```text
Tool: web_search
Search the web for current information, facts, or content beyond your
knowledge. Use action='search' to query. Then browse specific results,
refine your search, or close the session when done. The tool returns a
text summary you can narrate from — the user sees richer results
automatically alongside your text.

Parameters:
  action (required): "search" | "browse" | "refine" | "close"
  query: search query string (required for search, refine)
  max_results: 1-20, default 10
  freshness: "day" | "week" | "month" | "any" (default "any")
  search_domain: optional domain filter (e.g. "wikipedia.org")
  result_index: which result to browse, 0-based (required for browse)
  extract_mode: "full" | "summary" | "snippet" (default "full")
  content_types: optional hint — "map","cards","gallery","table","link_preview"
  search_session_id: opaque token from prior calls (required for browse/refine/close)
```

### What the LLM Receives Back

The tool returns a `ToolResult` with `data` containing **only text** from the
LLM's perspective:

```json
{
  "text_summary": "Found 8 top-rated restaurants in Rome:\n1. La Pergola (★4.8, €€€€) — 3 Michelin stars, Rome Cavalieri...\n2. Roscioli (★4.6, €€) — legendary carbonara, Via dei Giubbonari...\n...",
  "search_session_id": "ss_X7k2M",
  "continuation": {
    "available_actions": ["browse", "refine", "close"],
    "hint": "Use browse(result_index=N, search_session_id='ss_X7k2M') to read a page, refine(query=...) to narrow, or close to end."
  }
}
```

The LLM reads `text_summary` exactly like it reads `recall_memory` results or
`discover_capabilities` output. It then decides: narrate to user, browse deeper,
refine the query, or close.

### What the LLM NEVER Sees

| Hidden From LLM | Handled By |
| --- | --- |
| `content_blocks[]` — structured map/card/gallery/table data | Emitted on separate rich-content channel → UI renders |
| User taps on map pins, swipes cards, applies filters | Interaction Handler → synthetic user message injected |
| Search backend selection, rate limiting, caching | `SearchBackend` provider (hexagonal port) |
| Content block type detection and building | `ContentBlockTypeRegistry` |
| Session state lifecycle | In-memory cache scoped to `cognitive_trace_id` |

### ReAct Loop Impact

| Metric | Without web_search | With web_search | Delta |
| --- | --- | --- | --- |
| Tools visible to LLM (STANDARD) | 5 | 6 | +1 tool declaration (~600 chars) |
| Max iterations | 6 | 6 | No change |
| Tool call budget | 400 | 400 | No change |
| Prompt template | Unchanged | Unchanged | No new prompt sections |
| Mode allowlist entries | 5 names | 6 names | +1 string |
| Typical search flow iterations | — | 2–3 (search→browse→narrate) | Fits within budget |

### Iteration Flow Example

```
Iteration 0: LLM calls web_search(action="search", query="best restaurants Rome")
  → Receives text_summary + continuation
  → Decides: need more detail on result #0

Iteration 1: LLM calls web_search(action="browse", result_index=0, search_session_id="...")
  → Receives page content + continuation
  → Decides: enough info, narrate to user

Iteration 2: LLM produces text response (terminal)
  → "La Pergola is Rome's only 3-Michelin-star restaurant. The tasting menu is
     €290/person. I've placed it on the map for you — tap the pin for details.
     Would you like me to check availability for June 15th?"

Iteration 3: LLM calls web_search(action="close", search_session_id="...")
  → Cleans up session. Or tool auto-closes at turn end.
```

The LLM used 3 iterations for search → browse → narrate → close. STANDARD mode
allows 6 iterations. Still 3 iterations available for follow-up.

---

## 2. Tool Contract Spec

Following the pattern of `k1/contracts/tools/*.yaml` and
`k1/tools/family/definition.py`:

### Tool-Level Declaration

```yaml
tool_contract:
  name: "tool.interactive.web_search"
  version: "1.0.0"
  domain:
    - "SEARCH"
    - "WEB"
    - "INTERACTIVE"
  description: >
    Interactive web search producing dual output: a text summary for LLM
    narration (via the standard ReAct tool-result path) and structured
    content blocks for UI rendering (via a parallel rich-content channel).
    Four actions: search, browse, refine, close. Session state is scoped
    to the conversation turn.
  capabilities:
    - "web_search"
    - "page_fetch"
    - "content_rendering"
    - "user_interaction_feedback"
  limitations:
    - "read_only"
    - "no_system_of_record_mutation"
    - "session_scoped_to_turn"
    - "max_results_per_search: 20"
    - "max_page_content_chars: 32000"
    - "max_session_duration: single turn"

  context_precision:
    temporal: "anchor"
    spatial: "optional"
```

### Action: `search`

```yaml
action:
  name: "search"
  kind: "read"
  summary: "Execute a web search query and return ranked results."
  min_band: "GREEN"

  required_inputs:
    - name: "query"
      type: "STRING"
      description: "Search query string. Be specific — include location, year, or domain hints."

  optional_inputs:
    - name: "max_results"
      type: "INTEGER"
      description: "Maximum results to return. Default 10, max 20."
      default: 10
    - name: "freshness"
      type: "STRING"
      description: "Prefer recent results."
      enum: ["day", "week", "month", "any"]
      default: "any"
    - name: "search_domain"
      type: "STRING"
      description: "Restrict search to a specific domain (e.g. 'wikipedia.org', 'nytimes.com')."
    - name: "content_types"
      type: "ARRAY[STRING]"
      description: >
        Hint for what interactive content to prepare for the user.
        Options: "map" (geolocated results), "cards" (list items),
        "gallery" (images), "table" (comparisons), "link_preview" (URL unfurl).
        Omit to auto-detect from result content.
    - name: "interaction_hints"
      type: "OBJECT"
      description: >
        Optional rendering hints for the UI. Properties: allow_user_filter
        (bool, default true), allow_user_sort (bool, default true),
        tap_action ("expand"|"navigate"|"select"|"none", default "expand"),
        primary_action_label (string).

  output:
    type: "object"
    properties:
      text_summary:
        type: "string"
        description: "Plain-language summary for LLM narration. Includes top results with key details."
      content_blocks:
        type: "array"
        description: "Structured content blocks for UI rendering. Emitted on rich-content channel — NOT visible to LLM."
      search_session_id:
        type: "string"
        description: "Opaque session token. Pass to browse/refine/close actions."
      continuation:
        type: "object"
        description: "Available next actions and hints."
        properties:
          available_actions:
            type: "array"
            items: { type: "string", enum: ["browse", "refine", "close"] }
          content_block_ids:
            type: "array"
            items: { type: "string" }
          hint:
            type: "string"
```

### Action: `browse`

```yaml
action:
  name: "browse"
  kind: "read"
  summary: "Fetch and extract content from a specific search result page."
  min_band: "GREEN"

  required_inputs:
    - name: "result_index"
      type: "INTEGER"
      description: "0-based index of the result to browse from the search results."
    - name: "search_session_id"
      type: "STRING"
      description: "Session token from the search call."

  optional_inputs:
    - name: "extract_mode"
      type: "STRING"
      description: "Content extraction depth."
      enum: ["full", "summary", "snippet"]
      default: "full"
      notes: >
        "full": complete page text (up to 32000 chars).
        "summary": AI-generated ~500 word summary.
        "snippet": ~200 character excerpt.

  output:
    type: "object"
    properties:
      text_summary:
        type: "string"
        description: "Extracted page content formatted for LLM consumption."
      page_title:
        type: "string"
      page_url:
        type: "string"
      page_length_chars:
        type: "integer"
      content_blocks:
        type: "array"
        description: "Typically includes a link_preview block for the browsed page."
      continuation:
        type: "object"
```

### Action: `refine`

```yaml
action:
  name: "refine"
  kind: "read"
  summary: "Narrow or change the search query within an existing session."
  min_band: "GREEN"

  required_inputs:
    - name: "query"
      type: "STRING"
      description: "New or refined search query."
    - name: "search_session_id"
      type: "STRING"

  optional_inputs:
    - name: "content_types"
      type: "ARRAY[STRING]"
      description: "Updated content type hints for the refined results."

  output:
    type: "object"
    properties:
      text_summary:
        type: "string"
      content_blocks:
        type: "array"
      continuation:
        type: "object"
```

### Action: `close`

```yaml
action:
  name: "close"
  kind: "compute"
  summary: "End the search session and release in-memory resources."
  min_band: "GREEN"

  required_inputs:
    - name: "search_session_id"
      type: "STRING"

  output:
    type: "object"
    properties:
      summary:
        type: "object"
        properties:
          searches_performed: { type: "integer" }
          pages_browsed: { type: "integer" }
          total_results_explored: { type: "integer" }
          key_pages:
            type: "array"
            items:
              type: "object"
              properties:
                url: { type: "string" }
                title: { type: "string" }
                relevance: { type: "string" }
```

---

## 3. Content Block Type Specs

These are the five pre-registered types in the `ContentBlockTypeRegistry`.
Each type has a **detection function** (should this block be built from these
results?) and a **builder** (produce the structured payload).

### Block Type: `map`

```yaml
content_block_type:
  type_id: "map"
  schema_version: "1.0.0"

  detection:
    rule: "> 50% of results have non-null lat AND lng fields"
    fallback: "Always include if search_domain suggests location intent"

  data_contract:
    center:
      type: "tuple[float, float]"
      description: "Auto-computed centroid of all marker positions"
    zoom:
      type: "integer"
      description: "Auto-computed from marker spread (tight cluster=15, city=13, region=10)"
    markers:
      type: "array"
      items:
        id: { type: "string" }
        lat: { type: "float" }
        lng: { type: "float" }
        title: { type: "string" }
        subtitle: { type: "string" }
        color: { type: "string", description: "Derived from rating or category" }
        data:
          type: "object"
          properties:
            name: { type: "string" }
            rating: { type: "float" }
            price_level: { type: "string" }
            url: { type: "string" }
            image_url: { type: "string" }
            address: { type: "string" }
            phone: { type: "string" }
    cluster:
      type: "boolean"
      description: "True when > 15 markers"

  interaction_contract:
    supported_interactions:
      - tap_marker:
          payload: { marker_id: "string", lat: "float", lng: "float" }
          synthetic_message_template: >
            "[USER INTERACTION] The user tapped on '{title}' on the map.
            Rating: {rating}, Address: {address}, Price: {price_level}.
            Provide details about this selection and offer contextually
            relevant next steps."
      - pan_map:
          payload: { center_lat: "float", center_lng: "float", zoom: "integer" }
          synthetic_message_template: null  # panning is non-conversational
      - zoom_map:
          payload: { zoom: "integer" }
          synthetic_message_template: null  # zooming is non-conversational

  render_hints:
    cluster: true
    show_traffic: false
    default_marker_color: "#3388ff"
    rating_colors:
      ">=4.5": "#FFD700"
      ">=4.0": "#3388ff"
      ">=3.5": "#888888"
      "<3.5": "#cc4444"
```

### Block Type: `cards`

```yaml
content_block_type:
  type_id: "cards"
  schema_version: "1.0.0"

  detection:
    rule: "Results have at least 2 of: title, rating, price_level, image_url, description"
    fallback: "Always include if > 3 results and search is not image-specific"

  data_contract:
    cards:
      type: "array"
      items:
        id: { type: "string" }
        title: { type: "string" }
        subtitle: { type: "string", max_length: 150 }
        image_url: { type: "string", optional: true }
        rating: { type: "float", optional: true }
        price_level: { type: "string", optional: true }
        tags: { type: "array", items: { type: "string" } }
        data:
          type: "object"
          properties:
            url: { type: "string" }
            address: { type: "string" }
            phone: { type: "string" }
            hours: { type: "string" }
    filters:
      type: "array"
      description: "Auto-detected from card data. Built for any field with > 2 distinct values."
      items:
        key: { type: "string" }
        label: { type: "string" }
        type: { enum: ["select", "toggle", "range"] }
        options: { type: "array", items: { label: "string", value: "any" } }
    sort_options:
      type: "array"
      items: { type: "string" }
      description: "Auto-detected from card fields: rating, price, name, distance"
    layout:
      type: "string"
      enum: ["horizontal_scroll", "vertical_grid", "compact_list"]
      default: "horizontal_scroll"

  interaction_contract:
    supported_interactions:
      - tap_card:
          payload: { card_id: "string" }
          synthetic_message_template: >
            "[USER INTERACTION] The user selected '{title}' from the results.
            Rating: {rating}. Provide a detailed summary and suggest related options."
      - filter:
          payload: { filter_key: "string", filter_value: "any" }
          synthetic_message_template: >
            "[USER INTERACTION] The user applied filter: {filter_key} = {filter_value}.
            Update your recommendations based on the filtered results."
      - sort:
          payload: { sort_key: "string" }
          synthetic_message_template: >
            "[USER INTERACTION] The user sorted results by {sort_key}.
            Acknowledge the reordering and highlight the top result."

  render_hints:
    max_cards_visible: 5
    show_rating_stars: true
    show_price_indicators: true
```

### Block Type: `table`

```yaml
content_block_type:
  type_id: "table"
  schema_version: "1.0.0"

  detection:
    rule: "Results have >= 3 consistent structured fields across all items"
    fallback: "Include if user query suggests comparison intent ('compare', 'vs', 'best')"

  data_contract:
    columns:
      type: "array"
      items:
        key: { type: "string" }
        label: { type: "string" }
        type: { enum: ["text", "number", "rating", "price", "image", "link"] }
    rows:
      type: "array"
      items:
        type: "object"
        description: "Key-value pairs matching column keys"
    sortable: { type: "boolean", default: true }
    highlight_row_on_tap: { type: "boolean", default: true }

  interaction_contract:
    supported_interactions:
      - tap_row:
          payload: { row_index: "integer", row_data: "object" }
          synthetic_message_template: >
            "[USER INTERACTION] The user selected row {row_index} from the
            comparison table. Provide details about this item and explain
            how it compares to alternatives."
      - sort_column:
          payload: { column_key: "string", direction: "asc|desc" }
          synthetic_message_template: >
            "[USER INTERACTION] The user sorted the table by {column_key}
            ({direction}). Acknowledge the new ordering."
```

### Block Type: `gallery`

```yaml
content_block_type:
  type_id: "gallery"
  schema_version: "1.0.0"

  detection:
    rule: "> 50% of results have non-null image_url AND result is from image search OR query contains visual intent words"
    fallback: "Include if > 3 results have image_url"

  data_contract:
    images:
      type: "array"
      items:
        id: { type: "string" }
        url: { type: "string" }
        thumbnail_url: { type: "string" }
        caption: { type: "string" }
        source: { type: "string" }
        data: { type: "object" }
    layout:
      type: "string"
      enum: ["grid", "carousel", "masonry"]
      default: "grid"
    columns: { type: "integer", default: 3 }

  interaction_contract:
    supported_interactions:
      - tap_image:
          payload: { image_id: "string", index: "integer" }
          synthetic_message_template: >
            "[USER INTERACTION] The user opened image #{index} in the gallery.
            Caption: '{caption}'. Describe what the user is looking at and
            provide context."
      - swipe_gallery:
          payload: { direction: "left|right", new_index: "integer" }
          synthetic_message_template: null  # swiping is non-conversational
```

### Block Type: `link_preview`

```yaml
content_block_type:
  type_id: "link_preview"
  schema_version: "1.0.0"

  detection:
    rule: "Result is a single URL (typically from browse action)"
    fallback: "Always include for browse action results"

  data_contract:
    url: { type: "string" }
    title: { type: "string" }
    description: { type: "string" }
    thumbnail_url: { type: "string", optional: true }
    site_name: { type: "string", optional: true }
    favicon_url: { type: "string", optional: true }

  interaction_contract:
    supported_interactions:
      - tap_link:
          payload: { url: "string" }
          synthetic_message_template: null  # link navigation handled by UI, not conversation
      - dismiss_preview:
          payload: { url: "string" }
          synthetic_message_template: null
```

---

## 4. Search Backend Provider Contract

Following the hexagonal-port pattern (`ILLMPort`, `IDispatchPort`):

```python
# Conceptual interface — not a literal Python Protocol, but the contract shape

class SearchBackend:
    """Pluggable web search backend. One implementation per search provider."""

    async def search(
        self,
        query: str,
        max_results: int = 10,
        freshness: str = "any",        # "day" | "week" | "month" | "any"
        search_domain: str | None = None,
    ) -> SearchResultSet:
        """
        Returns:
            SearchResultSet:
                query: str
                total_results: int
                results: list[SearchResult]
                    SearchResult:
                        index: int
                        title: str
                        url: str
                        snippet: str
                        domain: str
                        published_date: str | None
                        lat: float | None      # if geolocated
                        lng: float | None      # if geolocated
                        rating: float | None   # if available
                        price_level: str | None
                        image_url: str | None
                        tags: list[str]
                        raw_data: dict          # provider-specific extras
                provider: str                  # "brave", "google", etc.
                latency_ms: int
        """

    async def fetch_page(
        self,
        url: str,
        extract_mode: str = "full",    # "full" | "summary" | "snippet"
    ) -> PageContent:
        """
        Returns:
            PageContent:
                url: str
                title: str
                content: str             # extracted text
                content_length_chars: int
                extract_mode: str
                metadata:
                    site_name: str | None
                    favicon_url: str | None
                    thumbnail_url: str | None
                    published_date: str | None
                    language: str | None
                latency_ms: int
        """

    def capabilities(self) -> SearchBackendCapabilities:
        """
        Returns:
            SearchBackendCapabilities:
                provider_name: str
                max_results_per_query: int
                supported_freshness: list[str]
                supports_domain_filter: bool
                supports_geolocation: bool
                supports_image_search: bool
                rate_limit_remaining: int | None
                rate_limit_reset_s: float | None
        """
```

---

## 5. Interactive Design on Top of the Contract

### The Separation of Concerns

```text
┌─────────────────────────────────────────────────────────────┐
│                    LLM's WORLD (text only)                   │
│                                                              │
│  web_search tool declaration (~600 chars)                    │
│  ToolResult.data.text_summary (plain text)                   │
│  ToolResult.data.continuation (hints for next action)        │
│  Standard ReAct loop: call → read → decide → repeat          │
│                                                              │
│  THE LLM HAS ZERO KNOWLEDGE OF:                              │
│    - Content blocks, maps, cards, galleries                  │
│    - UI rendering, React components, CSS                     │
│    - User interaction events, tap handlers                   │
│    - Rich content channel, bus topics                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ ToolResult.data.content_blocks[]
                              │ (emitted on separate channel)
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 USER'S WORLD (interactive)                   │
│                                                              │
│  UI subscribes to k1.content.rich.v1                         │
│  Receives: [{ type:"map", markers:[...] }, { type:"cards" }]│
│  Renders: interactive map + swipeable card list              │
│  User interacts: taps pin, filters, sorts, swipes           │
│  Interaction events → synthetic messages → LLM context       │
│  LLM responds as if user typed the interaction               │
└─────────────────────────────────────────────────────────────┘
```

### How the User Experience Unfolds

```text
TIME ──────────────────────────────────────────────────────→

t=0.0s  User: "Best restaurants in Rome?"

t=0.1s  Front LLM receives message, enters ReAct loop

t=0.2s  LLM calls: web_search(action="search", query="best restaurants Rome 2025",
                              content_types=["map", "cards"])
        ↓
t=0.5s  Search backend returns results
        ContentBlockTypeRegistry builds map + cards blocks
        ↓
        TWO THINGS HAPPEN SIMULTANEOUSLY:
        ┌─ Text path: text_summary → LLM reads "Found 8 results..."
        └─ Rich path: content_blocks → UI starts rendering map + cards

t=0.6s  USER SEES: Map appearing with pins popping in, cards loading
        (LLM is still reading text_summary, hasn't produced narration yet)

t=1.0s  LLM finishes reading, produces narration:
        "I found 8 top-rated spots! Check the map — tap any pin
         for details, or use the filters to narrow by price."

t=1.2s  USER SEES: Narration text appears below the map
        USER INTERACTS: Scrolls through cards, sees La Pergola (★4.8)

t=2.0s  USER TAPS "La Pergola" pin on map
        ↓
t=2.1s  Interaction Handler: builds synthetic message
        → injected into conversation as new user input

t=2.2s  LLM receives: "[USER INTERACTION] The user tapped on 'La Pergola'
        on the map. Rating: ★4.8, Address: Via Alberto Cadlolo, 101..."

t=2.3s  LLM calls: web_search(action="browse", result_index=0,
                              search_session_id="ss_X7k2M",
                              extract_mode="summary")
        ↓
t=3.0s  Page fetched, summary generated
        LLM receives: page content about La Pergola

t=3.2s  LLM narrates: "La Pergola is Rome's only 3-Michelin-star restaurant,
        located at the Rome Cavalieri Waldorf Astoria. The tasting menu is
        €290/person. Would you like me to check availability for June 15th?"
```

Key observation: **The user was interacting with the map at t=1.2s while the
LLM was still processing at t=1.0s.** The rich content renders in ~0.6s.
The LLM narration streams starting at ~1.0s. They happen in parallel on
different channels.

### User Interaction → Conversation Integration

User interactions are NOT tool calls. They are NOT part of the ReAct loop.
They are **external events** that produce **synthetic user messages**:

```
User taps "La Pergola" pin
  │
  ▼
UI emits: k1.content.interaction.v1
  { block_id: "map_abc", type: "tap_marker", marker_id: "pin_0" }
  │
  ▼
ContentInteractionHandler:
  1. Looks up block in BlockRegistry → finds MapBlock
  2. Finds marker pin_0 → { title: "La Pergola", rating: 4.8, ... }
  3. Applies synthetic_message_template:
     "[USER INTERACTION] The user tapped on 'La Pergola' on the map.
      Rating: ★4.8, Address: Via Alberto Cadlolo, 101.
      Price: €€€€. Provide details and suggest next steps."
  4. Publishes as k1.session.user.input.v1 (same topic as user text input)
  │
  ▼
FSM receives synthetic user input
  → Routes to Front LLM mailbox
  → Front LLM processes it exactly like a user text message
  → LLM may call web_search, recall_memory, or any other tool
  → LLM produces response
```

This means: **the LLM has zero awareness that the input came from a map tap
versus a user typing.** It's just another message in the conversation. The
`[USER INTERACTION]` prefix is a convention (like `[ASYNC RESULT ARRIVED]`)
that helps the LLM distinguish interaction events from user text, but the
mechanism is identical.

---

## 6. Registration Surface

Following the pattern of `FAMILY_TOOL_DEFINITIONS` in
`k1/tools/family/catalog.py`:

```python
# Conceptual — the registration surface is a single append-only list

WEB_SEARCH_ACTIONS: tuple[ActionSpec, ...] = (
    ACTION_SEARCH,
    ACTION_BROWSE,
    ACTION_REFINE,
    ACTION_CLOSE,
)

CONTENT_BLOCK_TYPES: tuple[ContentBlockType, ...] = (
    MAP_BLOCK_TYPE,
    CARDS_BLOCK_TYPE,
    TABLE_BLOCK_TYPE,
    GALLERY_BLOCK_TYPE,
    LINK_PREVIEW_BLOCK_TYPE,
)

# Each ActionSpec auto-registers as one Fabric CapabilityContract.
# Each ContentBlockType registers itself in the ContentBlockTypeRegistry.
# Adding a new action or block type = one line appended to the tuple.
```

### Where Things Go (Pattern, Not Prescription)

| Concern | Follows Pattern Of | Registers Into |
| --- | --- | --- |
| Tool contract (YAML) | `k1/contracts/tools/discover_capabilities.yaml` | Fabric contract registry |
| Action specs (Python) | `k1/tools/family/calendar/definition.py` | `ToolRegistry` → Fabric `CapabilityContract` |
| Content block types | `k1/tools/family/catalog.py` (the tuple pattern) | `ContentBlockTypeRegistry` |
| Search backend provider | `ILLMPort` / `IDispatchPort` hexagonal ports | Tool implementation dependency injection |
| Concierge tool integration | Existing `schemas_front.py` + `implementations.py` + `mode.py` | `FRONT_TOOL_SCHEMAS`, `TOOL_REGISTRY`, `TOOL_ALLOWLIST` |
| UI components | `ui/` component catalog | UI renderer registry (maps `type_id` → React component) |
| Rich content channel | `k1.response.stream.v1` / `k1.response.final.v1` bus topics | Bus topic `k1.content.rich.v1` |
| Interaction handler | Weave `[ASYNC RESULT ARRIVED]` injection | Bus topic `k1.content.interaction.v1` → synthetic user message |

---

## 7. Open Questions (Not Blocking M1)

1. **Multiple concurrent search sessions?** Per-turn, one session at a time
   is sufficient. Multi-session (comparing results from two queries) is a
   future optimization.

2. **Search session persistence across turns?** M1: session dies at turn end.
   Future: persist session to SS so the user can say "go back to that search
   from earlier."

3. **Child-safe search?** The `SearchBackend` provider contract supports a
   child-safe implementation that filters results. Not in M1 scope.

4. **Rate limiting / quota?** Exposed via `SearchBackend.capabilities()`.
   The tool implementation checks before calling.

5. **Offline / cached results?** A `CachingSearchBackend` decorator can wrap
   any backend. Same pattern as `ILLMPort` caching in ModelHub.

6. **Deep research mode (10+ pages)?** Route through Back via `dispatch_task`
   as described in the design document. Not in M1 Front-tool scope.
