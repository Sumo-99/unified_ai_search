def test_package_exposes_version() -> None:
    import unified_ai_search

    assert isinstance(unified_ai_search.__version__, str)
    assert unified_ai_search.__version__
