#!/usr/bin/env python3
# Placeholder tests for LamportClock

"""
test_clock.py - Unit tests for the Lamport Logical Clock used in
distributed mutual exclusion.

Run with:
    pytest test_clock.py -v

Assumes utils.py exposes:
    - LamportClock class with .tick(), .update(received), and .value()
    - make_request_key(timestamp, worker_id) helper
"""

import pytest
from utils import LamportClock, make_request_key


# ---------------------------------------------------------------------------
# 1. Initialization
# ---------------------------------------------------------------------------

class TestClockInitialization:
    """Verify that a LamportClock starts in the expected state."""

    def test_default_initial_value_is_zero(self):
        """Clock should start at 0 when no argument is provided."""
        clock = LamportClock()
        assert clock.value() == 0, "Default initial clock value must be 0."

    def test_custom_initial_value(self):
        """Clock should honour a positive integer passed at construction time."""
        clock = LamportClock(initial=10)
        assert clock.value() == 10, "Clock should start at the supplied initial value."

    def test_zero_initial_value_explicit(self):
        """Explicitly passing 0 should behave identically to the default."""
        clock = LamportClock(initial=0)
        assert clock.value() == 0

    def test_negative_initial_value_raises(self):
        """A negative starting value is logically invalid and must be rejected."""
        with pytest.raises((ValueError, AssertionError)):
            LamportClock(initial=-1)


# ---------------------------------------------------------------------------
# 2. Increment on internal / send events  (tick)
# ---------------------------------------------------------------------------

class TestClockTick:
    """Verify that tick() advances the clock by exactly 1."""

    def test_single_tick_increments_by_one(self):
        """One tick from 0 must yield 1."""
        clock = LamportClock()
        clock.tick()
        assert clock.value() == 1

    def test_tick_returns_updated_value(self):
        """tick() must return the new clock value, not the old one."""
        clock = LamportClock()
        returned = clock.tick()
        assert returned == clock.value(), "tick() return value must match internal state."

    def test_tick_from_non_zero_start(self):
        """tick() should add 1 regardless of the current value."""
        clock = LamportClock(initial=5)
        clock.tick()
        assert clock.value() == 6

    def test_tick_is_monotonically_increasing(self):
        """After every tick the clock value must be strictly larger than before."""
        clock = LamportClock()
        previous = clock.value()
        for _ in range(5):
            clock.tick()
            assert clock.value() > previous, "Clock must be strictly increasing after each tick."
            previous = clock.value()


# ---------------------------------------------------------------------------
# 3 & 4. Update on message receive  (Lamport rule)
# ---------------------------------------------------------------------------

class TestClockUpdate:
    """
    Verify: new_clock = max(local_clock, received_clock) + 1

    Cases:
      3. received > local  → clock jumps to received + 1
      4. received < local  → clock advances by 1 (local wins)
    """

    def test_update_with_larger_received_timestamp(self):
        """
        When the incoming timestamp is larger, the clock must jump to
        received + 1 (Lamport rule with remote clock dominating).
        """
        clock = LamportClock(initial=3)
        clock.update(received=10)
        # max(3, 10) + 1 == 11
        assert clock.value() == 11

    def test_update_with_smaller_received_timestamp(self):
        """
        When the incoming timestamp is smaller, the local clock dominates
        and the result is local + 1.
        """
        clock = LamportClock(initial=10)
        clock.update(received=3)
        # max(10, 3) + 1 == 11
        assert clock.value() == 11

    def test_update_returns_new_clock_value(self):
        """update() must return the updated clock value."""
        clock = LamportClock(initial=5)
        result = clock.update(received=8)
        assert result == clock.value(), "update() return value must match internal state."

    def test_update_with_equal_timestamp(self):
        """
        When received == local, max(local, received) == local,
        so the clock must advance by exactly 1.
        """
        clock = LamportClock(initial=7)
        clock.update(received=7)
        # max(7, 7) + 1 == 8
        assert clock.value() == 8

    def test_update_with_zero_received(self):
        """Receiving a timestamp of 0 from a freshly-started peer."""
        clock = LamportClock(initial=5)
        clock.update(received=0)
        # max(5, 0) + 1 == 6
        assert clock.value() == 6

    def test_lamport_rule_formula_correctness(self):
        """
        Directly verify the Lamport formula across several (local, received)
        pairs to ensure the implementation is not hard-coded.
        """
        cases = [
            (0,  0,  1),
            (0,  5,  6),
            (5,  0,  6),
            (3,  7, 8),
            (7,  3,  8),
            (10, 10, 11),
        ]
        for local, received, expected in cases:
            clock = LamportClock(initial=local)
            clock.update(received=received)
            assert clock.value() == expected, (
                f"update({received}) on clock({local}) → expected {expected}, "
                f"got {clock.value()}"
            )


