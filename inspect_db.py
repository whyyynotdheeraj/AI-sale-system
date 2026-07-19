import sqlite3

def inspect():
    conn = sqlite3.connect('ai_sales_os.db')
    cursor = conn.cursor()
    
    # Get tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [t[0] for t in cursor.fetchall()]
    print("Tables in database:", tables)
    
    for table in tables:
        print(f"\n--- Table: {table} ---")
        try:
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [c[1] for c in cursor.fetchall()]
            print("Columns:", columns)
            cursor.execute(f"SELECT * FROM {table} LIMIT 10")
            rows = cursor.fetchall()
            for r in rows:
                print(r)
        except Exception as e:
            print(f"Error reading {table}: {e}")
            
    conn.close()

if __name__ == '__main__':
    inspect()
