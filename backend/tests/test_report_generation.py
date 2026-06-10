import json
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest import mock

import app_deepseek as app_module


TEST_PREFIX = "codex-report"


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
    app_module.db.session.remove()


def _make_section_one():
    return """- 核心结论：建议继续推进社区与商业场景的小范围验证。
- 目标用户：社区篮球爱好者、培训机构教练、商业场馆管理者。
- 推进判断：价值明确，但必须控制成本和噪音风险。
- 关键风险：训练流程打断、设备回收失败、噪音被放大。
- 下一步：先做低成本原型和试点验证。"""


def _make_section_two(topic_count=4):
    lines = []
    for idx in range(1, topic_count + 1):
        lines.append(
            "\n".join(
                [
                    f"**议题{idx}：关键议题{idx}**",
                    f"- 讨论中的观点：参与者认为议题{idx}直接影响真实使用体验。",
                    f"- 系统判断：议题{idx}需要在试点中量化验证。",
                    f"- 待验证假设：若议题{idx}处理不好，将削弱付费意愿。",
                ]
            )
        )
    return "\n\n".join(lines)


def _make_section_three():
    return """| 分歧维度 | 观点A | 观点B | 当前偏向 | 待验证点 |
| --- | --- | --- | --- | --- |
| 定位 | 偏基础版 | 偏数据增强版 | 基础版优先 | 数据功能是否带来额外付费 |

- 分歧双方：一方强调低成本快速铺开，另一方强调数据能力建立差异化。
- 当前偏向：先做基础版进入真实场景，再决定是否叠加数据模块。
- 仍待验证点：数据增强是否真能显著提升复购和推荐率。"""


def _make_section_four(include_conclusion=True):
    prefix = "- 是否建议继续推进：建议继续推进，但仅限小范围验证。\n" if include_conclusion else ""
    return prefix + """- 原因：讨论显示真实需求存在，但对成本、噪音和维护稳定性仍有明显顾虑。
- 下一步动作：两周内完成可运行原型，选择 3 个试点场地做连续 30 天验证。
- 关键风险：批量成本超出预期、噪音导致负面反馈、场地运维配合度不足。
- 停止条件：若连续试点中用户留存和教练复用意愿均低于预期，则停止扩展投入。"""


def _make_discussion_summary_payload():
    return {
        "core_conclusion": "建议继续推进篮球自动回收器，但先做小范围验证。",
        "continue_recommendation": "建议继续推进，并优先安排试点验证。",
        "target_users": ["社区篮球爱好者", "培训机构教练", "场馆运营方"],
        "key_topics": [
            {
                "topic": "是否值得继续推进",
                "discussion_points": ["参与者认可节省捡球时间的价值"],
                "system_judgment": "产品具备继续验证价值",
                "open_questions": ["维护复杂度是否可控"],
            },
            {
                "topic": "训练场景适配",
                "discussion_points": ["需要兼顾室内外场地"],
                "system_judgment": "场景适配会影响复购意愿",
                "open_questions": ["复杂地面是否稳定回收"],
            },
            {
                "topic": "噪音与维护",
                "discussion_points": ["担心噪音影响训练专注"],
                "system_judgment": "运维体验会直接影响试点结果",
                "open_questions": ["维护周期是否足够长"],
            },
            {
                "topic": "价格接受度",
                "discussion_points": ["用户愿意为明确价值付费"],
                "system_judgment": "需要验证价格和价值是否匹配",
                "open_questions": ["价格上限区间在哪里"],
            },
        ],
        "divergences": [
            {
                "dimension": "推进节奏",
                "side_a": "快速试点",
                "side_b": "先补证据",
                "current_bias": "先做小范围试点",
                "pending_validation": "低噪音和维护稳定性",
            }
        ],
        "key_risks": ["噪音影响训练体验", "维护成本超预期"],
        "next_steps": ["完成原型试点", "补充一线访谈"],
    }


def _make_discussion_summary_text():
    return json.dumps(_make_discussion_summary_payload(), ensure_ascii=False)


