"""Tests for audit logging."""

from contextseek.observability.audit import AuditLog, AuditRecord, MetricPoint


def _make_record(**kwargs):
    defaults = {
        "request_id": "req-1",
        "action": "search",
        "scope": "acme/proj/user1",
        "policy_version": "v1",
    }
    defaults.update(kwargs)
    return AuditRecord(**defaults)


class TestAuditLog:
    def test_append_and_latest(self):
        log = AuditLog()
        record = _make_record()
        log.append(record)
        assert log.latest() is record

    def test_latest_by_action(self):
        log = AuditLog()
        log.append(_make_record(action="search"))
        log.append(_make_record(action="write"))
        assert log.latest(action="search").action == "search"

    def test_metric_series(self):
        log = AuditLog()
        log.append(
            _make_record(
                metrics=[
                    MetricPoint(name="latency", value=10.0),
                ]
            )
        )
        log.append(
            _make_record(
                metrics=[
                    MetricPoint(name="latency", value=20.0),
                ]
            )
        )
        series = log.metric_series("latency")
        assert series == [10.0, 20.0]

    def test_recent(self):
        log = AuditLog()
        for i in range(10):
            log.append(_make_record(request_id=f"req-{i}"))
        recent = log.recent(limit=3)
        assert len(recent) == 3

    def test_export_prometheus(self):
        log = AuditLog()
        log.append(_make_record(elapsed_ms=5.0))
        output = log.export_prometheus()
        assert "contextseek_request_metric" in output
