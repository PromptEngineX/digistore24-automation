import sqlite3

db = sqlite3.connect(r"E:\digiflow_starter\data\digiflow.sqlite3")

run_id = 1791392435
ids = ("54669", "47082", "48719")

cursor = db.execute("""
    DELETE FROM digistore_product_registry
    WHERE run_id = ?
      AND external_id IN (?, ?, ?)
      AND status = "accepted"
""", (run_id, *ids))

db.commit()

print(f"Deleted test registry rows: {cursor.rowcount}")

remaining = db.execute("""
    SELECT external_id, product_name, status, run_id
    FROM digistore_product_registry
    WHERE external_id IN (?, ?, ?)
    ORDER BY external_id
""", ids).fetchall()

print("Remaining matching records:")
for row in remaining:
    print(row)

db.close()
