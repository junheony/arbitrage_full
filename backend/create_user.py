"""Create a test user directly in the database."""
import asyncio
from datetime import datetime

from passlib.context import CryptContext
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.db_models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def create_user():
    """Create test user."""
    async with AsyncSessionLocal() as db:
        # Check if user exists
        result = await db.execute(select(User).where(User.email == "test@example.com"))
        existing_user = result.scalar_one_or_none()

        if existing_user:
            print(f"✓ User already exists: {existing_user.email}")
            print(f"  ID: {existing_user.id}")
            return existing_user

        # Create new user
        hashed_password = pwd_context.hash("testpass123")
        user = User(
            email="test@example.com",
            hashed_password=hashed_password,
            full_name="Test User",
            is_active=True,
            is_superuser=False,
            created_at=datetime.utcnow(),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        print(f"✓ Created user: {user.email}")
        print(f"  ID: {user.id}")
        print(f"  Password: testpass123")
        return user


if __name__ == "__main__":
    asyncio.run(create_user())
