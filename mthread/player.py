"""Replaying a recorded :class:`~mthread.session.Session` back onto a device."""

from __future__ import annotations

from typing import Iterable, Iterator

from .session import InputEvent, Session

__all__ = ["build_replay_script", "iter_replay_chunks", "replay"]

#: Gaps shorter than this are not worth a `sleep` call - the round trip through
#: the shell already costs more than the pause itself.
MIN_SLEEP = 0.005


def build_replay_script(
    events: Iterable[InputEvent],
    *,
    speed: float = 1.0,
    min_sleep: float = MIN_SLEEP,
) -> list[str]:
    """Turn events into shell lines that reproduce them with their original timing.

    Sleeps are emitted against a running clock rather than per-event deltas, so
    rounding to millisecond precision cannot accumulate into visible drift over a
    long recording.

    Args:
        speed: Playback multiplier; ``2.0`` replays twice as fast.
    """
    if speed <= 0:
        raise ValueError("speed must be positive")

    lines: list[str] = []
    elapsed = 0.0
    for event in events:
        target = event.t / speed
        gap = target - elapsed
        if gap >= min_sleep:
            rounded = round(gap, 3)
            lines.append(f"sleep {rounded:.3f}")
            elapsed += rounded
        lines.append(f"sendevent {event.device} {event.type} {event.code} {event.value}")
    return lines


def iter_replay_chunks(
    events: list[InputEvent],
    *,
    speed: float = 1.0,
    chunk_events: int = 4000,
) -> Iterator[list[str]]:
    """Yield the replay script in chunks, so long recordings stream to the device.

    Each chunk is time-rebased to its own first event; the small pause between
    chunks is the cost of not buffering a hundred-thousand-line script in memory.
    """
    for start in range(0, len(events), chunk_events):
        window = events[start : start + chunk_events]
        if not window:
            continue
        origin = window[0].t
        rebased = [
            InputEvent(t=event.t - origin, device=event.device, type=event.type, code=event.code, value=event.value)
            for event in window
        ]
        yield build_replay_script(rebased, speed=speed)


def replay(
    device,
    session: Session,
    *,
    speed: float = 1.0,
    repeat: int = 1,
    chunk_events: int = 4000,
    progress=None,
    should_continue=None,
) -> None:
    """Play *session* back on *device*.

    Args:
        repeat: How many times to loop the recording.
        progress: Called as ``progress(done, total)`` after each chunk.
        should_continue: Polled between chunks; return ``False`` to stop early.
    """
    if not session.events:
        return

    device_size = None
    try:
        device_size = device.screen_size
    except Exception:
        pass
    if session.screen_size and device_size and tuple(session.screen_size) != tuple(device_size):
        raise ValueError(
            f"This recording was made on a {session.screen_size[0]}x{session.screen_size[1]} screen "
            f"but the connected device is {device_size[0]}x{device_size[1]}. "
            "Raw touch coordinates are not portable between different panels."
        )

    total = len(session.events) * repeat
    done = 0
    for _ in range(max(1, repeat)):
        for chunk in iter_replay_chunks(session.events, speed=speed, chunk_events=chunk_events):
            if should_continue is not None and not should_continue():
                return
            device.run_script(chunk)
            done += min(chunk_events, total - done)
            if progress is not None:
                progress(done, total)
