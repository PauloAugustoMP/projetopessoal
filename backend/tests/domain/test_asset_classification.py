from backend.domain.asset_classification import infer_category


def test_a_rendimento_payout_identifies_a_reit():
    assert infer_category("TRXF11", {"reit_income"}) == "reit"


def test_dividends_or_jcp_identify_a_company_share():
    assert infer_category("POMO4", {"dividend"}) == "stock"
    assert infer_category("AURE3", {"jcp"}) == "stock"


def test_evidence_wins_over_the_ticker_suffix():
    # Units such as TAEE11/SAPR11 end in 11 but pay dividends/JCP, not rendimento.
    assert infer_category("TAEE11", {"jcp"}) == "stock"
    assert infer_category("SAPR11", {"dividend"}) == "stock"


def test_without_evidence_the_suffix_decides():
    assert infer_category("KNCR11") == "reit"
    assert infer_category("ALOS3") == "stock"
    assert infer_category("BBDC4") == "stock"


def test_subscription_rights_and_receipts_follow_their_underlying_reit():
    assert infer_category("AFHI12") == "reit"
    assert infer_category("AFHI13") == "reit"


def test_an_unrecognizable_ticker_defaults_to_stock():
    assert infer_category("XPTO") == "stock"
