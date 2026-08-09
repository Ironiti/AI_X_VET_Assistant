import pytest

from utils.rich_broadcast import (
    RICH_BROADCAST_HEADER,
    RICH_MARKDOWN_MAX_CHARS,
    build_rich_broadcast_markdown,
    decode_markdown_file,
    is_markdown_filename,
)


def test_markdown_filename_is_case_insensitive():
    assert is_markdown_filename("announcement.md")
    assert is_markdown_filename("ANNOUNCEMENT.MD")
    assert not is_markdown_filename("announcement.txt")
    assert not is_markdown_filename(None)


def test_decode_markdown_file_supports_utf8_bom():
    content = decode_markdown_file(b"\xef\xbb\xbf# Title\n\n- item")

    assert content == "# Title\n\n- item"
    assert build_rich_broadcast_markdown(content) == (
        f"{RICH_BROADCAST_HEADER}\n\n# Title\n\n- item"
    )


@pytest.mark.parametrize("raw_content", [b"", b" \r\n "])
def test_decode_markdown_file_rejects_empty_content(raw_content):
    with pytest.raises(ValueError, match="пуст"):
        decode_markdown_file(raw_content)


def test_decode_markdown_file_requires_utf8():
    with pytest.raises(ValueError, match="UTF-8"):
        decode_markdown_file(b"\xff\xfe\x00")


def test_rich_markdown_limit_includes_broadcast_header():
    available = RICH_MARKDOWN_MAX_CHARS - len(RICH_BROADCAST_HEADER) - 2
    assert len(build_rich_broadcast_markdown("a" * available)) == RICH_MARKDOWN_MAX_CHARS

    with pytest.raises(ValueError, match="слишком длинное"):
        build_rich_broadcast_markdown("a" * (available + 1))
