# ML Pipeline — CSI-based Indoor Localization

> **Status:** Work in progress. Will be populated as the project progresses.

## Planned Approach

1. **Feature Extraction** — amplitude + phase per subcarrier per antenna
2. **Fingerprinting** — build location-labeled CSI database
3. **Time Reversal** — apply time-reversal signal processing for multipath exploitation
4. **ML Models** — KNN, SVM, CNN for location classification

## Directory Structure (coming)

```
ml/
├── feature_extraction.py   ← Extract features from parsed CSI CSVs
├── fingerprint_db.py       ← Build and query fingerprint database
├── time_reversal.py        ← Time reversal signal processing
├── train.py                ← Train ML models
├── evaluate.py             ← Evaluate localization accuracy
└── models/                 ← Saved model files
```
