# Pricing-policy consistency fix

## One decision rule

- **COMPLIANT**: a policy price is known and `Net Pay` equals `Policy Trip Price` within $0.005, or the policy explicitly records an approved exception.
- **NON_COMPLIANT**: a policy price is known and `Net Pay - Policy Trip Price` is outside the tolerance.
- **NOT_VERIFIABLE**: the policy price, route, mileage input, or another required comparison input is missing. This is never counted as compliant.

The report keeps data reconciliation separate from pricing compliance. `MATCHED`, `STATE REPORT NOT UPLOADED`, and similar reconciliation labels are not used as pricing-policy approval.

## Financial definitions

- **Gross Pay** = state-report trip revenue.
- **Net Pay** = current driver payment.
- **Difference** = Net Pay - Policy Trip Price.
- **Loss from non-compliance** = positive differences only (payments above policy).
- **Projected profit** = actual profit + loss from non-compliance.
- The dashboard and PDF show trip counts, coverage, non-compliance percentage, loss, loss as a percentage of Gross Pay, actual margin, and projected margin.

## Verification

`python3 -m py_compile simple_reports.py app.py pdf_generator.py` passes in this package. The UI and downloadable PDF now call the same `policy_compliance_report` function, so they cannot silently use different compliance rules.
