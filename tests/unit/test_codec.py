"""True unit tests for pygwire.codec (StreamDecoder, BackendMessageDecoder, FrontendMessageDecoder).

All external dependencies (lookup_framing, PGMessage) are mocked so these tests
exercise only the codec module's own logic: buffering, compaction, iteration,
phase management, and feed mechanics.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from pygwire.codec import (
    _COMPACTION_THRESHOLD,
    BackendMessageDecoder,
    FrontendMessageDecoder,
)
from pygwire.constants import ConnectionPhase, MessageDirection
from pygwire.messages._base import PGMessage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class FakeMessage(PGMessage):
    """Minimal concrete PGMessage for test assertions."""

    value: str = ""


def _make_framing_mock(
    *,
    return_msg: PGMessage | None = None,
    consumed: int = 0,
    side_effect: Exception | None = None,
) -> MagicMock:
    """Build a mock FramingStrategy with a configurable try_parse."""
    framing = MagicMock()
    if side_effect:
        framing.try_parse.side_effect = side_effect
    elif return_msg is not None:
        framing.try_parse.return_value = (return_msg, consumed)
    else:
        framing.try_parse.return_value = None
    return framing


# ---------------------------------------------------------------------------
# StreamDecoder initialisation
# ---------------------------------------------------------------------------


class TestStreamDecoderInit:
    def test_initial_state_backend(self):
        decoder = BackendMessageDecoder()
        assert decoder.phase == ConnectionPhase.STARTUP
        assert decoder.buffered == 0
        assert decoder._direction == MessageDirection.BACKEND

    def test_initial_state_frontend(self):
        decoder = FrontendMessageDecoder()
        assert decoder.phase == ConnectionPhase.STARTUP
        assert decoder.buffered == 0
        assert decoder._direction == MessageDirection.FRONTEND


# ---------------------------------------------------------------------------
# Phase property
# ---------------------------------------------------------------------------


class TestPhaseProperty:
    def test_get_default_phase(self):
        decoder = BackendMessageDecoder()
        assert decoder.phase == ConnectionPhase.STARTUP

    def test_set_phase(self):
        decoder = BackendMessageDecoder()
        decoder.phase = ConnectionPhase.READY
        assert decoder.phase == ConnectionPhase.READY

    def test_set_phase_multiple_times(self):
        decoder = BackendMessageDecoder()
        decoder.phase = ConnectionPhase.READY
        decoder.phase = ConnectionPhase.SIMPLE_QUERY
        assert decoder.phase == ConnectionPhase.SIMPLE_QUERY


# ---------------------------------------------------------------------------
# feed()
# ---------------------------------------------------------------------------


class TestFeed:
    def test_feed_empty_bytes_is_noop(self):
        decoder = BackendMessageDecoder()
        decoder.feed(b"")
        assert decoder.buffered == 0

    def test_feed_empty_bytearray_is_noop(self):
        decoder = BackendMessageDecoder()
        decoder.feed(bytearray())
        assert decoder.buffered == 0

    def test_feed_empty_memoryview_is_noop(self):
        decoder = BackendMessageDecoder()
        decoder.feed(memoryview(b""))
        assert decoder.buffered == 0

    def test_feed_bytes(self):
        decoder = BackendMessageDecoder()
        decoder.feed(b"hello")
        assert decoder.buffered == 5

    def test_feed_bytearray(self):
        decoder = BackendMessageDecoder()
        decoder.feed(bytearray(b"hello"))
        assert decoder.buffered == 5

    def test_feed_memoryview(self):
        decoder = BackendMessageDecoder()
        decoder.feed(memoryview(b"hello"))
        assert decoder.buffered == 5

    def test_feed_accumulates(self):
        decoder = BackendMessageDecoder()
        decoder.feed(b"abc")
        decoder.feed(b"def")
        assert decoder.buffered == 6


# ---------------------------------------------------------------------------
# clear()
# ---------------------------------------------------------------------------


class TestClear:
    def test_clear_empties_buffer(self):
        decoder = BackendMessageDecoder()
        decoder.feed(b"some data")
        decoder.clear()
        assert decoder.buffered == 0

    def test_clear_empties_pending_messages(self):
        decoder = BackendMessageDecoder()
        # Manually inject a pending message
        decoder._messages.append(FakeMessage(value="pending"))
        decoder.clear()
        assert len(decoder._messages) == 0

    def test_clear_resets_pos(self):
        decoder = BackendMessageDecoder()
        decoder._pos = 42
        decoder.clear()
        assert decoder._pos == 0


# ---------------------------------------------------------------------------
# buffered property
# ---------------------------------------------------------------------------


class TestBuffered:
    def test_buffered_accounts_for_pos(self):
        decoder = BackendMessageDecoder()
        decoder.feed(b"0123456789")
        decoder._pos = 4
        assert decoder.buffered == 6

    def test_buffered_zero_when_empty(self):
        decoder = BackendMessageDecoder()
        assert decoder.buffered == 0


# ---------------------------------------------------------------------------
# _compact()
# ---------------------------------------------------------------------------


class TestCompact:
    def test_compact_removes_consumed_bytes(self):
        decoder = BackendMessageDecoder()
        decoder.feed(b"abcdefgh")
        decoder._pos = 3
        decoder._compact()

        assert decoder._pos == 0
        assert decoder.buffered == 5
        assert bytes(decoder._buf) == b"defgh"

    def test_compact_noop_when_pos_zero(self):
        decoder = BackendMessageDecoder()
        decoder.feed(b"abcdefgh")
        decoder._compact()

        assert decoder._pos == 0
        assert decoder.buffered == 8

    def test_compact_full_consumption(self):
        decoder = BackendMessageDecoder()
        decoder.feed(b"abc")
        decoder._pos = 3
        decoder._compact()

        assert decoder._pos == 0
        assert decoder.buffered == 0


# ---------------------------------------------------------------------------
# _parse() — single message parsing
# ---------------------------------------------------------------------------


class TestParse:
    @patch("pygwire.codec.lookup_framing")
    def test_parse_returns_none_when_framing_returns_none(self, mock_lookup):
        framing = _make_framing_mock()
        mock_lookup.return_value = framing

        decoder = BackendMessageDecoder()
        decoder.feed(b"not enough data")
        decoder._parse()

        assert len(decoder._messages) == 0

    @patch("pygwire.codec.lookup_framing")
    def test_parse_appends_message_on_success(self, mock_lookup):
        msg = FakeMessage(value="parsed")
        framing = _make_framing_mock(return_msg=msg, consumed=10)
        mock_lookup.return_value = framing

        decoder = BackendMessageDecoder()
        decoder.feed(b"x" * 20)
        decoder._parse()

        assert len(decoder._messages) == 1
        assert decoder._messages[0] is msg
        assert decoder._pos == 10

    @patch("pygwire.codec.lookup_framing")
    def test_parse_advances_pos_by_consumed(self, mock_lookup):
        msg = FakeMessage(value="x")
        framing = _make_framing_mock(return_msg=msg, consumed=7)
        mock_lookup.return_value = framing

        decoder = BackendMessageDecoder()
        decoder.feed(b"x" * 20)
        decoder._parse()

        assert decoder._pos == 7

    @patch("pygwire.codec.lookup_framing")
    def test_parse_uses_current_phase_and_direction(self, mock_lookup):
        framing = _make_framing_mock()
        mock_lookup.return_value = framing

        decoder = BackendMessageDecoder()
        decoder.phase = ConnectionPhase.READY
        decoder.feed(b"data")
        decoder._parse()

        mock_lookup.assert_called_once_with(ConnectionPhase.READY, MessageDirection.BACKEND)

    @patch("pygwire.codec.lookup_framing")
    def test_parse_passes_memoryview_to_framing(self, mock_lookup):
        framing = _make_framing_mock()
        mock_lookup.return_value = framing

        decoder = BackendMessageDecoder()
        decoder.feed(b"data")
        decoder._parse()

        call_args = framing.try_parse.call_args
        assert isinstance(call_args.kwargs["buf"], memoryview)

    @patch("pygwire.codec.lookup_framing")
    def test_parse_passes_pos_to_framing(self, mock_lookup):
        framing = _make_framing_mock()
        mock_lookup.return_value = framing

        decoder = BackendMessageDecoder()
        decoder.feed(b"data")
        decoder._pos = 2
        decoder._parse()

        call_args = framing.try_parse.call_args
        assert call_args.kwargs["pos"] == 2

    @patch("pygwire.codec.lookup_framing")
    def test_parse_triggers_compaction_over_threshold(self, mock_lookup):
        msg = FakeMessage(value="x")
        consumed = _COMPACTION_THRESHOLD + 1

        # Use a plain function (not MagicMock) to avoid holding memoryview
        # references in call_args, which would prevent bytearray resizing.
        framing = MagicMock()
        framing.try_parse = lambda **_: (msg, consumed)
        mock_lookup.return_value = framing

        decoder = BackendMessageDecoder()
        decoder.feed(b"x" * (consumed + 100))
        decoder._parse()

        # After compaction, pos should be reset to 0
        assert decoder._pos == 0
        assert decoder.buffered == 100

    @patch("pygwire.codec.lookup_framing")
    def test_parse_no_compaction_under_threshold(self, mock_lookup):
        msg = FakeMessage(value="x")
        consumed = _COMPACTION_THRESHOLD - 1
        framing = _make_framing_mock(return_msg=msg, consumed=consumed)
        mock_lookup.return_value = framing

        decoder = BackendMessageDecoder()
        decoder.feed(b"x" * (consumed + 50))
        decoder._parse()

        # Under threshold — pos stays advanced, no compaction
        assert decoder._pos == consumed

    @patch("pygwire.codec.lookup_framing")
    def test_parse_propagates_framing_exception(self, mock_lookup):
        from pygwire.exceptions import FramingError

        framing = _make_framing_mock(side_effect=FramingError("bad"))
        mock_lookup.return_value = framing

        decoder = BackendMessageDecoder()
        decoder.feed(b"bad data")

        with pytest.raises(FramingError, match="bad"):
            decoder._parse()


# ---------------------------------------------------------------------------
# Iterator protocol (__iter__, __next__)
# ---------------------------------------------------------------------------


class TestIterator:
    def test_iter_returns_self(self):
        decoder = BackendMessageDecoder()
        assert iter(decoder) is decoder

    @patch("pygwire.codec.lookup_framing")
    def test_next_returns_already_queued_message(self, mock_lookup):
        """__next__ should return pre-queued messages before calling _parse."""
        decoder = BackendMessageDecoder()
        msg = FakeMessage(value="queued")
        decoder._messages.append(msg)

        result = next(decoder)
        assert result is msg
        # lookup_framing should NOT be called since the message was already queued
        mock_lookup.assert_not_called()

    @patch("pygwire.codec.lookup_framing")
    def test_next_calls_parse_when_queue_empty(self, mock_lookup):
        msg = FakeMessage(value="parsed")
        framing = _make_framing_mock(return_msg=msg, consumed=5)
        mock_lookup.return_value = framing

        decoder = BackendMessageDecoder()
        decoder.feed(b"x" * 10)

        result = next(decoder)
        assert result is msg

    @patch("pygwire.codec.lookup_framing")
    def test_next_raises_stop_iteration_when_no_data(self, mock_lookup):
        framing = _make_framing_mock()  # returns None
        mock_lookup.return_value = framing

        decoder = BackendMessageDecoder()
        decoder.feed(b"partial")

        with pytest.raises(StopIteration):
            next(decoder)

    @patch("pygwire.codec.lookup_framing")
    def test_for_loop_yields_one_message_per_iteration(self, mock_lookup):
        """The iterator parses one message per __next__ call."""
        msg1 = FakeMessage(value="first")
        msg2 = FakeMessage(value="second")

        call_count = 0

        def side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (msg1, 5)
            elif call_count == 2:
                return (msg2, 5)
            return None

        framing = MagicMock()
        framing.try_parse.side_effect = side_effect
        mock_lookup.return_value = framing

        decoder = BackendMessageDecoder()
        decoder.feed(b"x" * 20)

        results = list(decoder)
        assert len(results) == 2
        assert results[0] is msg1
        assert results[1] is msg2

    @patch("pygwire.codec.lookup_framing")
    def test_for_loop_empty_buffer(self, mock_lookup):
        framing = _make_framing_mock()
        mock_lookup.return_value = framing

        decoder = BackendMessageDecoder()
        results = list(decoder)
        assert results == []


# ---------------------------------------------------------------------------
# _read() — internal queue drain
# ---------------------------------------------------------------------------


class TestRead:
    def test_read_returns_none_when_empty(self):
        decoder = BackendMessageDecoder()
        assert decoder._read() is None

    def test_read_returns_messages_in_fifo_order(self):
        decoder = BackendMessageDecoder()
        msg1 = FakeMessage(value="first")
        msg2 = FakeMessage(value="second")
        decoder._messages.append(msg1)
        decoder._messages.append(msg2)

        assert decoder._read() is msg1
        assert decoder._read() is msg2
        assert decoder._read() is None


# ---------------------------------------------------------------------------
# Phase changes between messages
# ---------------------------------------------------------------------------


class TestPhaseChangesBetweenMessages:
    @patch("pygwire.codec.lookup_framing")
    def test_phase_change_between_iterations(self, mock_lookup):
        """Verify lookup_framing is called with the current phase each time _parse runs."""
        msg1 = FakeMessage(value="first")
        msg2 = FakeMessage(value="second")

        call_count = 0

        def framing_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (msg1, 5)
            elif call_count == 2:
                return (msg2, 5)
            return None

        framing = MagicMock()
        framing.try_parse.side_effect = framing_side_effect
        mock_lookup.return_value = framing

        decoder = BackendMessageDecoder()
        decoder.feed(b"x" * 20)

        # Get first message in STARTUP phase
        result1 = next(decoder)
        assert result1 is msg1
        mock_lookup.assert_called_with(ConnectionPhase.STARTUP, MessageDirection.BACKEND)

        # Change phase, get second message
        decoder.phase = ConnectionPhase.READY
        result2 = next(decoder)
        assert result2 is msg2
        mock_lookup.assert_called_with(ConnectionPhase.READY, MessageDirection.BACKEND)


# ---------------------------------------------------------------------------
# FrontendMessageDecoder specifics
# ---------------------------------------------------------------------------


class TestFrontendMessageDecoder:
    def test_direction_is_frontend(self):
        decoder = FrontendMessageDecoder()
        assert decoder._direction == MessageDirection.FRONTEND

    @patch("pygwire.codec.lookup_framing")
    def test_parse_uses_frontend_direction(self, mock_lookup):
        framing = _make_framing_mock()
        mock_lookup.return_value = framing

        decoder = FrontendMessageDecoder()
        decoder.feed(b"data")
        decoder._parse()

        mock_lookup.assert_called_once_with(ConnectionPhase.STARTUP, MessageDirection.FRONTEND)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    @patch("pygwire.codec.lookup_framing")
    def test_compaction_at_exact_threshold(self, mock_lookup):
        """pos == _COMPACTION_THRESHOLD should NOT trigger compaction (> not >=)."""
        msg = FakeMessage(value="x")
        framing = _make_framing_mock(return_msg=msg, consumed=_COMPACTION_THRESHOLD)
        mock_lookup.return_value = framing

        decoder = BackendMessageDecoder()
        decoder.feed(b"x" * (_COMPACTION_THRESHOLD + 50))
        decoder._parse()

        # Exactly at threshold — no compaction
        assert decoder._pos == _COMPACTION_THRESHOLD

    @patch("pygwire.codec.lookup_framing")
    def test_multiple_parses_accumulate_pos(self, mock_lookup):
        msg = FakeMessage(value="x")

        call_count = 0

        def side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return (msg, 10)
            return None

        framing = MagicMock()
        framing.try_parse.side_effect = side_effect
        mock_lookup.return_value = framing

        decoder = BackendMessageDecoder()
        decoder.feed(b"x" * 30)

        list(decoder)

        assert decoder._pos == 20

    def test_feed_after_clear(self):
        decoder = BackendMessageDecoder()
        decoder.feed(b"old data")
        decoder.clear()
        decoder.feed(b"new")
        assert decoder.buffered == 3

    @patch("pygwire.codec.lookup_framing")
    def test_next_after_feed_more_data(self, mock_lookup):
        """Feeding more data between iterations should work."""
        msg = FakeMessage(value="x")

        call_count = 0

        # Use a plain function to avoid MagicMock holding memoryview references
        # in call_args, which would prevent bytearray resizing on feed().
        def try_parse_fn(**_):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return None  # not enough data yet
            elif call_count == 2:
                return (msg, 10)
            return None

        framing = MagicMock()
        framing.try_parse = try_parse_fn
        mock_lookup.return_value = framing

        decoder = BackendMessageDecoder()
        decoder.feed(b"partial")

        # First attempt — not enough data
        with pytest.raises(StopIteration):
            next(decoder)

        # Feed more and retry
        decoder.feed(b"more data here")
        result = next(decoder)
        assert result is msg
