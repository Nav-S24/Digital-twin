# Phase 9 — Driver Behaviour Analytics

Part of **Personalized Vehicle Brain & Health Digital Twin with Natural Language
Intelligence**. This phase analyzes VED (Vehicle Energy Dataset) driving logs to
score, profile, and coach individual drivers.

## Folder Structure

```
phase9_driver_behavior/
├── config/settings.py              # all thresholds, weights, paths (env-overridable)
├── preprocessing/data_loader.py    # Step 1: load, clean, segment VED data
├── feature_engineering/feature_extractor.py  # Step 2: trip-level features
├── detection/behavior_detector.py  # Step 3: event-level behaviour detection
├── profiling/driver_profiler.py    # Step 4: driver profile classification
├── scoring/driver_scorer.py        # Step 5: 0-100 driver score
├── coaching/coaching_engine.py     # Step 6: rule-based coaching
├── coaching/llm_coach.py           # Step 10: LLM narrative + reports
├── api/main.py                     # Step 7: FastAPI REST endpoints
├── dashboard/app.py                # Step 8: Streamlit dashboard
├── visualization/plots.py          # Step 9: Plotly charts
├── models/schemas.py               # Pydantic request/response schemas
├── utils/logger.py, exceptions.py  # cross-cutting concerns
├── tests/                          # pytest suite (40 tests)
├── pipeline.py                     # orchestrator shared by API/dashboard/CLI
├── main.py                         # CLI entry point
├── requirements.txt
└── .env.example
```

## Setup

```bash
cd phase9_driver_behavior
pip install -r requirements.txt
cp .env.example .env   # optional: add ANTHROPIC_API_KEY / OPENAI_API_KEY for LLM coaching
```

Place VED CSV files (e.g. `VED_171101_week.csv`, extracted from the official
`VED_DynamicData_Part1.7z` / `Part2.7z` archives) under `data/raw/`.

## Usage

**CLI (batch run + console report):**
```bash
python main.py --source data/raw/VED_171101_week.csv --veh-id 8
```

**REST API:**
```bash
uvicorn api.main:app --reload --port 8009
# then:
curl -X POST "http://localhost:8009/pipeline/run?source=data/raw/VED_171101_week.csv"
curl "http://localhost:8009/driver/profile?veh_id=8"
curl "http://localhost:8009/driver/score?veh_id=8"
curl "http://localhost:8009/driver/coaching?veh_id=8"
curl "http://localhost:8009/driver/statistics?veh_id=8"
curl "http://localhost:8009/driver/trips?veh_id=8"
```
Interactive docs at `http://localhost:8009/docs`.

**Dashboard:**
```bash
streamlit run dashboard/app.py
```
Enter the `data/raw` path (or a specific CSV) in the sidebar and click
**Load / Refresh Data**.

**Tests:**
```bash
pytest tests/ -v
```

## Design Notes & Calibration

- **VED timestamp reconstruction**: `DayNum` (fractional days since Nov 1, 2017)
  + `Timestamp(ms)` are combined into an absolute `timestamp` column.
- **GPS-derived kinematics are noise-guarded**: heading/bearing is only
  recomputed when the vehicle has moved ≥3m between fixes (otherwise the
  previous heading is carried forward), and acceleration is derived from a
  3-point rolling-median-smoothed speed signal with a minimum 0.4s time
  delta — both guard against consumer-GPS/OBD sampling jitter being
  misread as harsh events. This was empirically tuned against the real
  VED sample: without it, GPS jitter alone produced 10,000+ false
  "sharp cornering" events in one week of data.
- **Overspeeding uses a road-context-aware limit** (city/arterial/highway),
  not one flat number, since VED mixes highway and downtown driving.
- **Event rates are normalized per hour of driving time, not distance.**
  Distance-based normalization (events per 100km) was tried first but
  systematically over-penalized slow, congested city driving: at low
  speed a vehicle covers little distance per unit time, so a normal
  amount of stop-and-go behaviour got inflated into an extreme "rate"
  purely because the denominator (km) was small — it made typical
  Ann Arbor city trips look worse than free-flowing highway trips
  regardless of actual behaviour. A 5-minute duration floor prevents
  very short trips from producing runaway rates the same way.
- **Rapid lane change vs. sharp cornering are split by speed regime,
  not lateral-acceleration magnitude.** An earlier version tried to
  tell them apart using `lateral_accel < threshold`, but lateral
  acceleration is derived as `speed × heading_rate`, so requiring a
  large heading swing *and* a small lateral acceleration at highway
  speed is close to a mathematical contradiction — the detector never
  fired. It's now: sharp cornering below the highway-speed floor,
  rapid lane change above it.
- **Coaching never depends on the LLM being available.** `RuleBasedCoach`
  always runs first; `LLMCoach` (Anthropic or OpenAI, configurable) adds a
  narrative on top and is skipped silently on any failure.

## Verified Against Real Data

This module was built and validated against the actual VED dataset
(`VED_171101_week.csv`, part of a 383-vehicle Ann Arbor, MI fleet), not
synthetic placeholders — every module in the pipeline was run end-to-end
on real rows before being finalized, including a full-week stress test
(489,415 raw rows → 849 valid trips across 257 vehicles) to catch
calibration issues that don't show up on a small sample.

**Full week-1 result after calibration:** mean driver score 83.7
(median 88.4), profile distribution — Safe Driver 362, Eco Driver 340,
Normal Driver 92, High Risk Driver 53, Aggressive Driver 2. This
right-skewed shape (most trips safe, a meaningful minority flagged) is
consistent with typical usage-based-insurance telematics distributions.

A first pass at this calibration had a real flaw worth documenting: the
bonus terms (consistent speed, fuel efficiency, low idle) could
routinely outweigh a typical trip's penalty, so ~28% of trips landed
at exactly the 100-point ceiling after clipping — even though only
0.1% of trips had zero detected events at all. That's a pile-up
artifact, not 28% of drivers genuinely being flawless. Bonus weights
were reduced (`max_bonus_cap` 15→6, individual bonus weights ~2.5x
smaller) so bonus nudges a score up without routinely overshooting
100. After the fix, 7.9% of trips land at exactly 100 — still not
perfectly smooth, but a defensible "near-flawless trip" bucket rather
than a systemic ceiling-clipping bug.


