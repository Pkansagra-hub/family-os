import json
import os
import tempfile

from k1.fabric.manifest_translator import register_definition_to_store
from k1.fabric.resolver.request_frame import RequestFrame, RequestFrameIntent
from k1.fabric.resolver.situated_resolver import ResolveSituationRequest, ResolveSituationService
from k1.fabric.stores.global_projection_store import GlobalProjectionStore
from k1.tools.family.calendar.definition import CALENDAR_DEFINITION
from k1.tools.family.shopping.definition import SHOPPING_DEFINITION
from k1.tools.family.tasks.definition import TASKS_DEFINITION

tmp = tempfile.mktemp(suffix=".db")
gps = GlobalProjectionStore(tmp)
gps.open()

for d in [SHOPPING_DEFINITION, TASKS_DEFINITION, CALENDAR_DEFINITION]:
    register_definition_to_store(d, gps)
    parts = [d.title or "", d.description or ""]
    for a in d.actions:
        parts.append(a.name or "")
        parts.append(a.summary or "")
    parts.extend(d.domain_tags or [])
    gps.upsert_connector_fts_text(
        d.adapter_id, d.title or "", d.description or "", " ".join(p for p in parts if p)
    )

gps.invalidate_embedding_index()
svc = ResolveSituationService(gps, None)
frame = RequestFrame(
    request_id="r1",
    task_id="t1",
    trace_id="tr1",
    actor_id="u1",
    space_id="f:d",
    intents=[RequestFrameIntent(intent_id="i1", action="add eggs to my shopping list")],
)
req = ResolveSituationRequest(
    request_id="r1",
    frame=frame,
    actor_id="u1",
    space_id="f:d",
    session_id="s1",
    tier="MEDIUM",
    safety_band="GREEN",
)
env = svc.resolve(req)
d = env.to_dict()

print(json.dumps(d, indent=2, default=str))

gps.close()
os.unlink(tmp)
print(json.dumps(d, indent=2, default=str))

gps.close()
os.unlink(tmp)
