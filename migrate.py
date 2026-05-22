"""
migrate.py — Run this ONCE to update the existing database.
Delete this file after running it successfully.

Usage:  python migrate.py
"""
import sqlite3
import os

DB_PATH = os.path.join('instance', 'cafes.db')

conn   = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

print("=" * 50)
print("Café Atlas — Database Migration")
print("=" * 50)

# ── USER TABLE — new profile columns ─────────────────────────────────────────
cursor.execute("PRAGMA table_info(user)")
user_cols = [row[1] for row in cursor.fetchall()]
print(f"\n[USER TABLE] existing columns: {user_cols}")

new_user_cols = {
    'bio':        'TEXT',
    'avatar_url': 'TEXT',
    'location':   'TEXT',
    'website':    'TEXT',
}
for col, dtype in new_user_cols.items():
    if col not in user_cols:
        cursor.execute(f"ALTER TABLE user ADD COLUMN {col} {dtype}")
        print(f"  ✅ Added user.{col}")
    else:
        print(f"  ℹ️  user.{col} already exists — skipping")

# ── CAFE TABLE — added_by ForeignKey is ORM-level only ───────────────────────
print("\n[CAFE TABLE]")
cursor.execute("PRAGMA table_info(cafe)")
cafe_cols = [row[1] for row in cursor.fetchall()]
if 'added_by' in cafe_cols:
    print("  ℹ️  cafe.added_by already exists — ForeignKey is ORM metadata, no SQL change needed")
else:
    cursor.execute("ALTER TABLE cafe ADD COLUMN added_by INTEGER")
    print("  ✅ Added cafe.added_by")

# ── SUBSCRIBER TABLE ──────────────────────────────────────────────────────────
print("\n[SUBSCRIBER TABLE]")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS subscriber (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        email        TEXT NOT NULL UNIQUE,
        is_confirmed INTEGER NOT NULL DEFAULT 0,
        confirmed_at TEXT,
        created_at   TEXT
    )
""")
print("  ✅ subscriber table ready (created if it didn't exist)")

# Count existing rows
cursor.execute("SELECT COUNT(*) FROM subscriber")
sub_count = cursor.fetchone()[0]
print(f"  ℹ️  subscriber table currently has {sub_count} row(s)")

if sub_count > 0:
    cursor.execute("SELECT id, email, is_confirmed FROM subscriber")
    rows = cursor.fetchall()
    for row in rows:
        print(f"     → #{row[0]} {row[1]} confirmed={bool(row[2])}")

# ── FINAL VERIFY ──────────────────────────────────────────────────────────────
print("\n[FINAL VERIFY]")
cursor.execute("PRAGMA table_info(user)")
final_user_cols = [row[1] for row in cursor.fetchall()]
print(f"  user columns : {final_user_cols}")

cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [row[0] for row in cursor.fetchall()]
print(f"  all tables   : {tables}")

# ── COMMIT AND CLOSE ──────────────────────────────────────────────────────────
conn.commit()
conn.close()

print("\n" + "=" * 50)
print("✅ Migration complete!")
print("You can now delete migrate.py and restart Flask.")
print("=" * 50)
