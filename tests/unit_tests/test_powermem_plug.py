"""Unit tests for PowerMemPlug."""

from contextseek import ContextSeek
from contextseek.plugs import PowerMemPlug


class _FakeMemory:
    def get_all(self, user_id=None, agent_id=None, run_id=None, limit=100, offset=0):
        return {
            "results": [
                {"id": 9, "content": "sync me", "user_id": user_id, "agent_id": agent_id}
            ]
        }


def test_from_memory_plug_flow() -> None:
    ctx = ContextSeek()
    scope = "t/u/a"
    plug = PowerMemPlug.from_memory(_FakeMemory(), user_id="u", agent_id="a")
    assert len(plug.entries) == 1
    ctx.plug(plug, scope=scope)
    hits = ctx.retrieve("sync", scope=scope, k=5)
    assert hits
    assert hits.items[0].item.provenance.source_id == "powermem://9"


def test_from_records_get_all_shape() -> None:
    plug = PowerMemPlug.from_records(
        [
            {
                "id": 42,
                "content": "User likes tea",
                "metadata": {"tags": ["preference"]},
                "user_id": "u1",
            }
        ]
    )
    events = list(plug.stream())
    assert len(events) == 1
    assert events[0].content == "User likes tea"
    assert events[0].source == "powermem://42"
    assert "powermem" in events[0].tags
    assert "preference" in events[0].tags
    assert events[0].metadata["user_id"] == "u1"


def test_from_records_search_shape() -> None:
    plug = PowerMemPlug.from_records(
        [{"memory": "Deploy checklist", "score": 0.91, "id": 7}]
    )
    events = list(plug.stream())
    assert events[0].content == "Deploy checklist"
    assert events[0].metadata["powermem_score"] == 0.91
