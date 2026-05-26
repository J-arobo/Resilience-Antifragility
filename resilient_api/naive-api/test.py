import os
import sqlite3

print("Hello world!")
DB_PATH = os.path.join(os.getcwd(), "naive.db")

def init_db():
    print("how are you?")
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    input_value REAL,
                    result REAL
                )
            """)
            conn.commit()
        print(f"✅ DB initialized at {DB_PATH}")
    except Exception as e:
        print(f"❌ DB init failed: {e}")

# Call the function to initialize the DB
if __name__ == "__main__":
    init_db()
