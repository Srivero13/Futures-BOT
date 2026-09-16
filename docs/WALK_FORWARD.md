# Chronological walk-forward research

Use `walkforward_v16.py` to check whether forecast ranking persists across
chronological periods. This CPU-only research tool does not use CUDA or a GPU,
send orders, approve artifacts, or search for the most profitable parameters.

## Requirements and run

Use Python 3.12 and the pinned base requirements. No extra packages are required.
Provide chronological one-minute Binance CSV shards with matching JSON checksum
sidecars. Earlier history must contain enough examples for fitting; each fold
also needs at least 30 accepted calibration and test examples on the ranking grid.

Example: six monthly tests from March through August 2026, with existing ETH data:

```bash
python walkforward_v16.py \
  --files data/market-expanded/binance-ETHUSDT-*.csv \
  --symbol ETHUSDT \
  --first-test 2026-03-01 \
  --months 6 \
  --model linear \
  --horizon 3 \
  --alpha 10 \
  --work-dir data/walkforward-models \
  --output data/eth-linear-walkforward.json
```

This is finite work, not a timed training session. It performs several training
and ranking passes; wait for `Completed:`. Progress shows the frozen schedule,
training stages and each fold's ranking report. Some input-reading passes have
no per-batch progress. It can run beside a live observer, but both share CPU/disk.
Use an existing tmux session if terminal disconnect survival is needed.

The work directory stores guarded training artifacts for each fold. After an
interruption, repeat the same command to reuse completed fits. Ranking is
recomputed. No aggregate report is written until all folds complete and input
hashes are rechecked. Existing aggregate reports cannot be overwritten: choose
a new output filename when intentionally rerunning. No active model is replaced.

## Fixed protocol

| Test month | Training data ends before | Calibration month |
|---|---|---|
| March 2026 | February 1, 2026 | February 2026 |
| April 2026 | March 1, 2026 | March 2026 |
| May 2026 | April 1, 2026 | April 2026 |
| June 2026 | May 1, 2026 | May 2026 |
| July 2026 | June 1, 2026 | June 2026 |
| August 2026 | July 1, 2026 | July 2026 |

Training expands from the earliest supplied history. All boundaries are UTC,
with exclusive ends. Label ends crossing boundaries are excluded by the existing
trainer. Feature scaling is fit only on training data. Earlier test months can
enter later training prefixes, as they would become historical data over time.
Do not choose model type, horizon, or alpha after inspecting this schedule and
then present the same months as untouched validation.

For ranking, predictions and labels are sampled on a fixed UTC grid whose stride
is the horizon. This removes overlapping label intervals; it does not remove all
serial dependence. Both calibration and test reject model-OOD examples.

The 20th, 40th, 60th and 80th percentiles of accepted **calibration forecasts**
define bucket boundaries. Test returns never set those boundaries. Duplicate
cuts collapse, constant calibration forecasts produce one bucket, and empty
test buckets report null means. Exact Spearman ranks use average ranks for ties.
Constant test forecasts or returns have undefined correlation, reported as null.

## Read the results

Each fold records:

- Pearson and Spearman correlation between forecasts and subsequent returns.
- Counts and mean forecasts/actual returns for calibration-defined buckets.
- Highest-minus-lowest bucket mean actual return in log-basis-points.
- RMSE and zero-return RMSE on the same accepted grid examples.
- Calibration/test sample counts and OOD rejections.
- Existing training holdout diagnostics, explicitly labeled as overlapping.
- Model paths/checksums, boundaries, input checksums, and implementation hashes.

The summary counts folds with positive rank correlation and positive bucket
spread. Its mean correlation is equally weighted across defined folds. These
are descriptive metrics, not a significance test, probability of success, or
selection criterion. A positive bucket spread is not net P&L: it excludes costs,
execution, and an implementable position rule. July–August has already been
inspected in this project, and the full study is retrospective research.

The rank calculation caps each calibration/test segment at 100,000 accepted
examples and fails rather than silently subsampling beyond it. Monthly one-minute
segments fit under this cap. Input candles stream; exact ranks retain only these
bounded forecast/return pairs. Gaps reset feature windows but are not filled;
counts reveal sample availability, not a certificate of continuous coverage.

Possible next decisions must follow the results: consistent descriptive ranking
may justify a separately specified execution experiment; weak/inconsistent ranking
suggests revisiting features or targets. Neither outcome automatically promotes
a model. GPU installation does not alter this implementation's calculations.

## Longer horizons and fixed baselines

Research supports horizons of 1, 3, 5, 15, and 60 one-minute bars. The longer
horizons are available in training, model loading, diagnostics, walk-forward
ranking, and the offline execution backtest. Existing artifacts remain readable.
Training implementation hashes change with this update, so new training runs
receive new identities; historical artifacts are not rewritten.

Each fold now evaluates three fixed forecast baselines on exactly the same
model-accepted timestamps:

| Baseline | Predicted log return in basis points |
|---|---|
| Momentum | Previous 20-minute log return × 10,000 × horizon / 20 |
| Mean reversion | Negative of that momentum forecast |
| Zero | 0 |

The momentum rule assumes a constant recent trend rate; it is a deliberately
simple comparator, not a fitted or calibrated strategy. Reversal assumes the
opposite sign. Each nonconstant baseline has its own calibration-defined buckets.
RMSE and ranking are compared on identical rows, so model OOD rejection cannot
silently give a baseline a different evaluation sample. This is a conditional
comparison, not standalone baseline performance on every market observation.
No baseline bucket statistics include costs or simulated fills.

Summary fields include model-versus-baseline RMSE fold counts, each baseline's
mean defined Spearman correlation, and the model's top-bucket count and gross
mean return by month. The zero baseline has undefined rank correlation. Better
ranking or RMSE is not an economic promotion criterion.

## Declare development and reserved dates

Use `--reserve-from YYYY-MM-DD` to prohibit any development fold from extending
past that boundary. The runner records dates, model settings, baseline definitions,
source checksums, and runner hash in an adjacent `.protocol.json` **before fitting**.
A rerun with a different saved protocol fails; use a new output name for an
explicitly different experiment. Completed aggregate reports are still protected.
The protocol file persists if training fails or is interrupted.

For the next development experiment, keep the existing March–August schedule,
linear model, alpha 10, and compare the two declared horizons, 15 and 60 minutes.
Reserve September 1 onward from these development runs:

```bash
for horizon in 15 60; do
  python walkforward_v16.py \
    --files data/market-expanded/binance-ETHUSDT-*.csv \
    --symbol ETHUSDT \
    --first-test 2026-03-01 \
    --months 6 \
    --model linear \
    --horizon "$horizon" \
    --alpha 10 \
    --reserve-from 2026-09-01 \
    --work-dir data/walkforward-long-models \
    --output "data/eth-linear-h${horizon}-development.json" || break
done
```

This evaluates a finite, predefined comparison; it is not an adaptive parameter
search. Results for March–August are development evidence. The date guard only
applies to this runner with the supplied flag; it cannot certify that a period
was unseen elsewhere or prevent all other tools from reading it. No reserved
period is automatically evaluated. Wait for complete reserved data, record a
fixed hypothesis and acceptance criteria before accessing its outcomes, and
interpret the result as validation only if the period actually stayed unexamined.
Longer horizons yield fewer non-overlapping examples per month, so apparent
improvements require care. No new profitability, accuracy, or GPU-speed claim
is made by adding these horizons.
