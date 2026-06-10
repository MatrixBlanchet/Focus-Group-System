import unittest
import uuid
from unittest import mock

import app_deepseek as app_module


TEST_PREFIX = "codex-password-only"


def _unique_email():
    return f"{TEST_PREFIX}-{uuid.uuid4().hex[:10]}@example.com"


def _unique_username():
    return f"{TEST_PREFIX}-{uuid.uuid4().hex[:8]}"


def _cleanup_test_rows():
    app_module.VerificationCode.query.filter(
        app_module.VerificationCode.target.like(f"{TEST_PREFIX}-%")
    ).delete(synchronize_session=False)
    app_module.User.query.filter(
        app_module.User.email.like(f"{TEST_PREFIX}-%")
    ).delete(synchronize_session=False)
    app_module.User.query.filter(
        app_module.User.username.like(f"{TEST_PREFIX}-%")
    ).delete(synchronize_session=False)
    app_module.db.session.commit()


class PasswordOnlyAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app_module.app.config["TESTING"] = True
        with app_module.app.app_context():
            app_module.ensure_extended_schema()

    def setUp(self):
        self.client = app_module.app.test_client()
        with app_module.app.app_context():
            _cleanup_test_rows()

    def tearDown(self):
        with app_module.app.app_context():
            _cleanup_test_rows()

    def test_register_accepts_username_email_and_password_without_code(self):
        response = self.client.post(
            "/api/register",
            json={
                "username": _unique_username(),
                "email": _unique_email(),
                "password": "Password123",
            },
        )

        self.assertEqual(response.status_code, 201)
        payload = response.get_json()
        self.assertEqual(payload["status"], "success")
        self.assertIn("email", payload["user"])

    def test_login_accepts_email_and_password_only(self):
        email = _unique_email()
        password = "Password123"
        with app_module.app.app_context():
            user, error_message, status = app_module.register_user_account(
                _unique_username(),
                email,
                password,
            )
            self.assertIsNone(error_message)
            self.assertEqual(status, 201)
            self.assertIsNotNone(user)

        response = self.client.post(
            "/api/login",
            json={
                "email": email,
                "password": password,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["user"]["email"], email)

    def test_login_rejects_username_after_password_only_switch(self):
        username = _unique_username()
        password = "Password123"
        with app_module.app.app_context():
            user, error_message, status = app_module.register_user_account(
                username,
                _unique_email(),
                password,
            )
            self.assertIsNone(error_message)
            self.assertEqual(status, 201)
            self.assertIsNotNone(user)

        response = self.client.post(
            "/api/login",
            json={
                "target": username,
                "password": password,
            },
        )

        self.assertEqual(response.status_code, 401)
        payload = response.get_json()
        self.assertIn("error", payload)

    def test_send_code_endpoint_returns_success_when_email_verification_enabled(self):
        with mock.patch.object(app_module, "_gen_numeric_code", return_value="111111"), \
             mock.patch.object(app_module, "_send_email", return_value=(True, None)):
            response = self.client.post(
                "/api/auth/send-code",
                json={"target": _unique_email(), "purpose": "login"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["channel"], "email")

    def test_auth_pages_render_active_verification_controls(self):
        register_response = self.client.get("/register.html")
        index_response = self.client.get("/index.html")
        try:
            register_html = register_response.get_data(as_text=True)
            index_html = index_response.get_data(as_text=True)
        finally:
            register_response.close()
            index_response.close()

        self.assertIn('id="register-send-code-btn"', register_html)
        self.assertNotIn('data-verification-disabled="true"', register_html)
        self.assertIn('id="open-reset-btn"', index_html)
        self.assertIn('id="send-reset-code-btn"', index_html)
        self.assertIn('id="auth-method-toggle"', index_html)
        self.assertIn('id="auth-code"', index_html)

    def test_register_page_prevents_duplicate_submit_and_uses_1_5_line_height(self):
        response = self.client.get("/register.html")
        try:
            html = response.get_data(as_text=True)
        finally:
            response.close()

        self.assertIn("let registerSubmitting = false;", html)
        self.assertIn("if (registerSubmitting) {", html)
        self.assertIn("const submitBtn = document.getElementById('register-submit-btn');", html)
        self.assertIn(".hero-copy-title {", html)
        self.assertIn("line-height: 1.5;", html)

    def test_verification_timing_uses_ten_minute_ttl_and_one_minute_cooldown(self):
        self.assertEqual(app_module.VERIFICATION_TTL, 600)
        self.assertEqual(app_module.VERIFICATION_COOLDOWN, 60)

    def test_send_code_register_and_reset_password_flow_can_be_restored(self):
        email = _unique_email()
        username = _unique_username()
        new_password = "Password123"
        reset_password = "Password456"

        with mock.patch.object(app_module, "_gen_numeric_code", return_value="123456"), \
             mock.patch.object(app_module, "_send_email", return_value=(True, None)):
            send_register = self.client.post(
                "/api/auth/send-code",
                json={"target": email, "purpose": "register"},
            )
            self.assertEqual(send_register.status_code, 200)

            register_response = self.client.post(
                "/api/auth/register-with-code",
                json={
                    "target": email,
                    "code": "123456",
                    "username": username,
                    "password": new_password,
                },
            )
            self.assertEqual(register_response.status_code, 201)

            send_reset = self.client.post(
                "/api/auth/send-code",
                json={"target": email, "purpose": "reset_password"},
            )
            self.assertEqual(send_reset.status_code, 200)

            reset_response = self.client.post(
                "/api/auth/reset-password",
                json={
                    "target": email,
                    "code": "123456",
                    "new_password": reset_password,
                },
            )
            self.assertEqual(reset_response.status_code, 200)

        login_response = self.client.post(
            "/api/login",
            json={"email": email, "password": reset_password},
        )
        self.assertEqual(login_response.status_code, 200)
        self.assertEqual(login_response.get_json()["user"]["email"], email)

    def test_login_with_code_can_create_user_on_first_login(self):
        email = _unique_email()

        with mock.patch.object(app_module, "_gen_numeric_code", return_value="654321"), \
             mock.patch.object(app_module, "_send_email", return_value=(True, None)):
            send_response = self.client.post(
                "/api/auth/send-code",
                json={"target": email, "purpose": "login"},
            )
            self.assertEqual(send_response.status_code, 200)

            login_response = self.client.post(
                "/api/auth/login-with-code",
                json={"target": email, "code": "654321"},
            )

        self.assertEqual(login_response.status_code, 200)
        payload = login_response.get_json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["user"]["email"], email)

    def test_change_password_requires_email_verification_code(self):
        email = _unique_email()
        username = _unique_username()
        old_password = "Password123"
        new_password = "Password456"

        with app_module.app.app_context():
            user, error_message, status = app_module.register_user_account(
                username,
                email,
                old_password,
            )
            self.assertIsNone(error_message)
            self.assertEqual(status, 201)
            self.assertIsNotNone(user)

        login_response = self.client.post(
            "/api/login",
            json={"email": email, "password": old_password},
        )
        self.assertEqual(login_response.status_code, 200)

        without_code = self.client.post(
            "/api/user/password",
            json={"old_password": old_password, "new_password": new_password},
        )
        self.assertEqual(without_code.status_code, 400)

        with mock.patch.object(app_module, "_gen_numeric_code", return_value="987654"), \
             mock.patch.object(app_module, "_send_email", return_value=(True, None)):
            send_response = self.client.post(
                "/api/auth/send-code",
                json={"target": email, "purpose": "change_password"},
            )
            self.assertEqual(send_response.status_code, 200)

            change_response = self.client.post(
                "/api/user/password",
                json={
                    "old_password": old_password,
                    "new_password": new_password,
                    "code": "987654",
                },
            )

        self.assertEqual(change_response.status_code, 200)

        relogin_response = self.client.post(
            "/api/login",
            json={"email": email, "password": new_password},
        )
        self.assertEqual(relogin_response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
