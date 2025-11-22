"""Update test user password with properly hashed password."""
import sys
sys.path.insert(0, '/Users/max/Documents/개발/arbitrage_full/backend')

from app.auth.password import hash_password
import sqlite3

# Hash the password using the app's hash_password function
new_hashed_password = hash_password("test1234")
print(f"Generated hash: {new_hashed_password}")

# Update the database
conn = sqlite3.connect('arbitrage.db')
cursor = conn.cursor()

cursor.execute("UPDATE users SET hashed_password = ? WHERE email = ?", (new_hashed_password, "test@example.com"))
conn.commit()

print(f"✓ Updated password for test@example.com")
print("  Email: test@example.com")
print("  Password: test1234")

conn.close()
