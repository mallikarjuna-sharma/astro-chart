# Stream-engine calibration protocol

The engine must not claim calibrated aptitude probabilities until calibration is
earned from data. Create a de-identified JSON dataset with one object per case:

```json
{
  "case_id": "stable-random-id",
  "observed_stream": "science",
  "consent_status": "DE_IDENTIFIED_CONSENTED",
  "birth_time_quality": "EXACT_RECORDED",
  "outcome_window_months": 24,
  "outcome_confirmed": true
}
```

`tools/validate_stream_calibration.py dataset.json` rejects duplicated cases,
missing consent, unconfirmed outcomes, poor birth-time quality, and datasets
with fewer than 120 independent cases (at least 30 per stream). Only a passing
dataset may produce a `VALIDATED_CALIBRATED` configuration. The scorer exposes
that state in every report; otherwise its values remain explicitly engineered
support indices. No fabricated benchmark or hand-tuned result is accepted as
calibration.
