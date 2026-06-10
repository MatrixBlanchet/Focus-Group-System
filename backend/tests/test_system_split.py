import json
import unittest
import uuid
from unittest import mock

import app_deepseek as app_module


TEST_PREFIX = "codex-split"


def _unique_email():
    return f"{TEST_PREFIX}-{uuid.uuid4().hex[:10]}@example.com"


def _unique_username():
    return f"{TEST_PREFIX}-{uuid.uuid4().hex[:8]}"


def _cleanup_test_rows():
    room_ids = [
        item[0]
        for item in app_module.db.session.query(app_module.MeetingRoom.id)
        .filter(app_module.MeetingRoom.room_name.like(f"{TEST_PREFIX}-%"))
        .all()
    ] if hasattr(app_module, "MeetingRoom") else []
    if room_ids and hasattr(app_module, "MeetingRoomMessage"):
        app_module.MeetingRoomMessage.query.filter(
            app_module.MeetingRoomMessage.room_id.in_(room_ids)
        ).delete(synchronize_session=False)
    if room_ids and hasattr(app_module, "MeetingRoomMember"):
        app_module.MeetingRoomMember.query.filter(
            app_module.MeetingRoomMember.room_id.in_(room_ids)
        ).delete(synchronize_session=False)
    if room_ids and hasattr(app_module, "MeetingRoom"):
        app_module.MeetingRoom.query.filter(
            app_module.MeetingRoom.id.in_(room_ids)
        ).delete(synchronize_session=False)

    scenario_ids = [
        item[0]
        for item in app_module.db.session.query(app_module.ProductScenario.id)
        .filter(app_module.ProductScenario.product_name.like(f"{TEST_PREFIX}-%"))
        .all()
    ]
    if scenario_ids:
        app_module.ResearchRound.query.filter(
            app_module.ResearchRound.scenario_id.in_(scenario_ids)
        ).delete(synchronize_session=False)
        app_module.AnalysisReport.query.filter(
            app_module.AnalysisReport.scenario_id.in_(scenario_ids)
        ).delete(synchronize_session=False)
        app_module.ConversationRecord.query.filter(
            app_module.ConversationRecord.scenario_id.in_(scenario_ids)
        ).delete(synchronize_session=False)
        app_module.VirtualParticipant.query.filter(
            app_module.VirtualParticipant.scenario_id.in_(scenario_ids)
        ).delete(synchronize_session=False)
        app_module.ExternalEvidence.query.filter(
            app_module.ExternalEvidence.scenario_id.in_(scenario_ids)
        ).delete(synchronize_session=False)
        app_module.ProductScenario.query.filter(
            app_module.ProductScenario.id.in_(scenario_ids)
        ).delete(synchronize_session=False)

    app_module.User.query.filter(
        app_module.User.email.like(f"{TEST_PREFIX}-%")
    ).delete(synchronize_session=False)
    app_module.User.query.filter(
        app_module.User.username.like(f"{TEST_PREFIX}-%")
    ).delete(synchronize_session=False)
    app_module.db.session.commit()


class SystemSplitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app_module.app.config["TESTING"] = True
        with app_module.app.app_context():
            app_module.ensure_extended_schema()

    def setUp(self):
        self.client = app_module.app.test_client()
        with app_module.app.app_context():
            _cleanup_test_rows()

        self.email = _unique_email()
        self.password = "Password123"
        self.username = _unique_username()
        with app_module.app.app_context():
            user, error_message, status = app_module.register_user_account(
                self.username,
                self.email,
                self.password,
            )
            self.assertIsNone(error_message)
            self.assertEqual(status, 201)
            self.user_id = user.id

        login_response = self.client.post(
            "/api/login",
            json={"email": self.email, "password": self.password},
        )
        self.assertEqual(login_response.status_code, 200)

    def tearDown(self):
        with app_module.app.app_context():
            _cleanup_test_rows()

    def _register_and_login_user(self):
        client = app_module.app.test_client()
        email = _unique_email()
        password = "Password123"
        username = _unique_username()
        with app_module.app.app_context():
            user, error_message, status = app_module.register_user_account(
                username,
                email,
                password,
            )
            self.assertIsNone(error_message)
            self.assertEqual(status, 201)
            user_id = user.id

        login_response = client.post(
            "/api/login",
            json={"email": email, "password": password},
        )
        self.assertEqual(login_response.status_code, 200)
        return client, user_id

    def _create_standalone_scenario(self):
        response = self.client.post(
            "/api/scenarios",
            json={
                "product_name": f"{TEST_PREFIX}-standalone-product",
                "product_concept": "Standalone scenario for split-system verification.",
                "core_selling_points": ["ease", "speed"],
                "discussion_topics": ["fit", "risk"],
                "occasion_type": "focus_group",
                "occasion_description": "Standalone flow only",
                "research_goal": "Verify split behavior",
                "decision_problem": "Should the standalone flow remain independent?",
            },
        )
        self.assertEqual(response.status_code, 201)
        return response.get_json()

    def _create_meeting_room(self, client=None, **overrides):
        effective_client = client or self.client
        payload = {
            "room_name": f"{TEST_PREFIX}-room",
            "topic_title": "Meeting-only discussion",
            "topic_notes": "Waiting room and turn-based flow.",
            "target_count": 3,
            "product_name": f"{TEST_PREFIX}-meeting-product",
            "product_concept": "Internal draft for meeting room only.",
            "core_selling_points": ["coordination", "structure"],
            "discussion_topics": ["sequence", "decision"],
            "occasion_type": "focus_group",
            "occasion_description": "Meeting room only",
            "research_goal": "Verify meeting flow separation",
            "decision_problem": "Should meeting room drafts stay hidden?",
        }
        payload.update(overrides)
        response = effective_client.post("/api/meeting-rooms", json=payload)
        self.assertEqual(response.status_code, 201)
        return response.get_json()

    def test_get_scenarios_returns_only_standalone_scenarios(self):
        standalone = self._create_standalone_scenario()
        meeting = self._create_meeting_room()

        response = self.client.get("/api/scenarios")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        scenario_ids = {item["id"] for item in payload}
        self.assertIn(standalone["id"], scenario_ids)
        self.assertNotIn(meeting["scenario"]["id"], scenario_ids)
        returned_statuses = {item["meeting_status"] for item in payload}
        self.assertEqual(returned_statuses, {"standalone"})

    def test_standalone_scenario_can_generate_participants(self):
        scenario = self._create_standalone_scenario()
        fake_personas = [
            {
                "persona_name": "User A",
                "persona_tags": ["buyer"],
                "personality": "cautious",
                "background": "Tests the standalone flow.",
                "usage_goal": "Validate fit",
                "budget_sensitivity": "medium",
                "brand_preference": "",
                "risk_aversion": "high",
                "decision_style": "balanced",
                "deal_breakers": ["slow rollout"],
                "stance_summary": "Needs proof before rollout.",
            }
        ]

        with mock.patch.object(app_module, "call_deepseek", return_value=json.dumps(fake_personas, ensure_ascii=False)):
            response = self.client.post(
                f"/api/scenarios/{scenario['id']}/generate-participants",
                json={"count": 1},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(len(payload["participants"]), 1)
        self.assertEqual(payload["participants"][0]["persona_name"], "User A")

    def test_meeting_room_scenario_rejects_standalone_only_routes(self):
        meeting = self._create_meeting_room()
        scenario_id = meeting["scenario"]["id"]

        endpoints = [
            ("post", f"/api/scenarios/{scenario_id}/generate-participants", {}),
            ("get", f"/api/scenarios/{scenario_id}/participants", None),
            ("post", f"/api/scenarios/{scenario_id}/participants", {"persona_name": "X"}),
            ("get", f"/api/scenarios/{scenario_id}/simulate/stream-v2", None),
            ("post", f"/api/scenarios/{scenario_id}/conversation", {"content": "hello"}),
            ("delete", f"/api/scenarios/{scenario_id}", None),
        ]

        for method, url, body in endpoints:
            response = getattr(self.client, method)(url, json=body) if body is not None else getattr(self.client, method)(url)
            self.assertEqual(
                response.status_code,
                409,
                msg=f"{method.upper()} {url} should be blocked for meeting-managed scenarios",
            )

    def test_meeting_room_list_returns_owned_and_joined_rooms(self):
        owned_room = self._create_meeting_room(room_name=f"{TEST_PREFIX}-owned-room")

        owner_two_client, _ = self._register_and_login_user()
        joined_room = self._create_meeting_room(
            client=owner_two_client,
            room_name=f"{TEST_PREFIX}-joined-room",
            product_name=f"{TEST_PREFIX}-joined-product",
        )

        join_response = self.client.post(
            "/api/meeting-rooms/join",
            json={"room_code": joined_room["room"]["room_code"]},
        )
        self.assertEqual(join_response.status_code, 200)

        response = self.client.get("/api/meeting-rooms")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        room_ids = {item["room"]["id"] for item in payload["rooms"]}
        self.assertIn(owned_room["room"]["id"], room_ids)
        self.assertIn(joined_room["room"]["id"], room_ids)

    def test_root_route_returns_original_index_shell_instead_of_landing_page(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('id="page-title"', html)
        self.assertIn('data-panel="scenarios"', html)
        self.assertNotIn("把单人产品讨论和会议室系统彻底分开", html)

    def test_meetings_route_reuses_index_shell_with_meeting_workspace_param(self):
        response = self.client.get("/meetings", follow_redirects=False)

        self.assertIn(response.status_code, (301, 302, 303, 307, 308))
        location = response.headers.get("Location", "")
        self.assertIn("/index.html", location)
        self.assertIn("workspace=meeting", location)
