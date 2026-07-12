"""Smoke tests for the public package scaffold."""


def test_package_imports() -> None:
    import bill_titles

    assert bill_titles.__doc__ is not None
