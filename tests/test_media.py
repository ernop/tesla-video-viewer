from app.media import clamp_region


def test_clamp_region_pads_and_stays_even() -> None:
    left, top, width, height = clamp_region(10, 20, 110, 60, 1920, 1080, pad=8)
    assert left == 2
    assert top == 12
    assert width == 116
    assert height == 56
    assert width % 2 == 0
    assert height % 2 == 0


def test_clamp_region_clips_to_frame() -> None:
    left, top, width, height = clamp_region(0, 0, 40, 20, 80, 40, pad=8)
    assert left == 0
    assert top == 0
    assert left + width <= 80
    assert top + height <= 40
    assert width >= 2
    assert height >= 2
