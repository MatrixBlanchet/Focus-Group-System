import io
import json
import unittest
import uuid
import zipfile
from unittest import mock

import app_deepseek as app_module


TEST_PREFIX = "codex-export"


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


def _sample_report_markdown():
    return """## 一、核心观点总结
- 核心结论：建议继续推进。
- 关键风险：成本与噪音。

## 二、关键讨论点分析
**议题1：需求强度**
- 讨论中的观点：节省捡球时间有价值。
- 系统判断：需要真实场景量化验证。
- 待验证假设：用户愿意为效率付费。

**议题2：噪音控制**
- 讨论中的观点：噪音过大会干扰训练。
- 系统判断：必须先做原型降噪。
- 待验证假设：静音优化能提升接受度。

**议题3：维护复杂度**
- 讨论中的观点：维护频率影响运营意愿。
- 系统判断：需要简化保养动作。
- 待验证假设：非专业人员可在 5 分钟内完成维护。

**议题4：定价策略**
- 讨论中的观点：培训机构与社区用户支付逻辑不同。
- 系统判断：需要分层验证价格。
- 待验证假设：B 端比 C 端更易先付费。

## 三、主要分歧点归纳
| 分歧维度 | 观点A | 观点B | 当前偏向 | 待验证点 |
| --- | --- | --- | --- | --- |
| 定位 | 基础版先行 | 数据版先行 | 基础版 | 数据功能是否提升付费 |

## 四、可行性结论与建议
- 是否建议继续推进：建议继续推进。
- 下一步动作：完成三场地试点。
- 关键风险：成本超预期、噪音投诉。
- 停止条件：试点留存与复用意愿持续过低。"""


