import argparse
import asyncio
import re
from getpass import getpass

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import get_password_hash
from app.modules.auth.models import Staff


async def reset_credentials(
    username: str | None,
    is_admin: bool,
    new_username: str | None,
) -> None:
    current_username = username.strip().lower() if username is not None else None
    normalized_new_username = (
        new_username.strip().lower() if new_username is not None else current_username
    )
    if current_username is not None and (
        len(current_username) > 254 or any(character.isspace() for character in current_username)
    ):
        raise SystemExit("Current username must be a non-empty value without spaces.")
    if normalized_new_username is None:
        normalized_new_username = "admin"
    if not re.fullmatch(r"[a-zA-Z0-9._-]{3,64}", normalized_new_username):
        raise SystemExit("New username must be 3-64 characters: letters, numbers, '.', '_' or '-'.")

    password = getpass("New password (minimum 12 characters): ")
    if len(password) < 12:
        raise SystemExit("Password must be at least 12 characters.")
    confirmation = getpass("Confirm new password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match.")

    async with AsyncSessionLocal() as session:
        if is_admin:
            admins = list(
                (
                    await session.scalars(
                        select(Staff)
                        .where(Staff.role == "admin")
                        .order_by(Staff.id)
                        .with_for_update()
                    )
                ).all()
            )
            if not admins:
                raise SystemExit("No admin account found in the database.")
            if len(admins) > 1:
                usernames = ", ".join(admin.username for admin in admins)
                raise SystemExit(
                    f"Multiple admin accounts found ({usernames}); specify one with --username."
                )
            staff = admins[0]
        else:
            staff = await session.scalar(
                select(Staff)
                .where(Staff.username == current_username)
                .with_for_update()
            )
        if staff is None:
            if is_admin:
                raise SystemExit("No admin account found in the database.")
            raise SystemExit(f"No staff account found for username '{current_username}'.")

        if normalized_new_username != current_username:
            existing = await session.scalar(
                select(Staff.id).where(Staff.username == normalized_new_username)
            )
            if existing is not None:
                raise SystemExit(f"Username '{normalized_new_username}' is already in use.")
            staff.username = normalized_new_username

        staff.password_hash = get_password_hash(password)
        await session.commit()
        print(f"Credentials reset for username '{staff.username}'.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reset a staff account password and optionally change its username."
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--username", help="Account's current username")
    target.add_argument(
        "--admin",
        action="store_true",
        help="Target the only admin account (useful when its old username is unknown)",
    )
    parser.add_argument(
        "--new-username",
        help="Optional new username (3-64 letters, numbers, '.', '_' or '-')",
    )
    args = parser.parse_args()
    asyncio.run(reset_credentials(args.username, args.admin, args.new_username))


if __name__ == "__main__":
    main()
