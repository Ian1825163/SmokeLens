# Cigarette Smoke Window Plot

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

- `voc_mv`
- `co_mv`
- `pm1_0`
- `pm2_5`
- `pm10`
- `temperature`
- `humidity`

Generated files:

- `window.csv`: extracted rows used for the plot
- `smoke_window.svg`: static chart
- `index.html`: browser-friendly wrapper for the chart

Regenerate with:

```sh
node analysis/cigarette-smoke-window/generate_plot.js
```
