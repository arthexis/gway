def test_console_keeps_temporary_extracted_reexports():
    from gway import console
    from gway.recipes import load_recipe
    from gway.tokens import Token, chunk, tokenize

    assert console.Token is Token
    assert console.tokenize is tokenize
    assert console.chunk is chunk
    assert console.load_recipe is load_recipe
