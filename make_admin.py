import asyncio
import sys
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.database import async_session_maker
from database.models import User

async def promote_to_admin(email: str):
    async with async_session_maker() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        
        if not user:
            print(f"User with email {email} not found.")
            return
        
        user.is_admin = True
        await db.commit()
        print(f"User {email} has been promoted to Admin.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python make_admin.py <email>")
    else:
        asyncio.run(promote_to_admin(sys.argv[1]))
