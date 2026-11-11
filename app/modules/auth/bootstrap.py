import argparse
import asyncio
from getpass import getpass

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import get_password_hash
from app.modules.auth.models import Staff


async def create_owner(email: str, full_name: str) -> None:
    async with AsyncSessionLocal() as session:
        existing_owner = await session.scalar(
            select(Staff.id).where(Staff.role == "owner").limit(1)
        )
        if existing_owner is not None:
            raise SystemExit("An owner account already exists; bootstrap is one-time only.")
        existing_email = await session.scalar(
            select(Staff.id).where(Staff.email == email).limit(1)
        )
        if existing_email is not None:
            raise SystemExit("That email address is already in use.")

        password = getpass("Owner password (minimum 12 characters): ")
        if len(password) < 12:
            raise SystemExit("Password must be at least 12 characters.")
        confirmation = getpass("Confirm password: ")
        if password != confirmation:
            raise SystemExit("Passwords do not match.")

        session.add(
            Staff(
                email=email,
                full_name=full_name,
                password_hash=get_password_hash(password),
                role="owner",
                is_active=True,
            )
        )
        await session.commit()
        print(f"Created owner account for {email}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the first Urban Liquor POS owner.")
    parser.add_argument("--email", required=True, help="Owner email address")
    parser.add_argument("--name", required=True, help="Owner display name")
    args = parser.parse_args()
    asyncio.run(create_owner(args.email.strip().lower(), args.name.strip()))


if __name__ == "__main__":
    main()
