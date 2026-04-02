# Unified Monte Carlo Final Verification

This directory stores only the final successful unified Monte Carlo run.

## Execution order
1. Compare baseline vs candidate engines on overlapping models.
2. Pick winners using the quality-first rule: accuracy > completeness > stability > speed.
3. Re-run the full Data Lab baseline suite with winners enabled.
4. Merge successful split model-upgrade chunks.
5. Run strict site-access checks and strict optimization validation.
6. Persist the final results here only after every step passes.

## Final successful summary
- Completed at: 2026-04-02T11:17:26.136001+08:00
- Compared overlap methods: 19
- Winner file updated: True
- Core Data Lab status: passed
- Core Data Lab model count: 33
- Upgrade suite status: passed
- Upgrade suite model count: 57
- Site access status: passed
- Optimization status: passed
- Optimization success count: 27

## Review order
1. Open `comparison_report.json` and `verification_report.json` at the root.
2. Review `country_panel/` and `macro_finance_ts/` result bundles.
3. Review `model_anchor/` for the upgrade and anchoring outputs.
4. Review `site_access/verification_report.json`.
5. Review `optimization/verification_report.json`, then inspect `optimization/figures/` and `optimization/tables/`.