class ReportGenerationTests(unittest.TestCase):
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
        with self.client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["username"] = self.username

    def tearDown(self):
        with app_module.app.app_context():
            _cleanup_test_rows()

    def _create_scenario_bundle(self):
        with app_module.app.app_context():
            scenario = app_module.ProductScenario(
                user_id=self.user_id,
                product_name=f"{TEST_PREFIX}-篮球自动回收器",
                product_concept="一款能自动回收篮球并减少训练中断的设备。",
                core_selling_points=json.dumps(["节省捡球时间", "提高训练连续性"], ensure_ascii=False),
                discussion_topics=json.dumps(["是否值得推进", "优先验证哪些场景"], ensure_ascii=False),
                occasion_type="focus_group",
                occasion_description="标准焦点小组讨论",
                research_goal="判断该产品是否值得继续推进",
                decision_problem="当前阶段是否建议进入小范围验证",
                target_user_profile="社区球场用户与培训机构",
                competitor_context="人工捡球和普通回收架",
                validation_assumptions=json.dumps(["用户愿意为连续训练付费"], ensure_ascii=False),
                research_plan="先验证社区场景",
            )
            app_module.db.session.add(scenario)
            app_module.db.session.commit()

            participant = app_module.VirtualParticipant(
                scenario_id=scenario.id,
                persona_name="陈教练",
                persona_tags=json.dumps(["培训机构", "高频使用"], ensure_ascii=False),
                personality="务实谨慎",
                background="常年带青少年训练营。",
                usage_goal="提升训练效率",
            )
            app_module.db.session.add(participant)
            app_module.db.session.flush()

            records = [
                app_module.ConversationRecord(
                    scenario_id=scenario.id,
                    participant_id=-1,
                    content="我觉得这个产品有潜力，但担心维护复杂。",
                    is_host=False,
                ),
                app_module.ConversationRecord(
                    scenario_id=scenario.id,
                    participant_id=participant.id,
                    content="如果噪音太大，会影响训练专注度，但节省捡球时间确实有价值。",
                    is_host=False,
                ),
                app_module.ConversationRecord(
                    scenario_id=scenario.id,
                    participant_id=0,
                    content="请大家重点讨论真实场景中的接受度和付费意愿。",
                    is_host=True,
                ),
            ]
            app_module.db.session.add_all(records)

            evidence = app_module.ExternalEvidence(
                scenario_id=scenario.id,
                title="社区场馆运营访谈",
                evidence_type="market_data",
                source_label="访谈纪要",
                content="运营方关注设备稳定性与维护成本，认为连续训练效率提升有现实价值。",
                strength_level="中",
            )
            app_module.db.session.add(evidence)
            app_module.db.session.commit()
            return scenario.id

    def _create_empty_scenario(self):
        with app_module.app.app_context():
            scenario = app_module.ProductScenario(
                user_id=self.user_id,
                product_name=f"{TEST_PREFIX}-empty-{uuid.uuid4().hex[:6]}",
                product_concept="用于验证报告日志的空讨论场景",
                core_selling_points=json.dumps(["低成本验证"], ensure_ascii=False),
                discussion_topics=json.dumps(["是否值得推进"], ensure_ascii=False),
                occasion_type="focus_group",
                occasion_description="标准焦点小组讨论",
                research_goal="验证报告日志是否记录失败原因",
                decision_problem="当前阶段是否建议继续推进",
                target_user_profile="测试用户",
                competitor_context="暂无",
                validation_assumptions=json.dumps(["需要先有讨论记录"], ensure_ascii=False),
                research_plan="先记录失败原因",
            )
            app_module.db.session.add(scenario)
            app_module.db.session.commit()
            return scenario.id

    def test_generate_analysis_report_bundle_builds_complete_four_section_report(self):
        scenario_id = self._create_scenario_bundle()
        with app_module.app.test_request_context("/api/test"):
            from flask import session

            session["user_id"] = self.user_id
            report_inputs, error_response = app_module.build_report_inputs(scenario_id)
            self.assertIsNone(error_response)

            ai_outputs = iter(
                [
                    _make_discussion_summary_text(),
                    _make_section_one(),
                    _make_section_two(topic_count=4),
                    _make_section_three(),
                    _make_section_four(include_conclusion=True),
                    "建议继续推进小范围验证，最大风险是噪音和维护成本，优先动作是三场地试点。",
                ]
            )

            with mock.patch.object(app_module, "call_deepseek", side_effect=lambda *args, **kwargs: next(ai_outputs)):
                report, report_error = app_module.generate_analysis_report_bundle(report_inputs)

        self.assertIsNone(report_error)
        self.assertIsNotNone(report)
        with app_module.app.app_context():
            saved_report = app_module.AnalysisReport.query.filter_by(scenario_id=scenario_id).first()
            self.assertIsNotNone(saved_report)
            self.assertIn("## 一、核心观点总结", saved_report.content)
            self.assertIn("## 二、关键讨论点分析", saved_report.content)
            self.assertIn("## 三、主要分歧点归纳", saved_report.content)
            self.assertIn("## 四、可行性结论与建议", saved_report.content)
            self.assertIn("建议继续推进", saved_report.content)

    def test_generate_analysis_report_bundle_retries_invalid_section_instead_of_saving_partial_report(self):
        scenario_id = self._create_scenario_bundle()
        with app_module.app.test_request_context("/api/test"):
            from flask import session

            session["user_id"] = self.user_id
            report_inputs, error_response = app_module.build_report_inputs(scenario_id)
            self.assertIsNone(error_response)

            ai_outputs = iter(
                [
                    _make_discussion_summary_text(),
                    _make_section_one(),
                    _make_section_two(topic_count=2),
                    _make_section_two(topic_count=4),
                    _make_section_three(),
                    _make_section_four(include_conclusion=True),
                    "建议继续推进，优先试点并控制噪音和成本。",
                ]
            )

            with mock.patch.object(app_module, "call_deepseek", side_effect=lambda *args, **kwargs: next(ai_outputs)) as mocked_call:
                report, report_error = app_module.generate_analysis_report_bundle(report_inputs)

        self.assertIsNone(report_error)
        self.assertIsNotNone(report)
        self.assertGreaterEqual(mocked_call.call_count, 7)
        with app_module.app.app_context():
            saved_report = app_module.AnalysisReport.query.filter_by(scenario_id=scenario_id).first()
            self.assertIsNotNone(saved_report)
            self.assertGreaterEqual(saved_report.content.count("**议题"), 4)

    def test_generate_analysis_report_bundle_falls_back_when_conclusion_section_never_validates(self):
        scenario_id = self._create_scenario_bundle()
        with app_module.app.test_request_context("/api/test"):
            from flask import session

            session["user_id"] = self.user_id
            report_inputs, error_response = app_module.build_report_inputs(scenario_id)
            self.assertIsNone(error_response)

            ai_outputs = iter(
                [
                    _make_discussion_summary_text(),
                    _make_section_one(),
                    _make_section_two(topic_count=4),
                    _make_section_three(),
                    _make_section_four(include_conclusion=False),
                    _make_section_four(include_conclusion=False),
                    _make_section_four(include_conclusion=False),
                ]
            )

            with mock.patch.object(app_module, "call_deepseek", side_effect=lambda *args, **kwargs: next(ai_outputs)):
                report, report_error = app_module.generate_analysis_report_bundle(report_inputs)

        self.assertIsNotNone(report)
        self.assertIsNone(report_error)
        with app_module.app.app_context():
            saved_report = app_module.AnalysisReport.query.filter_by(scenario_id=scenario_id).first()
            rounds = app_module.ResearchRound.query.filter_by(scenario_id=scenario_id).count()
        self.assertIsNotNone(saved_report)
        self.assertGreaterEqual(rounds, 1)

    def test_validate_report_section_accepts_recommendation_with_continue_validation_wording(self):
        section_spec = next(
            item for item in app_module.REPORT_SECTION_SPECS if item["code"] == "section_recommendation"
        )
        body = """- 建议结论：建议继续进行两周小范围试点验证，再决定是否扩大投入。
- 下一步动作：两周内完成可运行原型，并在 3 个场地做连续 30 天试点。
- 关键风险：批量成本超预期，设备噪音影响场馆体验。
- 停止条件：若试点留存和复用意愿均低于预期，则停止投入。"""

        is_valid, error_message = app_module.validate_report_section(section_spec, body)

        self.assertTrue(is_valid, error_message)

    def test_generate_analysis_report_bundle_emits_fallback_transition_without_restarting_progress(self):
        scenario_id = self._create_scenario_bundle()
        with app_module.app.test_request_context("/api/test"):
            from flask import session

            session["user_id"] = self.user_id
            report_inputs, error_response = app_module.build_report_inputs(scenario_id)
            self.assertIsNone(error_response)

            ai_outputs = iter(
                [
                    _make_section_one(),
                    _make_section_two(topic_count=4),
                    _make_section_three(),
                    _make_section_four(include_conclusion=False),
                    _make_section_four(include_conclusion=False),
                    _make_section_four(include_conclusion=False),
                ]
            )
            progress_events = []

            with mock.patch.object(app_module, "call_deepseek", side_effect=lambda *args, **kwargs: next(ai_outputs)):
                report, report_error = app_module.generate_analysis_report_bundle(
                    report_inputs,
                    progress_callback=lambda stage_code, phase, pct: progress_events.append(stage_code),
                )

        self.assertIsNone(report_error)
        self.assertIsNotNone(report)
        self.assertEqual(progress_events.count("prepare_inputs"), 0)
        self.assertEqual(progress_events.count("section_summary"), 1)
        self.assertEqual(progress_events.count("section_analysis"), 1)
        self.assertEqual(progress_events.count("section_divergence"), 1)
        self.assertEqual(progress_events.count("section_recommendation"), 1)
        self.assertEqual(progress_events.count("finalize_report"), 1)
        self.assertIn("fallback_started", progress_events)
        self.assertLess(progress_events.index("fallback_started"), progress_events.index("finalize_report"))

    def test_generate_analysis_report_bundle_persists_discussion_summary_without_exposing_it_in_to_dict(self):
        scenario_id = self._create_scenario_bundle()
        with app_module.app.test_request_context("/api/test"):
            from flask import session

            session["user_id"] = self.user_id
            report_inputs, error_response = app_module.build_report_inputs(scenario_id)
            self.assertIsNone(error_response)

            ai_outputs = iter(
                [
                    _make_discussion_summary_text(),
                    _make_section_one(),
                    _make_section_two(topic_count=4),
                    _make_section_three(),
                    _make_section_four(include_conclusion=True),
                    "建议继续推进，先做小范围验证并控制维护与噪音风险。",
                ]
            )
            progress_events = []

            with mock.patch.object(app_module, "call_deepseek", side_effect=lambda *args, **kwargs: next(ai_outputs)):
                report, report_error = app_module.generate_analysis_report_bundle(
                    report_inputs,
                    progress_callback=lambda stage_code, phase, pct: progress_events.append(stage_code),
                )

        self.assertIsNone(report_error)
        self.assertIsNotNone(report)
        self.assertIn("discussion_summary", progress_events)
        with app_module.app.app_context():
            saved_report = app_module.AnalysisReport.query.filter_by(scenario_id=scenario_id).first()
            self.assertTrue(getattr(saved_report, "discussion_summary", ""))
            self.assertIn("建议继续推进", getattr(saved_report, "discussion_summary", ""))
            self.assertNotIn("discussion_summary", saved_report.to_dict())

    def test_generate_analysis_report_bundle_falls_back_to_direct_report_when_summary_generation_fails(self):
        scenario_id = self._create_scenario_bundle()
        with app_module.app.test_request_context("/api/test"):
            from flask import session

            session["user_id"] = self.user_id
            report_inputs, error_response = app_module.build_report_inputs(scenario_id)
            self.assertIsNone(error_response)

            ai_outputs = iter(
                [
                    "API Error: summary failed",
                    _make_section_one(),
                    _make_section_two(topic_count=4),
                    _make_section_three(),
                    _make_section_four(include_conclusion=True),
                    "建议继续推进，优先完成试点验证。",
                ]
            )
            progress_events = []

            with mock.patch.object(app_module, "call_deepseek", side_effect=lambda *args, **kwargs: next(ai_outputs)):
                report, report_error = app_module.generate_analysis_report_bundle(
                    report_inputs,
                    progress_callback=lambda stage_code, phase, pct: progress_events.append(stage_code),
                )

        self.assertIsNone(report_error)
        self.assertIsNotNone(report)
        self.assertIn("discussion_summary", progress_events)
        self.assertIn("fallback_to_direct_report", progress_events)
        self.assertEqual(progress_events.count("section_summary"), 1)

    def test_generate_report_stream_emits_discussion_summary_progress_stage(self):
        scenario_id = self._create_scenario_bundle()

        def fake_bundle(report_inputs, progress_callback=None):
            if progress_callback:
                progress_callback("discussion_summary", "生成讨论摘要", 14)
                progress_callback("section_summary", "生成核心观点总结", 24)
                progress_callback("section_analysis", "生成关键讨论点分析", 42)
                progress_callback("section_divergence", "生成主要分歧点归纳", 60)
                progress_callback("section_recommendation", "生成可行性结论与建议", 78)
                progress_callback("finalize_report", "整理摘要并保存报告", 92)
            report = mock.Mock()
            report.to_dict.return_value = {"id": 1, "content": "完整报告"}
            return report, None

        with mock.patch.object(app_module, "generate_analysis_report_bundle", side_effect=fake_bundle):
            response = self.client.get(f"/api/scenarios/{scenario_id}/generate-report/stream")

        payload_text = response.get_data(as_text=True)
        self.assertIn('"stage_code": "discussion_summary"', payload_text)

    def test_local_fallback_report_avoids_placeholder_topics_and_duplicate_risks(self):
        scenario_id = self._create_scenario_bundle()
        with app_module.app.test_request_context("/api/test"):
            from flask import session

            session["user_id"] = self.user_id
            report_inputs, error_response = app_module.build_report_inputs(scenario_id)
            self.assertIsNone(error_response)
            report, report_error = app_module.build_local_fallback_report_bundle(report_inputs)

        self.assertIsNone(report_error)
        self.assertIsNotNone(report)
        self.assertNotIn("关键验证点2", report.content)
        self.assertNotIn("关键验证点3", report.content)
        self.assertNotIn("关键验证点4", report.content)
        self.assertEqual(report.content.count("这个产品的市场会在3年内迅速扩大"), 0)

    def test_build_report_section_prompt_requests_longer_numbered_output(self):
        scenario_id = self._create_scenario_bundle()
        with app_module.app.test_request_context("/api/test"):
            from flask import session

            session["user_id"] = self.user_id
            report_inputs, error_response = app_module.build_report_inputs(scenario_id)
            self.assertIsNone(error_response)

            summary_prompt = app_module.build_report_section_prompt(
                report_inputs,
                app_module.REPORT_SECTION_SPECS[0],
            )
            recommendation_prompt = app_module.build_report_section_prompt(
                report_inputs,
                app_module.REPORT_SECTION_SPECS[3],
            )

        self.assertIn("每个编号小节至少展开 2 句", summary_prompt)
        self.assertIn("**1）核心结论**", summary_prompt)
        self.assertIn("每个编号标题单独成行", recommendation_prompt)
        self.assertIn("不要把多个编号内容挤在同一行", recommendation_prompt)

    def test_local_fallback_report_uses_numbered_blocks_and_compact_table_headers(self):
        scenario_id = self._create_scenario_bundle()
        with app_module.app.test_request_context("/api/test"):
            from flask import session

            session["user_id"] = self.user_id
            report_inputs, error_response = app_module.build_report_inputs(scenario_id)
            self.assertIsNone(error_response)
            report, report_error = app_module.build_local_fallback_report_bundle(report_inputs)

        self.assertIsNone(report_error)
        self.assertIsNotNone(report)
        self.assertIn("**1）核心结论**", report.content)
        self.assertIn("**2）目标用户**", report.content)
        self.assertIn("**1）是否继续推进**", report.content)
        self.assertIn("| 维度 | 观点A | 观点B | 当前偏向 | 验证重点 |", report.content)

    def test_generate_report_stream_emits_real_progress_stages_and_done_payload(self):
        scenario_id = self._create_scenario_bundle()

        def fake_bundle(report_inputs, progress_callback=None):
            if progress_callback:
                progress_callback("prepare_inputs", "准备讨论材料", 8)
                progress_callback("section_summary", "生成核心观点总结", 24)
                progress_callback("section_analysis", "生成关键讨论点分析", 42)
                progress_callback("section_divergence", "生成主要分歧点归纳", 60)
                progress_callback("section_recommendation", "生成可行性结论与建议", 78)
                progress_callback("finalize_report", "整理摘要并保存报告", 92)
            report = mock.Mock()
            report.to_dict.return_value = {"id": 1, "content": "完整报告"}
            return report, None

        with mock.patch.object(app_module, "generate_analysis_report_bundle", side_effect=fake_bundle):
            response = self.client.get(f"/api/scenarios/{scenario_id}/generate-report/stream")

        self.assertEqual(response.status_code, 200)
        payload_text = response.get_data(as_text=True)
        self.assertIn('"type": "progress"', payload_text)
        self.assertIn('"phase": "准备讨论材料"', payload_text)
        self.assertIn('"stage_code": "section_recommendation"', payload_text)
        self.assertIn('"type": "done"', payload_text)


    def test_generate_analysis_report_bundle_falls_back_to_local_report_when_ai_config_is_unavailable(self):
        scenario_id = self._create_scenario_bundle()
        with app_module.app.app_context():
            with app_module.app.test_request_context("/api/test"):
                from flask import session

                session["user_id"] = self.user_id
                report_inputs, error_response = app_module.build_report_inputs(scenario_id)
                self.assertIsNone(error_response)

                with mock.patch.object(app_module, "resolve_runtime_ai_configs", return_value=[]):
                    report, report_error = app_module.generate_analysis_report_bundle(report_inputs)

        self.assertIsNone(report_error)
        self.assertIsNotNone(report)
        with app_module.app.app_context():
            saved_report = app_module.AnalysisReport.query.filter_by(scenario_id=scenario_id).first()
            self.assertIsNotNone(saved_report)
            data = saved_report.to_dict()
        self.assertIn("## 一、核心观点总结", data["content"])
        self.assertIn("## 二、关键讨论点分析", data["content"])
        self.assertIn("## 三、主要分歧点归纳", data["content"])
        self.assertIn("## 四、可行性结论与建议", data["content"])
        self.assertTrue(data["executive_summary"])

    def test_generate_report_route_logs_validation_failure_for_debugging(self):
        scenario_id = self._create_empty_scenario()
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "report_generation.jsonl"
            with mock.patch.object(app_module, "REPORT_EVENT_LOG_PATH", str(log_path)):
                response = self.client.post(f"/api/scenarios/{scenario_id}/generate-report")

            self.assertEqual(response.status_code, 400)
            self.assertTrue(log_path.exists())
            entries = [
                json.loads(line)
                for line in log_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertGreaterEqual(len(entries), 2)
            self.assertEqual(entries[0]["event"], "report_generation_started")
            self.assertEqual(entries[-1]["event"], "report_generation_blocked")
            self.assertEqual(entries[-1]["scenario_id"], scenario_id)
            self.assertIn("请先进行对话模拟", entries[-1]["error"])


    def test_generate_analysis_report_bundle_falls_back_when_ai_generation_fails(self):
        scenario_id = self._create_scenario_bundle()
        with app_module.app.app_context():
            with app_module.app.test_request_context("/api/test"):
                from flask import session

                session["user_id"] = self.user_id
                report_inputs, error_response = app_module.build_report_inputs(scenario_id)
                self.assertIsNone(error_response)

                with mock.patch.object(app_module, "resolve_runtime_ai_configs", return_value=[{"name": "system"}]):
                    with mock.patch.object(app_module, "advance_report_generation", return_value=(None, "API Error: upstream failed", None)):
                        report, report_error = app_module.generate_analysis_report_bundle(report_inputs)

        self.assertIsNone(report_error)
        self.assertIsNotNone(report)
        with app_module.app.app_context():
            saved_report = app_module.AnalysisReport.query.filter_by(scenario_id=scenario_id).first()
            self.assertIsNotNone(saved_report)
            self.assertIn("## 一、核心观点总结", saved_report.content)

    def test_generate_report_stream_emits_first_progress_before_bundle_finishes(self):
        scenario_id = self._create_scenario_bundle()

        def slow_bundle(report_inputs, progress_callback=None):
            if progress_callback:
                progress_callback("prepare_inputs", "鍑嗗璁ㄨ鏉愭枡", 8)
            time.sleep(0.35)
            report = mock.Mock()
            report.to_dict.return_value = {"id": 1, "content": "瀹屾暣鎶ュ憡"}
            return report, None

        with mock.patch.object(app_module, "generate_analysis_report_bundle", side_effect=slow_bundle):
            response = self.client.get(f"/api/scenarios/{scenario_id}/generate-report/stream", buffered=False)
            stream = iter(response.response)
            start = time.perf_counter()
            first_chunk = next(stream).decode("utf-8")
            elapsed = time.perf_counter() - start

        self.assertLess(elapsed, 0.3)
        self.assertIn('"type": "progress"', first_chunk)


if __name__ == "__main__":
    unittest.main()
