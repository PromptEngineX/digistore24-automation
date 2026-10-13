import sqlite3

db = sqlite3.connect(r"E:\digiflow_starter\data\digiflow.sqlite3")

rows = db.execute("""
    SELECT external_id, product_name, status, run_id
    FROM digistore_product_registry
    WHERE external_id IN ("54669", "47082", "48719")
    ORDER BY external_id
""").fetchall()

for row in rows:
    print(row)

db.close()