# ---------------------------------------------------------------------------
# 5. Multiple sequential ticks
# ---------------------------------------------------------------------------

class TestMultipleSequentialTicks:
    """Verify that repeated tick() calls accumulate correctly."""

    def test_five_sequential_ticks_from_zero(self):
        """Five ticks from 0 must reach 5."""
        clock = LamportClock()
        for _ in range(5):
            clock.tick()
        assert clock.value() == 5

    def test_ten_sequential_ticks(self):
        """Ten ticks from 0 must reach 10."""
        clock = LamportClock()
        for _ in range(10):
            clock.tick()
        assert clock.value() == 10

    def test_ticks_interleaved_with_updates(self):
        """
        Simulates a realistic sequence:
          start=0, tick→1, update(5)→6, tick→7, tick→8, update(3)→9
        """
        clock = LamportClock()
        clock.tick()                   # 1
        clock.update(received=5)       # max(1,5)+1 = 6
        clock.tick()                   # 7
        clock.tick()                   # 8
        clock.update(received=3)       # max(8,3)+1 = 9
        assert clock.value() == 9

    def test_sequential_ticks_each_step_increases_by_one(self):
        """Every individual tick must add exactly 1 to the previous value."""
        clock = LamportClock()
        for step in range(1, 21):
            clock.tick()
            assert clock.value() == step, (
                f"After {step} tick(s) clock should be {step}, got {clock.value()}"
            )


# ---------------------------------------------------------------------------
# 6. Queue ordering: (timestamp, worker_id)
# ---------------------------------------------------------------------------

class TestQueueOrdering:
    """
    In Ricart-Agrawala / token-ring style algorithms, pending requests are
    stored as (timestamp, worker_id) tuples and sorted so that the process
    with the smallest logical time (and alphabetically smallest id on a tie)
    enters the critical section first.
    """

    def test_earlier_timestamp_has_higher_priority(self):
        """A request with a lower timestamp must sort before a higher one."""
        req_a = make_request_key(timestamp=3, worker_id="worker-2")
        req_b = make_request_key(timestamp=7, worker_id="worker-1")
        assert req_a < req_b, "Lower timestamp request must precede higher timestamp request."

    def test_tie_broken_alphabetically_by_worker_id(self):
        """
        When timestamps are equal, alphabetically earlier worker_id wins.
        'worker-A' < 'worker-B' lexicographically.
        """
        req_a = make_request_key(timestamp=5, worker_id="worker-A")
        req_b = make_request_key(timestamp=5, worker_id="worker-B")
        assert req_a < req_b, "Equal timestamps must be broken alphabetically by worker_id."

    def test_sort_multiple_requests_mixed_timestamps(self):
        """
        A realistic queue with mixed timestamps sorts by (ts, id).
        Expected order: (1,'w-C'), (2,'w-A'), (2,'w-B'), (5,'w-A')
        """
        requests = [
            make_request_key(2, "w-B"),
            make_request_key(5, "w-A"),
            make_request_key(1, "w-C"),
            make_request_key(2, "w-A"),
        ]
        sorted_requests = sorted(requests)
        expected = [
            (1, "w-C"),
            (2, "w-A"),
            (2, "w-B"),
            (5, "w-A"),
        ]
        assert sorted_requests == expected, (
            f"Queue order incorrect.\nExpected: {expected}\nGot:      {sorted_requests}"
        )

    def test_all_same_timestamp_sorted_by_worker_id(self):
        """When every request shares a timestamp, sort is purely alphabetical."""
        requests = [
            make_request_key(10, "worker-Z"),
            make_request_key(10, "worker-A"),
            make_request_key(10, "worker-M"),
        ]
        sorted_requests = sorted(requests)
        assert sorted_requests[0][1] == "worker-A"
        assert sorted_requests[1][1] == "worker-M"
        assert sorted_requests[2][1] == "worker-Z"

    def test_single_request_queue(self):
        """A queue with one request is trivially sorted."""
        requests = [make_request_key(99, "solo-worker")]
        assert sorted(requests) == [(99, "solo-worker")]


