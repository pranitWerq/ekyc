import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.database import async_session_maker
from database.models import User
from routes.auth import get_password_hash
import logging

logger = logging.getLogger(__name__)

async def create_admin(email: str, password: str, full_name: str):
    async with async_session_maker() as db:
        # Check if user exists
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        
        if user:
            logger.info(f"User {email} already exists. Promoting to admin...")
            user.is_admin = True
        else:
            logger.info(f"Creating new admin user: {email}")
            user = User(
                email=email,
                hashed_password=get_password_hash(password),
                full_name=full_name,
                is_admin=True
            )
            db.add(user)
        
        await db.commit()
        logger.info(f"Admin user {email} created/updated successfully.")

if __name__ == "__main__":
    email = "agent@gmail.com"
    password = "password123"
    full_name = "Agent Admin"
    asyncio.run(create_admin(email, password, full_name))
