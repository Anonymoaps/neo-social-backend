from sqlalchemy import create_engine, inspect
import os

DATABASE_URL = "sqlite:///neo.db"
engine = create_engine(DATABASE_URL)
inspector = inspect(engine)

try:
    columns = [c['name'] for c in inspector.get_columns('users')]
    required = ['email', 'password', 'verification_code', 'is_verified']
    missing = [c for c in required if c not in columns]

    if missing:
        print(f"FAIL: Missing columns: {missing}")
    else:
        print("SUCCESS: All columns present.")
except Exception as e:
    print(f"ERROR: {e}")