class ReportExportAndPresentationTests(unittest.TestCase):
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

    def _create_scenario_with_report(self):
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
            app_module.db.session.flush()

            report = app_module.AnalysisReport(
                scenario_id=scenario.id,
                report_title="篮球自动回收器分析报告",
                content=_sample_report_markdown(),
                executive_summary="建议继续推进三场地试点，优先验证成本、噪音和复用意愿。",
                key_assumptions=json.dumps(["用户愿意为效率付费"], ensure_ascii=False),
                evidence_items=json.dumps(["教练反馈节省训练中断时间"], ensure_ascii=False),
                decision_risks=json.dumps(["噪音投诉", "维护成本"], ensure_ascii=False),
                recommended_actions=json.dumps(["完成三场地试点", "验证降噪方案"], ensure_ascii=False),
                confidence_level="中",
                source_breakdown=json.dumps([
                    {
                        "section": "核心观点总结",
                        "summary": "来自参与者讨论与外部证据汇总",
                        "source_type": "discussion",
                        "strength_level": "中",
                    }
                ], ensure_ascii=False),
            )
            app_module.db.session.add(report)
            app_module.db.session.commit()
            return scenario.id

    def test_report_txt_export_returns_utf8_text_with_key_sections(self):
        scenario_id = self._create_scenario_with_report()

        response = self.client.get(f"/api/scenarios/{scenario_id}/report/txt")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["Content-Type"].startswith("text/plain"))
        payload = response.get_data(as_text=True)
        self.assertIn("篮球自动回收器分析报告", payload)
        self.assertIn("执行摘要", payload)
        self.assertIn("## 一、核心观点总结", payload)
        self.assertIn("## 四、可行性结论与建议", payload)

    def test_report_docx_export_returns_openable_word_package(self):
        scenario_id = self._create_scenario_with_report()

        response = self.client.get(f"/api/scenarios/{scenario_id}/report/docx")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["Content-Type"],
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        package = zipfile.ZipFile(io.BytesIO(response.data))
        self.assertIn("word/document.xml", package.namelist())
        document_xml = package.read("word/document.xml").decode("utf-8")
        self.assertIn("篮球自动回收器分析报告", document_xml)
        self.assertIn("可行性结论与建议", document_xml)

    def test_presentation_prompt_requests_detailed_multi_page_section_breakdown(self):
        scenario_id = self._create_scenario_with_report()

        with app_module.app.app_context():
            report = app_module.AnalysisReport.query.filter_by(scenario_id=scenario_id).first()
            prompt = app_module.build_presentation_prompt(report)

        self.assertIn("10-14", prompt)
        self.assertIn("章节单独拆页", prompt)
        self.assertIn("关键讨论点至少拆成 4 页", prompt)
        self.assertIn("结论与下一步", prompt)

    def test_report_export_returns_404_when_report_missing(self):
        with app_module.app.app_context():
            scenario = app_module.ProductScenario(
                user_id=self.user_id,
                product_name=f"{TEST_PREFIX}-无报告场景",
                product_concept="尚未生成报告。",
                core_selling_points=json.dumps(["占位卖点"], ensure_ascii=False),
                discussion_topics=json.dumps(["占位议题"], ensure_ascii=False),
                occasion_type="focus_group",
                occasion_description="标准焦点小组讨论",
            )
            app_module.db.session.add(scenario)
            app_module.db.session.commit()
            scenario_id = scenario.id

        response = self.client.get(f"/api/scenarios/{scenario_id}/report/txt")

        self.assertEqual(response.status_code, 404)

    def test_presentation_generate_and_fetch_use_existing_report_only(self):
        scenario_id = self._create_scenario_with_report()

        ai_payload = {
            "slides": [
                {"type": "cover", "title": "篮球自动回收器", "subtitle": "决策汇报"},
                {"type": "summary", "title": "执行摘要", "bullets": ["建议继续推进", "先做三场地试点"]},
                {"type": "overview", "title": "核心观点总结", "bullets": ["连续训练场景价值明确", "优先验证高频使用人群", "先小范围试点更稳妥"]},
                {"type": "insight", "title": "关键讨论点：需求强度", "bullets": ["节省捡球时间有价值", "高频训练场景价值最高", "非高频用户付费意愿偏弱"]},
                {"type": "insight", "title": "关键讨论点：噪音控制", "bullets": ["噪音是主要顾虑", "需要先做原型降噪", "训练环境容忍度有限"]},
                {"type": "insight", "title": "关键讨论点：维护复杂度", "bullets": ["维护频率影响运营接受度", "维护动作需要标准化", "非专业人员需能快速上手"]},
                {"type": "insight", "title": "关键讨论点：定价策略", "bullets": ["B 端与 C 端支付逻辑不同", "应分层验证价格", "机构用户更可能先付费"]},
                {"type": "divergence", "title": "主要分歧", "bullets": ["基础版优先", "数据版暂缓", "先验证核心效率价值"]},
                {"type": "risks", "title": "关键风险", "bullets": ["成本超预期", "降噪不达标", "复用意愿不足"]},
                {"type": "actions", "title": "建议动作", "bullets": ["完成三场地试点", "验证降噪方案", "对比不同价格接受度"]},
                {"type": "conclusion", "title": "结论与下一步", "bullets": ["建议继续推进三场地试点", "以高频训练用户为第一验证样本", "若留存持续过低则停止推进"]},
            ]
        }

        with mock.patch.object(app_module, "call_deepseek", return_value=json.dumps(ai_payload, ensure_ascii=False)):
            response = self.client.post(f"/api/scenarios/{scenario_id}/presentation/generate")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "success")
        self.assertGreaterEqual(len(payload["presentation"]["slides"]), 10)
        self.assertEqual(payload["presentation"]["slides"][3]["title"], "关键讨论点：需求强度")

        get_response = self.client.get(f"/api/scenarios/{scenario_id}/presentation")
        self.assertEqual(get_response.status_code, 200)
        saved = get_response.get_json()
        self.assertGreaterEqual(saved["slide_count"], 10)
        self.assertEqual(saved["slides"][0]["type"], "cover")

    def test_presentation_pptx_export_returns_openable_powerpoint_package(self):
        scenario_id = self._create_scenario_with_report()

        ai_payload = {
            "slides": [
                {"type": "cover", "title": "篮球自动回收器", "subtitle": "决策汇报"},
                {"type": "summary", "title": "执行摘要", "bullets": ["建议继续推进", "先做三场地试点"]},
                {"type": "overview", "title": "核心观点总结", "bullets": ["连续训练场景价值明确", "优先验证高频使用人群"]},
                {"type": "insight", "title": "关键讨论点：需求强度", "bullets": ["节省捡球时间有价值", "高频训练价值最高"]},
                {"type": "insight", "title": "关键讨论点：噪音控制", "bullets": ["噪音是主要顾虑", "需要先做原型降噪"]},
                {"type": "insight", "title": "关键讨论点：维护复杂度", "bullets": ["维护动作需标准化", "非专业人员要能快速上手"]},
                {"type": "insight", "title": "关键讨论点：定价策略", "bullets": ["B 端更可能先付费", "价格需分层验证"]},
                {"type": "divergence", "title": "主要分歧", "bullets": ["基础版优先", "数据版暂缓"]},
                {"type": "risks", "title": "关键风险", "bullets": ["成本超预期", "降噪不达标"]},
                {"type": "actions", "title": "建议动作", "bullets": ["完成三场地试点", "验证降噪方案"]},
                {"type": "conclusion", "title": "结论与下一步", "bullets": ["建议继续推进", "若复用意愿持续过低则停止"]},
            ]
        }

        with mock.patch.object(app_module, "call_deepseek", return_value=json.dumps(ai_payload, ensure_ascii=False)):
            generate_response = self.client.post(f"/api/scenarios/{scenario_id}/presentation/generate")
        self.assertEqual(generate_response.status_code, 200)

        response = self.client.get(f"/api/scenarios/{scenario_id}/presentation/pptx")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["Content-Type"],
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
        package = zipfile.ZipFile(io.BytesIO(response.data))
        self.assertIn("ppt/presentation.xml", package.namelist())
        slide_xml = package.read("ppt/slides/slide1.xml").decode("utf-8")
        self.assertIn("篮球自动回收器", slide_xml)

    def test_presentation_generate_rejects_missing_report(self):
        with app_module.app.app_context():
            scenario = app_module.ProductScenario(
                user_id=self.user_id,
                product_name=f"{TEST_PREFIX}-无报告演示稿",
                product_concept="没有报告不能生成演示稿。",
                core_selling_points=json.dumps(["占位卖点"], ensure_ascii=False),
                discussion_topics=json.dumps(["占位议题"], ensure_ascii=False),
                occasion_type="focus_group",
                occasion_description="标准焦点小组讨论",
            )
            app_module.db.session.add(scenario)
            app_module.db.session.commit()
            scenario_id = scenario.id

        response = self.client.post(f"/api/scenarios/{scenario_id}/presentation/generate")

        self.assertEqual(response.status_code, 404)

    def test_report_page_contains_txt_docx_and_presentation_controls(self):
        response = self.client.get("/report.html")
        html = response.get_data(as_text=True)

        self.assertIn('id="export-pdf-btn"', html)
        self.assertIn('id="export-txt-btn"', html)
        self.assertIn('id="export-docx-btn"', html)
        self.assertIn('id="export-pptx-btn"', html)
        self.assertIn('id="generate-presentation-btn"', html)
        self.assertIn('id="open-presentation-btn"', html)

    def test_presentation_page_route_renders_player_shell(self):
        response = self.client.get("/presentation")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="presentation-stage"', html)
        self.assertIn('id="prev-slide-btn"', html)
        self.assertIn('id="next-slide-btn"', html)
        self.assertIn('id="enter-fullscreen-btn"', html)
        self.assertIn('id="presentation-help-btn"', html)
        self.assertIn('id="presentation-help-panel"', html)
        self.assertIn('id="presentation-help-close-btn"', html)


if __name__ == "__main__":
    unittest.main()
