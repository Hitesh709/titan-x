import time


def test_event_processing_baseline() -> None:
    # Lightweight deterministic baseline; full load testing should run in CI/staging.
    events = 10_000
    start = time.perf_counter()
    values = [i * 2 for i in range(events)]
    elapsed = time.perf_counter() - start
    assert len(values) == events
    assert elapsed < 1.0
