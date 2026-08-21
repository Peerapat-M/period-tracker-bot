from unittest.mock import patch

import pytest
from linebot.v3.messaging import TextMessage

import messaging


def _msg():
    return [TextMessage(text="hello")]


def test_send_reply_uses_reply_when_it_succeeds():
    with patch.object(messaging.MessagingApi, "reply_message") as mock_reply, \
         patch.object(messaging.MessagingApi, "push_message") as mock_push:
        messaging.send_reply("token", _msg(), fallback_to="u1")
    mock_reply.assert_called_once()
    mock_push.assert_not_called()


def test_send_reply_falls_back_to_push_when_reply_fails():
    with patch.object(messaging.MessagingApi, "reply_message", side_effect=Exception("expired")), \
         patch.object(messaging.MessagingApi, "push_message") as mock_push:
        messaging.send_reply("token", _msg(), fallback_to="u1")
    mock_push.assert_called_once()


def test_send_reply_raises_when_reply_and_fallback_push_both_fail():
    with patch.object(messaging.MessagingApi, "reply_message", side_effect=Exception("expired")), \
         patch.object(messaging.MessagingApi, "push_message", side_effect=Exception("push down")):
        with pytest.raises(Exception):
            messaging.send_reply("token", _msg(), fallback_to="u1")


def test_send_reply_raises_when_reply_fails_with_no_fallback_target():
    with patch.object(messaging.MessagingApi, "reply_message", side_effect=Exception("expired")):
        with pytest.raises(Exception):
            messaging.send_reply("token", _msg())
