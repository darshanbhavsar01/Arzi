# Arzi eval report (replay mode)

Deterministic engine plus recorded agent answers, synthetic demo cases only.

| Case | Run completed | Totals exact (paise) | Flags caught | Flag amounts exact | Narration passed guardrails | Latency (s) |
|---|---|---|---|---|---|---|
| case_a | True | True | 4/4 | 4/4 | True | 0.37 |
| case_b | True | True | 6/6 | 6/6 | True | 0.20 |
| case_c | True | True | 1/1 | 1/1 | True | 0.23 |

- Flag precision: 11/11; recall: 11/11
- Rupee exact-match (flag amounts): 11/11
- Median end-to-end latency (replay): 0.23 s
- Cost per claim in replay: INR 0 (live cost is measured in the cost ledger).
