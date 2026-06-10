import json
import unittest
import uuid

import app_deepseek as app_module


TEST_PREFIX = "codex-meeting"


def _unique_email():
    return f"{TEST_PREFIX}-{uuid.uuid4().hex[:10]}@example.com"


def _unique_username():
    return f"{TEST_PREFIX}-{uuid.uuid4().hex[:8]}"


def _cleanup_test_rows():
    scenario_ids = [
        item[0]
        for item in app_module.db.session.query(app_module.ProductScenario.id)
        .filter(app_module.ProductScenario.product_name.like(f"{TEST_PREFIX}-%"))
        .all()
    ]
    room_ids = [
        item[0]
        for item in app_module.db.session.query(app_module.MeetingRoom.id)
        .filter(app_module.MeetingRoom.scenario_id.in_(scenario_ids or [-1]))
        .all()
    ]
    if room_ids:
        app_module.MeetingRoomMessage.query.filter(
            app_module.MeetingRoomMessage.room_id.in_(room_ids)
        ).delete(synchronize_session=False)
        app_module.MeetingRoomMember.query.filter(
            app_module.MeetingRoomMember.room_id.in_(room_ids)
        ).delete(synchronize_session=False)
        app_module.MeetingRoom.query.filter(
            app_module.MeetingRoom.id.in_(room_ids)
        ).delete(synchronize_session=False)
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


class MeetingRoomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app_module.app.config["TESTING"] = True
        with app_module.app.app_context():
            app_module.ensure_extended_schema()

    def setUp(self):
        self.owner_client = app_module.app.test_client()
        self.member_client = app_module.app.test_client()
        self.third_client = app_module.app.test_client()
        with app_module.app.app_context():
            _cleanup_test_rows()
        self.owner_id = self._register_and_login(self.owner_client)
        self.member_id = self._register_and_login(self.member_client)
        self.third_id = self._register_and_login(self.third_client)

    def tearDown(self):
        with app_module.app.app_context():
            _cleanup_test_rows()

    def _register_and_login(self, client):
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
            user_id = user.id
        response = client.post(
            "/api/login",
            json={"email": email, "password": password},
        )
        self.assertEqual(response.status_code, 200)
        return user_id

    def test_cannot_join_meeting_room_after_meeting_has_started(self):
        create_response = self.owner_client.post(
            "/api/meeting-rooms",
            json={
                "room_name": f"{TEST_PREFIX}-room",
                "topic_title": "轮转发言测试",
                "target_count": 2,
                "product_name": f"{TEST_PREFIX}-product",
                "product_concept": "验证会议开始后的加入限制",
            },
        )
        self.assertEqual(create_response.status_code, 201)
        create_payload = create_response.get_json()
        room_id = create_payload["room"]["id"]
        room_code = create_payload["room"]["room_code"]

        join_response = self.member_client.post(
            "/api/meeting-rooms/join",
            json={"room_code": room_code},
        )
        self.assertEqual(join_response.status_code, 200)

        room_payload = self.owner_client.get(f"/api/meeting-rooms/{room_id}").get_json()
        member_ids = [member["id"] for member in room_payload["members"]]
        order_response = self.owner_client.patch(
            f"/api/meeting-rooms/{room_id}/turn-order",
            json={"member_ids": member_ids},
        )
        self.assertEqual(order_response.status_code, 200)

        start_response = self.owner_client.post(f"/api/meeting-rooms/{room_id}/start")
        self.assertEqual(start_response.status_code, 200)

        late_join_response = self.third_client.post(
            "/api/meeting-rooms/join",
            json={"room_code": room_code},
        )

        self.assertEqual(late_join_response.status_code, 409)
        payload = late_join_response.get_json()
        self.assertIn("会议已经开始", payload.get("error", ""))

        verify_payload = self.owner_client.get(f"/api/meeting-rooms/{room_id}").get_json()
        self.assertEqual(len(verify_payload["members"]), 2)

    def test_waiting_message_post_returns_full_room_bundle_for_immediate_refresh(self):
        create_response = self.owner_client.post(
            "/api/meeting-rooms",
            json={
                "room_name": f"{TEST_PREFIX}-room",
                "topic_title": "等待区消息刷新",
                "target_count": 2,
                "product_name": f"{TEST_PREFIX}-product",
                "product_concept": "验证消息发送后页面可立即刷新",
            },
        )
        self.assertEqual(create_response.status_code, 201)
        room_id = create_response.get_json()["room"]["id"]

        post_response = self.owner_client.post(
            f"/api/meeting-rooms/{room_id}/messages",
            json={"content": "请大家准备开始"},
        )

        self.assertEqual(post_response.status_code, 201)
        payload = post_response.get_json()
        self.assertIn("room", payload)
        self.assertIn("members", payload)
        self.assertIn("messages", payload)
        self.assertIn("discussion", payload)
        self.assertEqual(payload["room"]["id"], room_id)
        self.assertTrue(
            any(message["content"] == "请大家准备开始" for message in payload["messages"])
        )

    def test_update_meeting_room_returns_messages_for_immediate_waiting_room_refresh(self):
        create_response = self.owner_client.post(
            "/api/meeting-rooms",
            json={
                "room_name": f"{TEST_PREFIX}-room",
                "topic_title": "initial-topic",
                "target_count": 2,
                "product_name": f"{TEST_PREFIX}-product",
                "product_concept": "verify topic update returns system message bundle",
            },
        )
        self.assertEqual(create_response.status_code, 201)
        room_id = create_response.get_json()["room"]["id"]

        update_response = self.owner_client.patch(
            f"/api/meeting-rooms/{room_id}",
            json={
                "topic_title": "updated-topic",
                "topic_notes": "notes",
                "discussion_topics": ["topic-1", "topic-2", "topic-3", "topic-4"],
            },
        )

        self.assertEqual(update_response.status_code, 200)
        payload = update_response.get_json()
        self.assertIn("messages", payload)
        self.assertTrue(
            any("updated-topic" in (message.get("content") or "") for message in payload["messages"])
        )

    def test_human_turn_returns_immediately_when_next_speaker_is_ai(self):
        create_response = self.owner_client.post(
            "/api/meeting-rooms",
            json={
                "room_name": f"{TEST_PREFIX}-room",
                "topic_title": "async-ai-turn",
                "target_count": 2,
                "product_name": f"{TEST_PREFIX}-product",
                "product_concept": "verify next AI turn is queued instead of blocking the response",
            },
        )
        self.assertEqual(create_response.status_code, 201)
        room_id = create_response.get_json()["room"]["id"]

        room_payload = self.owner_client.get(f"/api/meeting-rooms/{room_id}").get_json()
        member_ids = [member["id"] for member in room_payload["members"]]
        order_response = self.owner_client.patch(
            f"/api/meeting-rooms/{room_id}/turn-order",
            json={"member_ids": member_ids},
        )
        self.assertEqual(order_response.status_code, 200)

        start_response = self.owner_client.post(f"/api/meeting-rooms/{room_id}/start")
        self.assertEqual(start_response.status_code, 200)

        queued_room_ids = []
        original_enqueue = getattr(app_module, "enqueue_room_ai_turn_worker", None)

        def _capture_enqueue(target_room_id):
            queued_room_ids.append(target_room_id)

        app_module.enqueue_room_ai_turn_worker = _capture_enqueue
        try:
            discussion_response = self.owner_client.post(
                f"/api/meeting-rooms/{room_id}/discussion/messages",
                json={"content": "我先补充一下主要顾虑。"},
            )
        finally:
            if original_enqueue is not None:
                app_module.enqueue_room_ai_turn_worker = original_enqueue

        self.assertEqual(discussion_response.status_code, 200)
        payload = discussion_response.get_json()
        self.assertEqual(payload["room"]["id"], room_id)
        self.assertEqual(queued_room_ids, [room_id])
        self.assertTrue(payload["discussion"]["ai_turn_pending"])
        self.assertEqual(payload["discussion"]["active_speaker"]["speaker_origin"], "ai")
        self.assertEqual(payload["discussion"]["messages"][-1]["content"], "我先补充一下主要顾虑。")


if __name__ == "__main__":
    unittest.main()
