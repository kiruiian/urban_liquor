import unittest

from fastapi import HTTPException

from app.core.security import get_password_hash
from app.modules.auth.dependencies import require_admin
from app.modules.auth.models import Staff
from app.modules.auth.router import login
from app.modules.auth.schemas import LoginRequest


class AuthTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.password = "correct horse battery staple"
        cls.password_hash = get_password_hash(cls.password)

    def setUp(self) -> None:
        self.admin = Staff(
            id=1,
            username="storeadmin",
            full_name="Store Admin",
            password_hash=self.password_hash,
            role="admin",
            is_active=True,
        )

    async def test_login_normalizes_username_case(self) -> None:
        staff = self.admin

        class Session:
            async def scalar(self, _statement):
                return staff

        response = await login(
            LoginRequest(username="STOREADMIN", password=self.password),
            Session(),
        )

        self.assertTrue(response.access_token)
        self.assertEqual(response.staff.username, "storeadmin")

    async def test_login_rejects_wrong_password(self) -> None:
        staff = self.admin

        class Session:
            async def scalar(self, _statement):
                return staff

        with self.assertRaises(HTTPException) as raised:
            await login(
                LoginRequest(username="storeadmin", password="incorrect password"),
                Session(),
            )

        self.assertEqual(raised.exception.status_code, 401)

    async def test_inactive_staff_cannot_log_in(self) -> None:
        self.admin.is_active = False
        staff = self.admin

        class Session:
            async def scalar(self, _statement):
                return staff

        with self.assertRaises(HTTPException) as raised:
            await login(
                LoginRequest(username="storeadmin", password=self.password),
                Session(),
            )

        self.assertEqual(raised.exception.status_code, 401)

    async def test_cashier_cannot_use_admin_dependency(self) -> None:
        cashier = Staff(
            id=2,
            username="cashier",
            full_name="Cashier",
            password_hash=self.password_hash,
            role="cashier",
            is_active=True,
        )

        with self.assertRaises(HTTPException) as raised:
            await require_admin(cashier)

        self.assertEqual(raised.exception.status_code, 403)
