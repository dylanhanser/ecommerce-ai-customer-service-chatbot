# external_store_v1 adjudication setup

- Primary input SHA-256: `cf1c1e9ca76dd76acca50576adfb860ac69a7279ff045eb540e1626c580c2767`
- Secondary input SHA-256: `874fcfa587aa9619f72ff2fba5595791fef1ddefa26a59b5954d597b731c360a`
- Disputed review IDs: R010, R011, R013, R016, R025, R030, R051, R054, R061, R064, R081, R095, R100, R104, R105, R115
- Field disagreement counts: pair_valid 3; question_self_contained 9; answer_relevance 11; role_pairing_correct 0; answer_usable_as_reference 8; residual_pii_found 1; gold_category 0; exclude_reason 15.
- Total field disagreements: 47
- Eligibility disagreements: 7
- Template SHA-256: `866645afa373849f55d79cbaf130f85d677574bd53be2122a28dca8d227d276b`
- Tests: `scripts/test_external_review_adjudication.py` 6 passed; `scripts/test_external_review_protocol.py` 10 passed.
- Current status: INCOMPLETE
