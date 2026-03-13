# NLQ Ground Truth Test Suite v2

107 cases. Zero deps. 4 endpoints. 11 assertion types.

v1 tested the label (metric ID). v2 tests the contents (data, units, values).

New assertions: data_must_exist, value_must_be_numeric, unit_must_be,
unit_must_not_be, breakdown_must_include, metrics_must_include_any,
metrics_must_include_all, data_count_min, field_must_exist.

Sections: MR(25) AL(14) BD(15) TM(8) STD(5) DB(12) UI(8) PD(5) DR(5skip) GD(4) NG(6)

Run: python run_tests.py --base-url http://localhost:PORT
Tags: --tag galaxy / dashboard-v2 / unit-integrity / persona / breakdown / alias / guardrail
