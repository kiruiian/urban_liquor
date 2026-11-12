import argparse
import asyncio
from getpass import getpass
import re

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import get_password_hash
from app.modules.auth.models import Staff


async def create_admin(username: str, full_name: str) -> None:
    if not re.fullmatch(r"[a-zA-Z0-9._-]{3,64}", username):
        raise SystemExit("Username must be 3-64 characters: letters, numbers, '.', '_' or '-'.")
    async with AsyncSessionLocal() as session:
        existing_admin = await session.scalar(
            select(Staff.id).where(Staff.role == "admin").limit(1)
        )
        if existing_admin is not None:
            raise SystemExit("An admin account already exists; bootstrap is one-time only.")
        normalized_username = username.strip().lower()
        existing_username = await session.scalar(
            select(Staff.id).where(Staff.username == normalized_username).limit(1)
        )
        if existing_username is not None:
            raise SystemExit("That username is already in use.")

        password = getpass("Admin password (minimum 12 characters): ")
        if len(password) < 12:
            raise SystemExit("Password must be at least 12 characters.")
        confirmation = getpass("Confirm password: ")
        if password != confirmation:
            raise SystemExit("Passwords do not match.")

        session.add(
            Staff(
                username=normalized_username,
                full_name=full_name,
                password_hash=get_password_hash(password),
                role="admin",
                is_active=True,
            )
        )
        await session.commit()
        print(f"Created admin account with username '{normalized_username}'")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the first Urban Liquor POS admin.")
    parser.add_argument("--username", required=True, help="Admin username")
    parser.add_argument("--name", required=True, help="Admin display name")
    args = parser.parse_args()
    asyncio.run(create_admin(args.username.strip(), args.name.strip()))


if __name__ == "__main__":
    main()
