# Creator score (scoring v3, 2026-10-11)

A creator's score compares their **engagement** with **international benchmarks**. It never
compares them with our own roster. Source of truth: `admin/intl_benchmarks.py`; formula:
`fit.score_core` in `admin/fit.py`.

```
ratio = creator's engagement / benchmark for their platform and size band
score = 100 x min(1, ratio / 2)
```

| ratio | score | tag |
|---|---|---|
| 0.8x or less | 40 or less | Not recommended (below 40) |
| 1.0x (at benchmark) | 50 | Possible fit |
| 1.2x | 60 | Good fit |
| 1.6x | 80 | Strong fit |
| 2x or more | 100 | Strong fit |

## Benchmarks: a range, low to middle source (version 2026-10-11.2)

 = the lowest source's typical value for the band;  = the middle source's. A creator
is scored against both ends: the score shown is the midpoint and  / 
carry the ends (a creator can read "Possible fit to Strong fit").

| Band (followers) | Instagram: (likes+comments) / followers | TikTok: interactions / views |
|---|--:|--:|
| Nano under 20K | 1.0 - 3.75% | 3.4 - 3.8% |
| Micro 20K-100K | 0.8 - 2.75% | 3.4 - 3.6% |
| Mid 100K-500K | 0.9 - 2.25% | 3.4 - 3.7% |
| Macro 500K-1M | 0.9 - 1.5% | 3.4 - 3.7% |
| Mega 1M+ | 0.7 - 1.5% | 3.4% (one source) |

Instagram: low = IQFluence (Sep 2026, 30.1M creators), high = HypeAuditor (2025, the middle of
IQFluence / HypeAuditor / Buffer). TikTok: low = Rival IQ (2025, median brand by view), high =
the average of Rival IQ and Socialinsider (2025, 2M videos) because only two sources exist.

Editable in Admin > Settings > "Creator score benchmarks (international)"; saved as the
 setting, {platform: {band: [low, high]}}; cached 60 s. A figure equal to the
table's default is not stored.

## Not scored

* YouTube, Snapchat, Facebook, X: no agreed benchmark, shown as "not scored".
* Views, consistency, interest: no international benchmark, not in the number.
* Audience country/gender/age, fake followers, our own campaign record: shown as checks beside
  the score, never inside it.
* The objective (Awareness / Engagement / Traffic) does not change the number.

Override a figure without a deploy: Settings key `intl_benchmarks`, e.g.
`{"Instagram": {"mid": 1.1}}`. Cached for 60 seconds.
