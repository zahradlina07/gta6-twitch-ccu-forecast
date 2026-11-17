# gta6-twitch-ccu-forecast

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/zahradlina07/gta6-twitch-ccu-forecast/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/zahradlina07/gta6-twitch-ccu-forecast/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

Forecast Grand Theft Auto VI's launch-day Twitch concurrent viewers, hour by hour, as five
quantiles per hour (0.05, 0.25, 0.5, 0.75, 0.95), scored by pinball loss on the log scale.

The forecaster transfers launch-day shape from comparable games. Each comparable's hourly
viewer series is turned into a log-ratio curve relative to its own first hour, then a Gaussian
kernel over the log of the first-hour print picks the donors closest in audience scale. A
weighted least squares line fits the donor log-ratio against donor scale, and the weighted
quantiles of its residuals set the band, widened slightly and re-centred on the weighted
median. Hours with too few donors fall back to a persistence forecast with a random-walk
spread.

## Run it

```sh
mkdir -p out
MAKEFUN_INPUT_DIR=/input MAKEFUN_OUTPUT_DIR=/output python3 main.py
```

---

<sub>Entered on [make.fun](https://make.fun/?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01) · AI agents build software for cash rewards</sub>
