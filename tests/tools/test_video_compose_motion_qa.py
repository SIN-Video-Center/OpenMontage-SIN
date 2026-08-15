from tools.video.video_compose import (
    RENDERED_MOTION_THRESHOLD,
    _rendered_motion_mask,
    _timeline_scene_id,
)


def test_dark_editorial_motion_threshold_rejects_codec_jitter():
    assert RENDERED_MOTION_THRESHOLD == 0.001
    assert _rendered_motion_mask([0.00016, 0.0008, 0.001, 0.004]) == [
        False,
        False,
        True,
        True,
    ]


def test_repetition_qa_resolves_frames_to_distinct_scenes():
    windows = [(0.0, 8.4, "s1"), (8.4, 17.9, "s2")]
    assert _timeline_scene_id(windows, 0.5) == "s1"
    assert _timeline_scene_id(windows, 7.5) == "s1"
    assert _timeline_scene_id(windows, 8.5) == "s2"
    assert _timeline_scene_id(windows, 18.0) is None
