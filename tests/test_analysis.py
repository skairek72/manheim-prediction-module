from pathlib import Path

from manheim_pm.load import load_sales
from manheim_pm.movers import movers
from manheim_pm.pitches import pitches
from manheim_pm.trends import trends

SAMPLE = Path(__file__).parent.parent / "data" / "sample_sales.csv"


def test_pipeline_ranks_known_trends():
    df = load_sales(SAMPLE)
    mv, tr = movers(df), trends(df)

    # The sample data builds in rising demand for RAV4 and falling demand for Model 3 / Altima.
    assert tr.loc["Toyota RAV4", "direction"] == "heating up"
    assert tr.loc["Tesla Model 3", "direction"] == "cooling"
    assert tr.loc["Nissan Altima", "direction"] == "cooling"
    assert set(tr.tail(2).index) == {"Tesla Model 3", "Nissan Altima"}
    assert mv.loc["Toyota RAV4", "sell_through"] > mv.loc["Tesla Model 3", "sell_through"]

    out = pitches(mv, tr)
    assert out and all(p.strip() for p in out)
