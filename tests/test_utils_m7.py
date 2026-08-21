import pandas as pd
import pytest

from utils import format_dataframe


def test_format_dataframe_mixed_object_column_does_not_crash():
    """
    M7: An object-dtype column that is mostly numeric-like strings but
    contains one already pt-BR-formatted value (e.g. "1.234,56") must not
    crash the whole table render. The genuinely numeric cells should still
    get proper pt-BR formatting, and the offending cell should render as-is
    (not silently dropped) instead of raising ValueError.
    """
    df = pd.DataFrame({
        "Valor Total (R$)": ["1500.50", "200", "1.234,56"],
    })

    styler = format_dataframe(df)

    # Force pandas to actually execute the Styler.format() callbacks.
    html = styler.to_html()

    assert html is not None

    # Genuinely numeric cells should be formatted pt-BR style.
    assert "R$ 1.500,50" in html
    assert "R$ 200,00" in html

    # The already-formatted / non-convertible cell must still be present
    # (rendered as-is), not dropped or replaced by an error.
    assert "1.234,56" in html


def test_formatter_callback_falls_back_on_unconvertible_string_volume_column():
    """
    Direct check of the per-cell conversion logic used for object-dtype
    numeric-like columns (volume/quantity keywords branch): a value that
    float() cannot parse (because it is already pt-BR formatted) should be
    rendered as-is instead of raising.
    """
    df = pd.DataFrame({
        "Quantidade (Ton)": ["1500.50", "200", "1.234,56"],
    })

    styler = format_dataframe(df)

    # Force pandas to actually execute the Styler.format() callbacks.
    html = styler.to_html()

    assert "1.500,5" in html
    assert "200,0" in html
    assert "1.234,56" in html
