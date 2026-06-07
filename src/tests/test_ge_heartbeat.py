import gzip
import json
from unittest.mock import MagicMock, patch

from ge.heartbeat import HeartbeatReporter


class TestHeartbeatReporter:

    def _make_reporter(self):
        cfg = MagicMock()
        cfg.id = "ge-test"
        cfg.heartbeat_url = "http://localhost:8000/api/ge/heartbeat"
        cfg.auth_token = None
        cfg.heartbeat_interval = 10
        slot_mgr = MagicMock()
        slot_mgr.total = 4
        slot_mgr.idle = 3
        client = MagicMock()
        reporter = HeartbeatReporter(cfg, slot_mgr, client)
        return reporter, client, cfg

    def test_initial_state(self):
        reporter, _, _ = self._make_reporter()
        assert reporter.running_task_id is None

    def test_add_and_remove_task_id(self):
        reporter, _, _ = self._make_reporter()
        reporter.add_task_id(101)
        assert reporter.running_task_id == 101
        reporter.add_task_id(102)
        assert reporter.running_task_id in (101, 102)
        reporter.remove_task_id(101)
        assert reporter.running_task_id == 102
        reporter.remove_task_id(102)
        assert reporter.running_task_id is None

    def test_remove_nonexistent(self):
        reporter, _, _ = self._make_reporter()
        reporter.add_task_id(101)
        reporter.remove_task_id(999)
        assert reporter.running_task_id == 101

    def _mock_response(self, client, data: dict):
        mock_resp = MagicMock()
        mock_resp.json.return_value = data
        client.post.return_value = mock_resp

    def test_send_idle(self):
        reporter, client, _ = self._make_reporter()
        self._mock_response(client, {"status": "ok"})
        resp = reporter.send()
        assert resp == {"status": "ok"}
        call_args = client.post.call_args
        assert call_args is not None
        raw = call_args.kwargs["content"]
        body = json.loads(gzip.decompress(raw))
        assert body["ge_id"] == "ge-test"
        assert body["state"] == "idle"
        assert body["task_id"] is None
        assert body["task_ids"] == []
        assert body["slots"]["total"] == 4
        assert body["slots"]["idle"] == 3

    def test_send_running(self):
        reporter, client, _ = self._make_reporter()
        reporter.add_task_id(201)
        reporter.add_task_id(202)
        self._mock_response(client, {"status": "ok", "cancelled_task_ids": [201]})
        resp = reporter.send()
        call_args = client.post.call_args
        body = json.loads(gzip.decompress(call_args.kwargs["content"]))
        assert body["state"] == "running"
        assert body["task_ids"] == [201, 202]
        assert body["task_id"] == 201

    def test_send_with_progress(self):
        reporter, client, _ = self._make_reporter()
        reporter.add_task_id(301)
        reporter.set_progress(301, "downloading")
        reporter.add_task_id(302)
        reporter.set_progress(302, "building")
        self._mock_response(client, {"status": "ok"})
        reporter.send()
        call_args = client.post.call_args
        body = json.loads(gzip.decompress(call_args.kwargs["content"]))
        assert body["task_ids"] == [301, 302]
        assert body["progress"] is not None

    def test_send_with_gzip(self):
        reporter, client, _ = self._make_reporter()
        reporter.add_task_id(401)
        self._mock_response(client, {"status": "ok"})
        resp = reporter.send()
        assert resp == {"status": "ok"}

    def test_cancellation_detection(self):
        reporter, client, _ = self._make_reporter()
        reporter.add_task_id(501)
        reporter.add_task_id(502)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": "ok", "cancelled_task_ids": [501]}
        client.post.return_value = mock_resp
        resp1 = reporter.send()
        assert resp1["cancelled_task_ids"] == [501]

    def test_clear_progress(self):
        reporter, _, _ = self._make_reporter()
        reporter.set_progress(601, "running")
        reporter.set_progress(602, "running")
        reporter.clear_progress(601)
        reporter.add_task_id(601)
        reporter.add_task_id(602)
        assert reporter.running_task_id in (601, 602)

    def test_running_task_id_property(self):
        reporter, _, _ = self._make_reporter()
        assert reporter.running_task_id is None
        reporter.add_task_id(701)
        assert reporter.running_task_id == 701
        reporter.add_task_id(702)
        reporter.remove_task_id(701)
        assert reporter.running_task_id == 702
