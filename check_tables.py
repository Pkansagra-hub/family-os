import sqlite3

conn = sqlite3.connect("k0_runtime.sqlite3")
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [row[0] for row in cursor.fetchall()]
print("Tables in k0_runtime.sqlite3:")
for table in tables:
    print(f"  - {table}")
conn.close()
conn.close()
