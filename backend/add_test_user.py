"""Add test user directly to SQLite database."""
import sqlite3
from datetime import datetime

# Simple bcrypt hash for password "test1234"
# Generated with: python3 -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('test1234'))"
HASHED_PASSWORD = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/lewJO.7ILWs1Q1Jpu"

conn = sqlite3.connect('arbitrage.db')
cursor = conn.cursor()

# Check if user exists
cursor.execute("SELECT id FROM users WHERE email = ?", ("test@example.com",))
existing = cursor.fetchone()

if existing:
    print(f"✓ User already exists with ID: {existing[0]}")
else:
    # Insert user
    now = datetime.utcnow().isoformat()
    cursor.execute("""
        INSERT INTO users (email, hashed_password, full_name, is_active, is_superuser, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, ("test@example.com", HASHED_PASSWORD, "Test User", 1, 0, now))
    
    user_id = cursor.lastrowid
    print(f"✓ Created user with ID: {user_id}")
    
    # Create default risk limits
    cursor.execute("""
        INSERT INTO risk_limits (user_id, created_at)
        VALUES (?, ?)
    """, (user_id, now))
    
    conn.commit()
    print("✓ User created successfully!")
    print("  Email: test@example.com")
    print("  Password: test1234")

conn.close()
