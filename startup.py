"""
Runs once when the app boots. Sets up the database, seeds GL codes,
and generates data only if the database is empty. Safe to run repeatedly.
"""
from database import initialize_database, get_connection

def setup_if_needed():
    initialize_database()

    conn = get_connection()
    cursor = conn.cursor()

    # Check if data already exists
    cursor.execute("SELECT COUNT(*) FROM transactions")
    txn_count = cursor.fetchone()[0]
    conn.close()

    if txn_count == 0:
        print("Empty database detected. Seeding GL codes and generating data...")
        import seed_gl_codes
        seed_gl_codes.seed()
        import generate_data
        generate_data.generate()
        print("Setup complete.")
    else:
        print(f"Database already has {txn_count} transactions. Skipping setup.")

if __name__ == "__main__":
    setup_if_needed()