# ---------------------------------------------------------------------------
# 7. Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge cases that could expose off-by-one errors or overflow issues."""

    def test_receive_same_timestamp_as_local(self):
        """
        Receiving a timestamp identical to the local clock must still advance
        the clock by 1 (max(t,t)+1 = t+1).
        """
        clock = LamportClock(initial=42)
        clock.update(received=42)
        assert clock.value() == 43

    def test_receive_timestamp_zero_on_fresh_clock(self):
        """
        A brand-new clock (value=0) receiving timestamp 0 must move to 1.
        This is the very first event in the system.
        """
        clock = LamportClock()
        clock.update(received=0)
        assert clock.value() == 1

    def test_very_large_timestamp_update(self):
        """
        The clock must handle arbitrarily large timestamps without overflow
        (Python integers are unbounded, so this validates the formula only).
        """
        large = 10 ** 18
        clock = LamportClock(initial=0)
        clock.update(received=large)
        assert clock.value() == large + 1

    def test_large_local_clock_tick(self):
        """tick() on a very large clock value should still add exactly 1."""
        large = 10 ** 18
        clock = LamportClock(initial=large)
        clock.tick()
        assert clock.value() == large + 1

    def test_clock_never_goes_backward_after_updates(self):
        """
        Regardless of the sequence of ticks and updates, the clock value
        must never decrease.
        """
        clock = LamportClock()
        history = []
        operations = [
            ("tick",   None),
            ("update", 100),
            ("tick",   None),
            ("update", 50),
            ("update", 200),
            ("tick",   None),
            ("update", 1),
        ]
        for op, arg in operations:
            if op == "tick":
                clock.tick()
            else:
                clock.update(received=arg)
            history.append(clock.value())

        for i in range(1, len(history)):
            assert history[i] >= history[i - 1], (
                f"Clock went backward at step {i}: {history[i - 1]} → {history[i]}"
            )

    def test_multiple_clocks_are_independent(self):
        """
        Two separate LamportClock instances must not share state.
        Operations on one must not affect the other.
        """
        clock_a = LamportClock(initial=0)
        clock_b = LamportClock(initial=0)

        clock_a.tick()
        clock_a.tick()
        clock_a.tick()

        assert clock_b.value() == 0, (
            "clock_b must remain 0; operations on clock_a must not bleed over."
        )

    def test_update_does_not_skip_the_plus_one(self):
        """
        Lamport rule is max(local, received) + 1, NOT max(local, received).
        Ensure the +1 is always applied even when max dominates.
        """
        clock = LamportClock(initial=0)
        clock.update(received=99)
        # If implementation forgets +1, value would be 99 instead of 100
        assert clock.value() == 100, (
            "update() must apply +1 after the max; got clock == 99 (missing +1)."
        )

pass
