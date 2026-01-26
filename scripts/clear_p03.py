"""Clear P03 data for fresh test."""

import sqlite3

conn = sqlite3.connect("/data/k0.db")
cursor = conn.cursor()

# Clear P03 tables
tables = [
    "st_kg_dom",
    "st_kg_edges",
    "st_kg_entity_aliases",
    "st_embedding_queue",
]

for table in tables:
    cursor.execute(f"DELETE FROM {table}")
    print(f"Cleared {table}: {cursor.rowcount} rows")

# Reset P03 watermarks
cursor.execute("DELETE FROM st_pipeline_watermarks WHERE pipeline_id = 'P03'")
print(f"Reset P03 watermarks: {cursor.rowcount} rows")

conn.commit()
conn.close()
print("Done - P03 data cleared.")
