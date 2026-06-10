import unittest
import uuid
from datetime import datetime
from unittest import mock

import app_deepseek as app_module


TEST_PREFIX = "codex-user-ai"


def _unique_email():
    return f"{TEST_PREFIX}-{uuid.uuid4().hex[:10]}@example.com"


def _unique_username():
    return f"{TEST_PREFIX}-{uuid.uuid4().hex[:8]}"


def _cleanup_test_rows():
    app_module.ProductScenario.query.filter(
        app_module.ProductScenario.product_name.like(f"{TEST_PREFIX}-%")
    ).delete(synchronize_session=False)
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


class UserAiConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app_module.app.config["TESTING"] = True
        with app_module.app.app_context():
            app_module.ensure_extended_schema()

    def setUp(self):
        self.client = app_module.app.test_client()
        self.original_secret = getattr(app_module, "USER_AI_CONFIG_SECRET", None)
        self.original_api_key = getattr(app_module, "DEEPSEEK_API_KEY", None)
        self.original_api_keys = list(getattr(app_module, "DEEPSEEK_API_KEYS", []))
        self.original_base_url = getattr(app_module, "DEEPSEEK_BASE_URL", None)
        self.original_model = getattr(app_module, "MODEL", None)
        setattr(app_module, "USER_AI_CONFIG_SECRET", "codex-test-user-ai-secret")
        setattr(app_module, "DEEPSEEK_API_KEY", "system-default-key")
        setattr(app_module, "DEEPSEEK_API_KEYS", ["system-default-key"])
        setattr(app_module, "DEEPSEEK_BASE_URL", "https://system.example.com")
        setattr(app_module, "MODEL", "system-model")
        with app_module.app.app_context():
            _cleanup_test_rows()

    def tearDown(self):
        setattr(app_module, "USER_AI_CONFIG_SECRET", self.original_secret)
        setattr(app_module, "DEEPSEEK_API_KEY", self.original_api_key)
        setattr(app_module, "DEEPSEEK_API_KEYS", self.original_api_keys)
        setattr(app_module, "DEEPSEEK_BASE_URL", self.original_base_url)
        setattr(app_module, "MODEL", self.original_model)
        with app_module.app.app_context():
            _cleanup_test_rows()

    def _register_and_login(self):
        email = _unique_email()
        username = _unique_username()
        password = "Password123"
        with app_module.app.app_context():
            user, error_message, status = app_module.register_user_account(
                username,
                email,
                password,
            )
            self.assertIsNone(error_message)
            self.assertEqual(status, 201)
            self.assertIsNotNone(user)

        login_response = self.client.post(
            "/api/login",
            json={"email": email, "password": password},
        )
        self.assertEqual(login_response.status_code, 200)
        return email

    def test_user_ai_config_requires_login(self):
        response = self.client.get("/api/user/ai-config")
        self.assertEqual(response.status_code, 401)

    def test_user_ai_config_returns_empty_summary_when_not_configured(self):
        self._register_and_login()

        response = self.client.get("/api/user/ai-config")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["has_config"], False)
        self.assertEqual(payload["key_count"], 0)
        self.assertEqual(payload["masked_keys"], [])
        self.assertEqual(payload["endpoint_url"], "")
        self.assertEqual(payload["model_name"], "")

    def test_user_ai_config_test_accepts_partial_key_success_and_masks_results(self):
        self._register_and_login()

        def fake_post(url, headers=None, json=None, timeout=None):
            auth_header = headers.get("Authorization", "")
            token = auth_header.replace("Bearer ", "")
            if token == "good-key":
                response = mock.Mock()
                response.status_code = 200
                response.json.return_value = {
                    "choices": [{"message": {"content": "ok"}}]
                }
                return response
            response = mock.Mock()
            response.status_code = 401
            response.text = "bad key"
            return response

        with mock.patch.object(app_module.requests, "post", side_effect=fake_post):
            response = self.client.post(
                "/api/user/ai-config/test",
                json={
                    "endpoint_url": "https://user.example.com/v1/chat/completions",
                    "model_name": "user-model",
                    "api_keys": "bad-key\ngood-key",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["valid_key_count"], 1)
        self.assertEqual(payload["invalid_key_count"], 1)
        self.assertTrue(all("good-key" not in item["masked_key"] for item in payload["results"]))
        self.assertTrue(any(item["is_valid"] for item in payload["results"]))

    def test_user_ai_config_save_stores_encrypted_keys_and_summary_only(self):
        email = self._register_and_login()

        def fake_post(url, headers=None, json=None, timeout=None):
            response = mock.Mock()
            response.status_code = 200
            response.json.return_value = {
                "choices": [{"message": {"content": "ok"}}]
            }
            return response

        with mock.patch.object(app_module.requests, "post", side_effect=fake_post):
            save_response = self.client.patch(
                "/api/user/ai-config",
                json={
                    "endpoint_url": "https://user.example.com/v1/chat/completions",
                    "model_name": "user-model",
                    "api_keys": "user-key-1\nuser-key-2",
                },
            )

        self.assertEqual(save_response.status_code, 200)
        payload = save_response.get_json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["config"]["key_count"], 2)
        self.assertNotIn("user-key-1", json_repr(payload))

        with app_module.app.app_context():
            user = app_module.User.query.filter_by(email=email).first()
            self.assertIsNotNone(user)
            encrypted = getattr(user, "ai_api_keys_encrypted", "")
            self.assertTrue(encrypted)
            self.assertNotIn("user-key-1", encrypted)
            self.assertNotIn("user-key-2", encrypted)
            self.assertEqual(getattr(user, "ai_endpoint_url", ""), "https://user.example.com/v1/chat/completions")
            self.assertEqual(getattr(user, "ai_model_name", ""), "user-model")
            self.assertEqual(getattr(user, "ai_config_enabled", False), True)
            self.assertIsInstance(getattr(user, "ai_last_tested_at", None), datetime)

        get_response = self.client.get("/api/user/ai-config")
        self.assertEqual(get_response.status_code, 200)
        summary = get_response.get_json()
        self.assertEqual(summary["key_count"], 2)
        self.assertEqual(len(summary["masked_keys"]), 2)
        self.assertNotIn("user-key-1", json_repr(summary))

    def test_user_ai_config_save_works_without_explicit_secret_config(self):
        self._register_and_login()
        setattr(app_module, "USER_AI_CONFIG_SECRET", None)

        def fake_post(url, headers=None, json=None, timeout=None):
            response = mock.Mock()
            response.status_code = 200
            response.json.return_value = {
                "choices": [{"message": {"content": "ok"}}]
            }
            return response

        with mock.patch.object(app_module.requests, "post", side_effect=fake_post):
            response = self.client.patch(
                "/api/user/ai-config",
                json={
                    "endpoint_url": "https://user.example.com/v1/chat/completions",
                    "model_name": "user-model",
                    "api_keys": "user-key-1",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "success")

    def test_call_deepseek_uses_user_config_first_and_falls_back_to_system_default(self):
        email = _unique_email()
        username = _unique_username()
        password = "Password123"
        with app_module.app.app_context():
            user, error_message, status = app_module.register_user_account(
                username,
                email,
                password,
            )
            self.assertIsNone(error_message)
            self.assertEqual(status, 201)
            self.assertIsNotNone(user)
            user.ai_endpoint_url = "https://user.example.com/v1/chat/completions"
            user.ai_model_name = "user-model"
            user.ai_config_enabled = True
            user.ai_last_test_status = "success"
            user.ai_api_keys_encrypted = "placeholder"
            app_module.db.session.commit()
            user_id = user.id

        with mock.patch.object(app_module, "decrypt_user_api_keys", return_value=["user-key-1"]), \
             mock.patch.object(app_module.requests, "post") as mock_post, \
             app_module.app.test_request_context("/api/test"):
            from flask import session

            session["user_id"] = user_id

            bad_response = mock.Mock()
            bad_response.status_code = 401
            bad_response.text = "bad key"

            good_response = mock.Mock()
            good_response.status_code = 200
            good_response.json.return_value = {
                "choices": [{"message": {"content": "system fallback ok"}}]
            }

            mock_post.side_effect = [bad_response, good_response]

            result = app_module.call_deepseek("hello", "system")

        self.assertEqual(result, "system fallback ok")
        self.assertEqual(mock_post.call_count, 2)
        first_call = mock_post.call_args_list[0]
        second_call = mock_post.call_args_list[1]
        self.assertEqual(first_call.args[0], "https://user.example.com/v1/chat/completions")
        self.assertEqual(
            first_call.kwargs["headers"]["Authorization"],
            "Bearer user-key-1",
        )
        self.assertEqual(
            second_call.kwargs["headers"]["Authorization"],
            "Bearer system-default-key",
        )

    def test_profile_panel_renders_user_ai_config_controls(self):
        response = self.client.get("/index.html")
        try:
            html = response.get_data(as_text=True)
        finally:
            response.close()

        self.assertIn('id="profile-ai-endpoint-url"', html)
        self.assertIn('id="profile-ai-model-name"', html)
        self.assertIn('id="profile-ai-api-keys"', html)
        self.assertIn('id="test-user-ai-config-btn"', html)
        self.assertIn('id="save-user-ai-config-btn"', html)


def json_repr(value):
    return app_module.json.dumps(value, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
