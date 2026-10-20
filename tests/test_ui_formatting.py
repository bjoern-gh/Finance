"""Unit tests for UI data representation formatting in streamlit_app."""

import pandas as pd
from streamlit_app import (
    format_2_decimals,
    format_target_upside,
    get_column_config,
    style_dataframe,
    KNOWN_FLOAT_COLUMNS,
)


def test_format_2_decimals():
    assert format_2_decimals(1.2) == "1.20"
    assert format_2_decimals(1.200000) == "1.20"
    assert format_2_decimals(123.456) == "123.46"
    assert format_2_decimals(10) == "10.00"
    assert format_2_decimals(-5.1) == "-5.10"
    assert format_2_decimals(None) == "N/A"
    assert format_2_decimals(pd.NA) == "N/A"
    assert format_2_decimals("N/A") == "N/A"
    assert format_2_decimals("") == "N/A"
    assert format_2_decimals("invalid") == "invalid"


def test_format_target_upside():
    assert format_target_upside(15.6) == "16%"
    assert format_target_upside(25.0) == "25%"
    assert format_target_upside(-3.2) == "-3%"
    assert format_target_upside(0.0) == "0%"
    assert format_target_upside(None) == "-"
    assert format_target_upside(pd.NA) == "-"
    assert format_target_upside("N/A") == "-"
    assert format_target_upside("") == "-"


def test_get_column_config():
    df = pd.DataFrame(
        {
            "Company": ["Apple", "Microsoft"],
            "Price": [1.2, 123.4567],
            "Buy Score": [85, 60],
            "Target Upside (%)": [15.6, -3.2],
            "52W High (%)": [-5.12, -12.34],
            "Custom Float": [3.1415, 2.7182],
            "Custom Int": [1, 2],
            "Market Cap": ["2.50T", "45.6M"],
            "Valuation": ["Fair", "Cheap"],
        }
    )

    cfg = get_column_config(df)

    # Float columns -> %.2f
    assert cfg["Price"]["type_config"]["format"] == "%.2f"
    assert cfg["52W High (%)"]["type_config"]["format"] == "%.2f"
    assert cfg["Custom Float"]["type_config"]["format"] == "%.2f"

    # Target upside -> %.0f%% (full percentage without separator)
    assert cfg["Target Upside (%)"]["type_config"]["format"] == "%.0f%%"

    # Integer columns -> %.0f
    assert cfg["Buy Score"]["type_config"]["format"] == "%.0f"
    assert cfg["Custom Int"]["type_config"]["format"] == "%.0f"

    # Non-numeric columns should not have number config
    assert "Company" not in cfg
    assert "Market Cap" not in cfg
    assert "Valuation" not in cfg


def test_style_dataframe_formatting():
    df = pd.DataFrame(
        {
            "Company": ["Apple", "Microsoft"],
            "Price": [1.2, 123.4567],
            "Target Upside (%)": [15.6, -3.2],
            "Valuation": ["Fair", "Cheap"],
            "Buy Score": [85, pd.NA],
        }
    )

    styler = style_dataframe(df)
    styler._compute()

    # Verify formatted values in styler display functions
    # Row 0: Apple, Price 1.20, Target Upside 16%
    assert styler._display_funcs[(0, 0)](df.iloc[0, 0]) == "Apple"
    assert styler._display_funcs[(0, 1)](df.iloc[0, 1]) == "1.20"
    assert styler._display_funcs[(0, 2)](df.iloc[0, 2]) == "16%"

    # Row 1: Microsoft, Price 123.46, Target Upside -3%, missing Buy Score '-'
    assert styler._display_funcs[(1, 0)](df.iloc[1, 0]) == "Microsoft"
    assert styler._display_funcs[(1, 1)](df.iloc[1, 1]) == "123.46"
    assert styler._display_funcs[(1, 2)](df.iloc[1, 2]) == "-3%"
    assert styler._display_funcs[(1, 4)](df.iloc[1, 4]) == "-"


def test_known_float_columns_all_configured():
    df = pd.DataFrame({col: [1.2, None] for col in KNOWN_FLOAT_COLUMNS})
    cfg = get_column_config(df)
    for col in KNOWN_FLOAT_COLUMNS:
        assert col in cfg
        assert cfg[col]["type_config"]["format"] == "%.2f"
