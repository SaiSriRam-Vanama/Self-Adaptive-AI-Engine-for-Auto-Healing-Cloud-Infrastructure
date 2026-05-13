import pytest
from engine import AutoHealingEngine
import pandas as pd

def test_generate_metrics():
    engine = AutoHealingEngine()
    df = engine.generate_metrics()
    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) == {"Server", "CPU", "Memory", "Errors"}
    assert len(df) == len(engine.servers)

def test_update_history_and_risk_predictor():
    engine = AutoHealingEngine()
    df = engine.generate_metrics()
    engine.update_history(df)
    risks = engine.predict_risks()
    # Risks is list of dict or empty
    assert isinstance(risks, list)
