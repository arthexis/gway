import pytest

from gway.console import Token, chunk, process, tokenize


def test_double_quotes_group_spaces():
    assert tokenize('echo "hello world"') == [
        Token("echo"), Token("hello world", "double")
    ]


def test_single_quotes_group_spaces_as_literal():
    tokens = tokenize("echo 'hello world'")
    assert tokens == [Token("echo"), Token("hello world", "single")]
    assert tokens[1].literal is True


def test_embedded_dash_is_ordinary_text():
    assert tokenize("echo charger-alpha-01") == [
        Token("echo"), Token("charger-alpha-01")
    ]


def test_single_quoted_flag_like_value_is_literal(gateway):
    def echo(value: str):
        return value
    gateway.echo = gateway.wrap_callable("echo_value", echo)
    _, last = process([[Token("echo"), Token("--special", "single")]], gw_instance=gateway)
    assert last == "--special"


def test_unquoted_flag_like_positional_is_syntax(gateway):
    def echo(value: str):
        return value
    gateway.echo = gateway.wrap_callable("echo_value", echo)
    with pytest.raises(TypeError, match="Unknown argument"):
        process([["echo", "--special"]], gw_instance=gateway)


def test_double_quoted_flag_like_positional_remains_syntax(gateway):
    def echo(value: str):
        return value
    gateway.echo = gateway.wrap_callable("echo_value", echo)
    with pytest.raises(TypeError, match="Unknown argument"):
        process([[Token("echo"), Token("--special", "double")]], gw_instance=gateway)


def test_single_quoted_dash_does_not_split_stage():
    assert chunk([Token("echo"), Token("-", "single")]) == [[Token("echo"), Token("-", "single")]]


def test_single_quoted_semicolon_does_not_split_stage():
    assert chunk([Token("echo"), Token(";", "single")]) == [[Token("echo"), Token(";", "single")]]


def test_unquoted_dash_splits_stage():
    assert chunk([Token("one"), Token("-"), Token("two")]) == [[Token("one")], [Token("two")]]


def test_double_dash_ends_option_parsing(gateway):
    def echo(value: str):
        return value
    gateway.echo = gateway.wrap_callable("echo_value", echo)
    _, last = process([[Token("echo"), Token("--"), Token("--special")]], gw_instance=gateway)
    assert last == "--special"


def test_single_quoted_sigil_is_not_resolved(gateway):
    gateway.context["site"] = "MTY"
    def echo(value: str):
        return value
    gateway.echo = gateway.wrap_callable("echo_value", echo)
    _, last = process([[Token("echo"), Token("[site]", "single")]], gw_instance=gateway)
    assert last == "[site]"


def test_double_quoted_sigil_can_resolve(gateway):
    gateway.context["site"] = "MTY"
    def echo(value: str):
        return value
    gateway.echo = gateway.wrap_callable("echo_value", echo)
    _, last = process([[Token("echo"), Token("[site]", "double")]], gw_instance=gateway)
    assert last == "MTY"


def test_single_quoted_numeric_text_stays_string(gateway):
    def echo(value: int):
        return value
    gateway.echo = gateway.wrap_callable("echo_value", echo)
    _, last = process([[Token("echo"), Token("32", "single")]], gw_instance=gateway)
    assert last == "32"
    assert isinstance(last, str)


def test_double_quoted_numeric_text_uses_signature_conversion(gateway):
    def echo(value: int):
        return value
    gateway.echo = gateway.wrap_callable("echo_value", echo)
    _, last = process([[Token("echo"), Token("32", "double")]], gw_instance=gateway)
    assert last == 32


def test_empty_single_quoted_string_is_preserved():
    assert tokenize("echo ''") == [Token("echo"), Token("", "single")]


def test_unterminated_single_quote_fails():
    with pytest.raises(ValueError, match="Unterminated single-quoted string"):
        tokenize("echo 'oops")


def test_unterminated_double_quote_fails():
    with pytest.raises(ValueError, match="Unterminated double-quoted string"):
        tokenize('echo "oops')
