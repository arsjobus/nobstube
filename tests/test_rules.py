from api.filtering.rules import RuleEngine
from api.models import Video

def test_reaction_is_rejected():
    engine = RuleEngine({
        "exclusions": {"content_types": ["reaction"]},
        "settings": {"minimum_duration_seconds": 0},
    })
    video = Video(
        source="test",
        source_id="1",
        url="https://example.com/1",
        title="My reaction to the latest film",
    )
    rejected, _ = engine.hard_reject(video)
    assert rejected

def test_long_technical_video_can_pass():
    engine = RuleEngine({
        "exclusions": {"content_types": []},
        "settings": {"minimum_duration_seconds": 300},
    })
    video = Video(
        source="test",
        source_id="2",
        url="https://example.com/2",
        title="University lecture: how lithium ion batteries work",
        duration_seconds=3600,
    )
    rejected, _ = engine.hard_reject(video)
    assert not rejected


def test_political_search_query_is_rejected_when_politics_is_excluded():
    engine = RuleEngine({
        "exclusions": {"content_types": ["politics"]},
        "settings": {},
    })

    rejected, reason = engine.hard_reject(None, query="trump news")

    assert rejected
    assert reason == "Political search query"


def test_nonpolitical_query_is_not_rejected_by_politics_rule():
    engine = RuleEngine({
        "exclusions": {"content_types": ["politics"]},
        "settings": {},
    })

    rejected, _ = engine.hard_reject(None, query="news about computer security")

    assert not rejected
