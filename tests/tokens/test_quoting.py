import pytest

from gway.console import process
from gway.tokens import Token, chunk, statements, tokenize


def _echo(gateway, annotation=str):
    def echo(value: annotation):
        return value

    gateway.echo = gateway.wrap("echo_value", echo)


def _run(gateway, *tokens):
    _, last = process([[Token("echo"), *tokens]], gw_instance=gateway)
    return last


def test_quotes_group_spaces_and_preserve_provenance():
    assert tokenize('echo "hello world"') == [
        Token("echo"),
        Token("hello world", "double"),
    ]

    tokens = tokenize("echo 'hello world'")
    assert tokens == [Token("echo"), Token("hello world", "single")]
    assert tokens[1].literal is True


def test_embedded_dash_is_ordinary_text():
    assert tokenize("echo charger-alpha-01") == [
        Token("echo"),
        Token("charger-alpha-01"),
    ]


def test_single_quoted_flag_like_value_is_literal(gateway):
    _echo(gateway)
    assert _run(gateway, Token("--special", "single")) == "--special"


@pytest.mark.parametrize("quote", [None, "double"])
def test_nonliteral_flag_like_positional_is_syntax(gateway, quote):
    _echo(gateway)
    token = Token("--special", quote) if quote else Token("--special")

    with pytest.raises(TypeError, match="Unknown argument"):
        _run(gateway, token)


@pytest.mark.parametrize(
    ("separator", "splitter"),
    [
        ("-", chunk),
        (";", statements),
    ],
)
@pytest.mark.parametrize("quote", ["single", "double"])
def test_quoted_separators_do_not_split(separator, splitter, quote):
    tokens = [Token("echo"), Token(separator, quote)]
    assert splitter(tokens) == [tokens]


@pytest.mark.parametrize(
    ("separator", "splitter"),
    [
        ("-", chunk),
        (";", statements),
    ],
)
def test_unquoted_separators_split(separator, splitter):
    assert splitter([Token("one"), Token(separator), Token("two")]) == [
        [Token("one")],
        [Token("two")],
    ]


def test_semicolon_is_not_a_pipeline_separator():
    tokens = [Token("one"), Token(";"), Token("two")]
    assert chunk(tokens) == [tokens]


def test_double_dash_ends_option_parsing(gateway):
    _echo(gateway)
    assert _run(gateway, Token("--"), Token("--special")) == "--special"


@pytest.mark.parametrize(
    ("quote", "expected"),
    [
        ("single", "[site]"),
        ("double", "MTY"),
    ],
)
def test_quoted_sigil_semantics(gateway, quote, expected):
    gateway.context["site"] = "MTY"
    _echo(gateway)

    assert _run(gateway, Token("[site]", quote)) == expected


@pytest.mark.parametrize(
    ("quote", "expected"),
    [
        ("single", "[charger [field]]"),
        ("double", "ABC"),
    ],
)
def test_nested_sigil_semantics(gateway, quote, expected):
    gateway.context["field"] = "serial"
    gateway.context["charger"] = {"serial": "ABC"}
    _echo(gateway)

    assert _run(gateway, Token("[charger [field]]", quote)) == expected


@pytest.mark.parametrize(
    ("quote", "expected", "expected_type"),
    [
        ("single", "32", str),
        ("double", 32, int),
    ],
)
def test_quoted_numeric_signature_conversion(gateway, quote, expected, expected_type):
    _echo(gateway, int)

    last = _run(gateway, Token("32", quote))

    assert last == expected
    assert isinstance(last, expected_type)


def test_empty_single_quoted_string_is_preserved():
    assert tokenize("echo ''") == [Token("echo"), Token("", "single")]


@pytest.mark.parametrize(
    ("source", "quote"),
    [
        ("echo 'oops", "single"),
        ('echo "oops', "double"),
    ],
)
def test_unterminated_quote_fails(source, quote):
    with pytest.raises(ValueError, match=f"Unterminated {quote}-quoted string"):
        tokenize(source)


@pytest.mark.parametrize("value", [";", "-"])
def test_double_quoted_separator_reaches_operation_as_argument(gateway, value):
    _echo(gateway)
    assert _run(gateway, Token(value, "double")) == value
