from wayback_mcp.client.extractor import (
    extract_html,
    extract_plaintext,
    classify_mime,
    WORD_THRESHOLD,
    WORD_CAP,
    PLAINTEXT_CAP,
)


def _words(n: int) -> str:
    return " ".join(["word"] * n)


# --- Tracer bullet ---

def test_article_tag_used_when_content_exceeds_threshold():
    html = f"<html><body><article>{_words(300)}</article></body></html>"
    result = extract_html(html)
    assert result.method == "article"
    assert result.word_count >= WORD_THRESHOLD


# --- Semantic container priority ---

def test_main_tag_preferred_over_article():
    html = f"<html><body><main>{_words(300)}</main><article>{_words(300)}</article></body></html>"
    result = extract_html(html)
    assert result.method == "main"


def test_role_main_used_when_no_main_or_article():
    html = f'<html><body><div role="main">{_words(300)}</div></body></html>'
    result = extract_html(html)
    assert result.method == "role-main"


def test_sparse_semantic_tag_falls_through_to_body():
    # <main> present but only 10 words — below threshold → body-fallback
    sparse_main = _words(10)
    body_text = _words(400)
    html = f"<html><body><main>{sparse_main}</main><p>{body_text}</p></body></html>"
    result = extract_html(html)
    assert result.method == "body-fallback"
    assert result.word_count > WORD_THRESHOLD


# --- Body-fallback cleanup ---

def test_script_and_style_stripped_in_body_fallback():
    html = (
        "<html><body>"
        "<script>var x = 1;</script>"
        "<style>.cls { color: red; }</style>"
        f"<p>{_words(50)}</p>"
        "</body></html>"
    )
    result = extract_html(html)
    assert "var x" not in result.text
    assert ".cls" not in result.text


def test_wayback_toolbar_stripped_in_body_fallback():
    toolbar = '<div id="wm-ipp-base">WAYBACK TOOLBAR INJECTED CONTENT</div>'
    html = f"<html><body>{toolbar}<p>{_words(50)}</p></body></html>"
    result = extract_html(html)
    assert "WAYBACK TOOLBAR" not in result.text


# --- Truncation ---

def test_html_truncated_at_word_cap():
    html = f"<html><body><p>{_words(WORD_CAP + 500)}</p></body></html>"
    result = extract_html(html)
    assert result.truncated is True
    assert result.word_count == WORD_CAP


def test_html_not_truncated_when_under_cap():
    html = f"<html><body><p>{_words(100)}</p></body></html>"
    result = extract_html(html)
    assert result.truncated is False


# --- Plain text ---

def test_plaintext_returned_as_is():
    text = "Hello world. " * 50
    result = extract_plaintext(text)
    assert result.method == "plain-text"
    assert result.text == text
    assert result.truncated is False


def test_plaintext_truncated_at_char_cap():
    text = "a" * (PLAINTEXT_CAP + 100)
    result = extract_plaintext(text)
    assert result.truncated is True
    assert len(result.text) == PLAINTEXT_CAP


# --- Link density: nav-heavy containers fall through ---

def test_nav_heavy_main_falls_through_to_body():
    # <main> content is all <a> tags — high link density → should not be accepted
    nav = "".join(f'<a href="#">{"word " * 25}</a>' for _ in range(15))
    body_content = _words(400)
    html = f"<html><body><main>{nav}</main><p>{body_content}</p></body></html>"
    result = extract_html(html)
    assert result.method == "body-fallback"


def test_content_rich_article_accepted_despite_some_links():
    # <article> has links but they're a minority of the text
    article = f"<article><p>{_words(300)}</p><a href='#'>Read more</a></article>"
    html = f"<html><body>{article}</body></html>"
    result = extract_html(html)
    assert result.method == "article"


# --- MIME type classification ---

def test_classify_text_html():
    assert classify_mime("text/html") == "html"


def test_classify_xhtml():
    assert classify_mime("application/xhtml+xml") == "html"


def test_classify_with_charset_param():
    assert classify_mime("text/html; charset=utf-8") == "html"


def test_classify_text_plain():
    assert classify_mime("text/plain") == "plain"


def test_classify_pdf_declined():
    assert classify_mime("application/pdf") == "declined"


def test_classify_image_declined():
    assert classify_mime("image/jpeg") == "declined"
    assert classify_mime("image/png") == "declined"


def test_classify_video_declined():
    assert classify_mime("video/mp4") == "declined"


def test_classify_audio_declined():
    assert classify_mime("audio/mpeg") == "declined"


def test_classify_binary_declined():
    assert classify_mime("application/octet-stream") == "declined"
    assert classify_mime("application/zip") == "declined"


def test_classify_office_docs_declined():
    assert classify_mime("application/msword") == "declined"
    assert classify_mime("application/vnd.openxmlformats-officedocument.wordprocessingml.document") == "declined"


def test_classify_unknown_declined():
    assert classify_mime("application/x-unknown-type") == "declined"
