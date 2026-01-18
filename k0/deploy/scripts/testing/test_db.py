import sqlite3

conn = sqlite3.connect("d:/familyos/k0/deploy/data/k0_kernel.db")
print("Journal mode:", conn.execute("PRAGMA journal_mode").fetchone())
print(
    "Tables count:",
    conn.execute('SELECT COUNT(*) FROM sqlite_master WHERE type="table"').fetchone(),
)
print(
    "st_device_keys exists:",
    conn.execute(
        'SELECT COUNT(*) FROM sqlite_master WHERE type="table" AND name="st_device_keys"'
    ).fetchone(),
)
try:
    print(
        "Can query st_device_keys:", conn.execute("SELECT COUNT(*) FROM st_device_keys").fetchone()
    )
except Exception as e:
    print("Error querying st_device_keys:", e)
conn.close()
conn.close()
