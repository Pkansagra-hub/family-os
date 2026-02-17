"""Planner stage services -- one service per pipeline stage.

Stage services are Layer 2 (Section 30.6): they import Layer 1 ports and
Layer 0 types, but NEVER import Layer 3 (PlannerAgent) or each other.

Modules
-------
sketch_service     -- Stage 1 SKETCH (Section 6, Epic 3.1)
expand_service     -- Stage 2 EXPAND (Section 7, Epic 3.2)
validate_service   -- Stage 3 VALIDATE (Section 8, Epic 3.3)
commit_service     -- Stage 4 COMMIT (Section 9, Epic 3.4)
"""
