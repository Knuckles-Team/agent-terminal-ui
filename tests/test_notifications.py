"""Tests for notifications.py -- Desktop notifications."""

from __future__ import annotations

import io
import sys

import pytest

from agent_terminal_ui.notifications import (
    DesktopNotifier,
    NotificationMethod,
    _detect_method,
)


class TestNotificationMethod:
    def test_enum_values(self) -> None:
        assert NotificationMethod.AUTO.value == "auto"
        assert NotificationMethod.OSC9.value == "osc9"
        assert NotificationMethod.BEL.value == "bel"
        assert NotificationMethod.OFF.value == "off"


class TestDesktopNotifier:
    def test_init_with_string(self) -> None:
        notifier = DesktopNotifier(method="bel")
        assert notifier.method == NotificationMethod.BEL

    def test_init_with_enum(self) -> None:
        notifier = DesktopNotifier(method=NotificationMethod.OSC9)
        assert notifier.method == NotificationMethod.OSC9

    def test_threshold(self) -> None:
        notifier = DesktopNotifier(threshold_secs=60)
        assert notifier.threshold_secs == 60
        notifier.threshold_secs = 10
        assert notifier.threshold_secs == 10

    def test_threshold_min_clamp(self) -> None:
        notifier = DesktopNotifier()
        notifier.threshold_secs = 0
        assert notifier.threshold_secs == 1

    def test_no_notify_on_failure(self) -> None:
        notifier = DesktopNotifier(method="bel", threshold_secs=1)
        assert notifier.notify_turn_complete(elapsed_secs=100, success=False) is False

    def test_no_notify_below_threshold(self) -> None:
        notifier = DesktopNotifier(method="bel", threshold_secs=30)
        assert notifier.notify_turn_complete(elapsed_secs=10) is False

    def test_no_notify_when_off(self) -> None:
        notifier = DesktopNotifier(method="off", threshold_secs=1)
        assert notifier.notify_turn_complete(elapsed_secs=100) is False

    def test_bel_notification(self, monkeypatch: pytest.MonkeyPatch) -> None:
        buffer = io.StringIO()
        monkeypatch.setattr(sys, "stdout", buffer)
        notifier = DesktopNotifier(method="bel", threshold_secs=1)
        result = notifier.notify_turn_complete(elapsed_secs=100)
        assert result is True
        assert "\x07" in buffer.getvalue()

    def test_osc9_notification(self, monkeypatch: pytest.MonkeyPatch) -> None:
        buffer = io.StringIO()
        monkeypatch.setattr(sys, "stdout", buffer)
        notifier = DesktopNotifier(method="osc9", threshold_secs=1)
        result = notifier.notify_turn_complete(elapsed_secs=100)
        assert result is True
        output = buffer.getvalue()
        assert "\x1b]9;" in output
        assert "Agent turn complete" in output

    def test_include_summary(self, monkeypatch: pytest.MonkeyPatch) -> None:
        buffer = io.StringIO()
        monkeypatch.setattr(sys, "stdout", buffer)
        notifier = DesktopNotifier(
            method="osc9", threshold_secs=1, include_summary=True
        )
        notifier.notify_turn_complete(elapsed_secs=45.3, cost_usd=0.0123)
        output = buffer.getvalue()
        assert "45.3s" in output
        assert "$0.0123" in output

    def test_test_method(self, monkeypatch: pytest.MonkeyPatch) -> None:
        buffer = io.StringIO()
        monkeypatch.setattr(sys, "stdout", buffer)
        notifier = DesktopNotifier(method="bel")
        assert notifier.test() is True

    def test_test_off(self) -> None:
        notifier = DesktopNotifier(method="off")
        assert notifier.test() is False


class TestAutoDetect:
    def test_detect_method_returns_enum(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TERM_PROGRAM", raising=False)
        monkeypatch.delenv("TERM", raising=False)
        result = _detect_method()
        assert isinstance(result, NotificationMethod)

    def test_detect_iterm(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")
        assert _detect_method() == NotificationMethod.OSC9

    def test_detect_ghostty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TERM_PROGRAM", "ghostty")
        assert _detect_method() == NotificationMethod.OSC9

    def test_detect_xterm(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TERM_PROGRAM", "unknown")
        monkeypatch.setenv("TERM", "xterm-256color")
        assert _detect_method() == NotificationMethod.BEL
