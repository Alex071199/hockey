from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.scraper.onhockey import determine_league, parse_stream_url, build_stream_url


def test_determine_league_khl():
    assert determine_league("КХЛ — Матч") == "KHL"
    assert determine_league("KHL game") == "KHL"


def test_determine_league_vhl():
    assert determine_league("ВХЛ — Игра") == "VHL"
    assert determine_league("VHL match") == "VHL"


def test_determine_league_mhl():
    assert determine_league("МХЛ — Турнир") == "MHL"
    assert determine_league("MHL tournament") == "MHL"


def test_determine_league_none():
    assert determine_league("NHL game") is None
    assert determine_league("") is None
    assert determine_league("Liiga") is None


def test_parse_stream_url_youtube():
    result = parse_stream_url("https://www.onhockey.tv/np_youtube.php?channel=abc123", "youtube")
    assert result["source"] == "youtube"
    assert "abc123" in result["url"]


def test_parse_stream_url_vk():
    result = parse_stream_url("https://www.onhockey.tv/np_vk.php?channel=-123&id=456", "vklive")
    assert result["source"] == "vk"


def test_build_stream_url_relative():
    assert build_stream_url("/np_stream400.php?channel=test") == "https://www.onhockey.tv/np_stream400.php?channel=test"


def test_build_stream_url_protocol_relative():
    assert build_stream_url("//example.com/stream") == "https://example.com/stream"


def test_build_stream_url_absolute():
    assert build_stream_url("https://example.com/stream") == "https://example.com/stream"
