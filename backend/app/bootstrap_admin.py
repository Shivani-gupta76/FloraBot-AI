"""Provision an administrator from a trusted shell after configuring the database."""
from getpass import getpass
from sqlalchemy import select
from app.core.security import hash_password
from app.db.database import SessionLocal
from app.db.models import User, UserRole

email = input("Administrator email: ").strip().lower()
name = input("Administrator name: ").strip()
password = getpass("Administrator password (minimum 10 characters): ")
if len(password) < 10:
    raise SystemExit("Password must be at least 10 characters")
with SessionLocal() as db:
    if db.scalar(select(User.id).limit(1)) is not None:
        raise SystemExit("Provisioning is only allowed while the users table is empty")
    db.add(User(email=email, full_name=name, password_hash=hash_password(password), role=UserRole.admin))
    db.commit()
print("Administrator created.")
