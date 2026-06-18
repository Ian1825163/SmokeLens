# Cigarette Smoke Window Plot

## Codex Handoff Summary

Purpose:

- Build a compact visualization that shows one clean `normal_air -> cigarette_smoke -> normal_air` transition from `data/smokelens.csv`.
- The chart should be presentation-ready and should reflect the values actually shown on the dashboard.

Current branch work:

- Created this analysis folder and reproducible generator.
- Selected a clear transition window from 2026-06-15 after 13:00 UTC+8.
- Generated `window.csv`, `smoke_window.svg`, and `index.html`.
- Changed the plot from model mV features to dashboard display fields.
- Fixed a CSV parsing bug caused by empty inference columns before `cigarette_detected`; parser now locates `model_version` and reads sensor fields relative to that position.
- Made the label timeline thinner and the whole SVG more compact.
- Moved the legend to the top-right.
- Left-side series labels are right-aligned outside the plotting area so text does not enter the panels.
- X-axis tick labels use UTC+8 time-of-day format, including origin `14:34:40`.
- Red downward arrows mark the cigarette smoke boundary times only: `14:35:24` and `14:36:29`.

Important constraints:

- Do not commit or push these latest local chart/layout changes until the user explicitly says so.
- Do not include `.DS_Store` or `analysis/.DS_Store`.
- Dashboard VOC/CO display uses `voc_raw` and `co_raw`, not `voc_mv` / `co_mv`.
- Model feature columns use `voc_mv` / `co_mv`, but this chart intentionally follows dashboard display values.
- PM and climate fields should parse as `pm1_0`, `pm2_5`, `pm10`, `temperature`, `humidity`; if `pm1_0` is near 2890 or temperature is 2-96, the CSV columns are misaligned.

Local status at handoff:

- Latest generated SVG height is `790` for a compact layout.
- The bottom `time of day, UTC+8` axis caption was removed.
- The user is iterating visually; expect small layout/text refinements before commit.

Selected window:

```text
timestamp: 1781505280 ~ 1781505430
local time: 2026-06-15 14:34:40 ~ 14:37:10 UTC+8
```

Label runs:

| label | timestamp start | timestamp end | rows |
| --- | ---: | ---: | ---: |
| normal_air | 1781505280 | 1781505323 | 42 |
| cigarette_smoke | 1781505324 | 1781505388 | 62 |
| normal_air | 1781505389 | 1781505430 | 40 |

Dashboard values plotted:

- `voc_raw`
- `co_raw`
- `pm1_0`
- `pm2_5`
- `pm10`
- `temperature`
- `humidity`

Generated files:

- `window.csv`: extracted rows used for the plot
- `smoke_window.svg`: static chart
- `index.html`: browser-friendly wrapper for the chart

Shared analysis data:

- `../data/datapool.csv`: shared analysis data for teammates.
- It started as a copy of `data/datapool.csv`, then missing rows from the full SmokeLens log were appended.
- Merge identity used `node_id,timestamp,mode,model_version,voc_raw,co_raw,pm1_0,pm2_5,pm10,temperature,humidity` instead of `id`, because `datapool.csv` already had duplicate `id` values.
- The shared file lives under `analysis/` so teammates can use it for plotting even though root `data/*.csv` is ignored by `.gitignore`.

Regenerate with:

```sh
node analysis/cigarette-smoke-window/generate_plot.js
```
