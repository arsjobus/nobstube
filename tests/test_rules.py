from app.filtering.rules import RuleEngine
from app.models import Video

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
