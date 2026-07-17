import copy
import random
import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import sample_external_review_candidates as sampler


def row(candidate_id, session_id, category="其他", method="legacy_keyword", month="1", anomaly="", senders="1"):
    return {
        "external_candidate_id": candidate_id, "external_session_id": session_id,
        "candidate_status": "accepted", "refined_category": category,
        "role_inference_method": method, "source_month": month,
        "inferred_service_sender_count": senders, "parser_anomaly_types": anomaly,
        "role_inference_sender_session_count": "60", "role_inference_threshold_sessions": "58",
        "role_inference_first_ratio": "0.10", "role_inference_last_ratio": "0.82",
        "final_question": "问题", "final_answer": "回答",
    }


def synthetic_rows():
    rows = []
    index = 0
    for category in sampler.REPRESENTATIVE_QUOTAS:
        for method in sampler.METHODS:
            for month in range(1, 7):
                for _ in range(3):
                    index += 1; rows.append(row(f"c{index:04d}", f"s{index:04d}", category, method, str(month)))
    # Exactly two mixed and two statistical multi-sender role-special records.
    for method, senders in (("mixed", "1"), ("mixed", "1"), ("statistical_sender_rule", "2"), ("statistical_sender_rule", "2")):
        index += 1; rows.append(row(f"c{index:04d}", f"s{index:04d}", "其他", method, str((index % 6) + 1), "", senders))
    for anomaly, count in sampler.ANOMALY_QUOTAS.items():
        # Extra rows ensure representative selection can naturally consume some
        # anomaly candidates without starving the later audit subgroup.
        for _ in range(count + 30):
            index += 1; rows.append(row(f"c{index:04d}", f"s{index:04d}", "物流发货", "legacy_keyword", str((index % 6) + 1), anomaly))
    return rows


class SamplingTests(unittest.TestCase):
    def test_quotas_uniqueness_and_risk_groups(self):
        records, fallbacks = sampler.sample(synthetic_rows())
        self.assertEqual(len(records), 120)
        self.assertEqual(Counter(r["sample_group"] for r in records), Counter(representative=96, role_special=4, parser_anomaly=12, near_threshold=8))
        self.assertEqual(Counter(r["refined_category"] for r in records if r["sample_group"] == "representative"), sampler.REPRESENTATIVE_QUOTAS)
        self.assertEqual(len({r["external_candidate_id"] for r in records}), 120)
        self.assertEqual(len({r["external_session_id"] for r in records}), 120)
        self.assertEqual(len(fallbacks), 0)

    def test_repeatable_and_input_order_independent(self):
        rows = synthetic_rows()
        first, _ = sampler.sample(rows)
        second, _ = sampler.sample(copy.deepcopy(rows))
        shuffled = copy.deepcopy(rows); random.Random(91).shuffle(shuffled)
        third, _ = sampler.sample(shuffled)
        ids = lambda records: [r["external_candidate_id"] for r in records]
        self.assertEqual(ids(first), ids(second)); self.assertEqual(ids(first), ids(third))

    def test_fallback_is_traceable(self):
        rows = synthetic_rows()
        # Month 1 and 2 both receive quota for this role; force their rows to
        # share a session so the second cell must use its documented fallback.
        for item in rows:
            if item["refined_category"] == "价格补偿" and item["role_inference_method"] == "legacy_keyword" and item["source_month"] in {"1", "2"}:
                item["external_session_id"] = "shared-fallback-session"
        _, fallbacks = sampler.sample(rows)
        self.assertTrue(fallbacks)

    def test_privacy_sanitization(self):
        text = "电话13800138000 地址[ADDRESS_RELATED_MESSAGE] https://secret.example C:\\Users\\name"
        clean = sampler.sanitize(text)
        self.assertFalse(sampler.has_residual_pii(clean))


if __name__ == "__main__":
    unittest.main()
