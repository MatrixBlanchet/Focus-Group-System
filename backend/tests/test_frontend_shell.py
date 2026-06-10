import unittest

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
INDEX_HTML = BASE_DIR / "static" / "index.html"


class FrontendShellTests(unittest.TestCase):
    def test_report_entry_uses_new_window_instead_of_same_tab_navigation(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("window.open(`/report?scenario_id=${effectiveScenarioId}&from=report`, '_blank')", html)
        self.assertIn("openDetailedReportPage(currentScenarioId)", html)
        self.assertNotIn("window.location.href = `/report?scenario_id=${currentScenarioId}&from=report`", html)
        self.assertNotIn("onclick=\"window.location.href='/report?scenario_id=${currentScenarioId}'\"", html)

    def test_report_stream_errors_are_exposed_instead_of_becoming_generic_missing_data(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("let reportError = null;", html)
        self.assertIn("} else if (event.type === 'error') {", html)
        self.assertIn("reportError = event.error ||", html)
        self.assertIn("if (reportError) {", html)
        self.assertIn("throw new Error(reportError);", html)

    def test_meeting_room_page_disables_cache_and_forces_reload_after_key_actions(self):
        html = (BASE_DIR / "static" / "meeting-room.html").read_text(encoding="utf-8")

        self.assertIn("cache: 'no-store'", html)
        self.assertIn("await refreshMeetingRoom({ preserveDrafts: true });", html)
        self.assertIn("requestImmediateRoomRefresh(reason).catch(() => {});", html)
        self.assertIn("applyPayload(data, { preserveDrafts: true });", html)

    def test_index_meeting_nav_redirects_to_standalone_meeting_page(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("function openMeetingWorkspacePage()", html)
        self.assertIn("window.location.href = '/meeting-room';", html)
        self.assertIn("if (btn.dataset.panel === 'meeting-room') {", html)
        self.assertIn("openMeetingWorkspacePage();", html)

    def test_standalone_meeting_page_contains_room_entry_hub(self):
        html = (BASE_DIR / "static" / "meeting-room.html").read_text(encoding="utf-8")

        self.assertIn('id="meeting-entry-panel"', html)
        self.assertIn('id="create-room-name-input"', html)
        self.assertIn('id="create-room-topic-input"', html)
        self.assertIn('id="create-room-product-name-input"', html)
        self.assertIn('id="create-room-product-concept-input"', html)
        self.assertIn('id="entry-room-code-input"', html)
        self.assertIn('id="meeting-room-list"', html)

    def test_meeting_room_page_has_fast_room_sync_signal_hooks(self):
        html = (BASE_DIR / "static" / "meeting-room.html").read_text(encoding="utf-8")

        self.assertIn("const MEETING_SYNC_CHANNEL = 'focus-group-meeting-sync';", html)
        self.assertIn("function notifyRoomActivity(reason = 'room_action')", html)
        self.assertIn("function handleRoomSyncSignal(payload)", html)
        self.assertIn("new BroadcastChannel(MEETING_SYNC_CHANNEL)", html)
        self.assertIn("window.addEventListener('storage', (event) => {", html)

    def test_meeting_room_page_animates_new_messages_and_active_speaker(self):
        html = (BASE_DIR / "static" / "meeting-room.html").read_text(encoding="utf-8")

        self.assertIn("@keyframes feedItemEnter", html)
        self.assertIn(".feed-item.feed-item-enter", html)
        self.assertIn('id="active-speaker-banner"', html)
        self.assertIn(".speaker-banner.attention-pulse", html)
        self.assertIn("function pulseActiveSpeakerChange()", html)

    def test_meeting_room_page_handles_pending_ai_turn_and_action_busy_states(self):
        html = (BASE_DIR / "static" / "meeting-room.html").read_text(encoding="utf-8")

        self.assertIn("function setButtonBusy(buttonId, busy, busyLabel, idleLabel)", html)
        self.assertIn("state.pendingStartMeeting = false", html)
        self.assertIn("state.pendingDiscussionSubmit = false", html)
        self.assertIn("state.discussion?.ai_turn_pending", html)
        self.assertIn("AI THINKING", html)

    def test_meeting_room_page_can_generate_report_after_meeting_end(self):
        html = (BASE_DIR / "static" / "meeting-room.html").read_text(encoding="utf-8")

        self.assertIn("function generateMeetingReportAndOpen()", html)
        self.assertIn("state.pendingReportGeneration = false", html)
        self.assertIn("window.open(`/report?scenario_id=${state.scenario.id}&from=meeting&room_id=${state.room.id}&regenerate=1`, '_blank')", html)
        self.assertNotIn("await apiFetch(`${API_BASE}/scenarios/${state.scenario.id}/generate-report`", html)
        self.assertIn("setButtonBusy('open-report-btn', true,", html)

    def test_report_page_uses_stream_generation_and_shows_progress(self):
        html = (BASE_DIR / "static" / "report.html").read_text(encoding="utf-8")

        self.assertIn("function shouldForceRegenerate()", html)
        self.assertIn('id="report-progress-bar"', html)
        self.assertIn('id="report-progress-text"', html)
        self.assertIn("fetch(`${API_BASE}/scenarios/${scenarioId}/generate-report/stream`", html)
        self.assertIn("const reader = response.body.getReader();", html)
        self.assertIn("const decoder = new TextDecoder();", html)
        self.assertIn("if (event.type === 'progress') {", html)
        self.assertIn("function setReportProgress(pct, text)", html)
        self.assertIn("setReportProgress(pct, phaseText);", html)
        self.assertIn("let reportProgressValue = 0;", html)
        self.assertIn("const nextPct = Math.max(reportProgressValue, safePct);", html)
        self.assertIn("document.getElementById('report-progress-bar').style.width = nextPct + '%';", html)
        self.assertIn("if (params.get('from') === 'meeting' && params.get('room_id')) {", html)
        self.assertIn("return `/meeting-room?room_id=${encodeURIComponent(params.get('room_id'))}`;", html)
        self.assertIn("function syncBackButtonLabel()", html)
        self.assertIn("document.getElementById('back-btn').innerHTML = '<i class=\"fas fa-arrow-left\"></i>返回会议室';", html)


if __name__ == "__main__":
    unittest.main()
