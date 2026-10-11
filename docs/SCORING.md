# Creator score (scoring v3, ranges, 2026-10-11)

A creator's score compares their **engagement** with **international benchmarks**. It never
compares them with our own roster. Source of truth: `admin/intl_benchmarks.py`; formula:
`fit.score_core` in `admin/fit.py`.

```
ratio = creator's engagement / benchmark for their platform and size band
score = 100 x min(1, ratio / 2)
```

A benchmark is a range (low to high), so the score is worked out at both ends and kept as a
range: the number shown is the midpoint, and `score_range` / `tag_range` carry the ends (a
creator can read "Possible fit to Strong fit").

| ratio (at the midpoint) | score | tag |
|---|---|---|
| 0.8x or less | 40 or less | Not recommended (below 40) |
| 1.0x (at benchmark) | 50 | Possible fit |
| 1.2x | 60 | Good fit |
| 1.6x | 80 | Strong fit |
| 2x or more | 100 | Strong fit |

## Benchmarks: low = lowest source, high = middle source (version 2026-10-11.2)

| Band (followers) | Instagram: (likes+comments) / followers | TikTok: interactions / views |
|---|--:|--:|
| Nano under 20K | 1.0 - 3.75% | 3.4 - 3.8% |
| Micro 20K-100K | 0.8 - 2.75% | 3.4 - 3.6% |
| Mid 100K-500K | 0.9 - 2.25% | 3.4 - 3.7% |
| Macro 500K-1M | 0.9 - 1.5% | 3.4 - 3.7% |
| Mega 1M+ | 0.7 - 1.5% | 3.4% (one source) |

Instagram: low = IQFluence (Sep 2026, 30.1M creators, median by tier); high = HypeAuditor
(2025, the middle of IQFluence / HypeAuditor / Buffer). TikTok: low = Rival IQ (2025, median
brand account by view); high = the average of Rival IQ and Socialinsider (2025, 2M videos),
because only two sources exist. TikTok engagement here is (likes + comments + shares) / views;
the benchmark also counts saves, which the scrape does not return, so our figure is slightly
conservative.

Editable in Admin > Settings > "Creator score benchmarks (international)"; saved as the
`intl_benchmarks` setting, {platform: {band: [low, high]}}; cached 60 s. A figure equal to the
table's default is not stored.

## Not scored

* YouTube, Snapchat, Facebook, X: no agreed benchmark, shown as "not scored".
* Views, consistency, interest: no international benchmark, not in the number.
* Audience country/gender/age, fake followers, our own campaign record: shown as checks beside
  the score, never inside it.
* The objective (Awareness / Engagement / Traffic) does not change the number.
* The shortlist's country and product-space markdowns (`matcher.apply_rules`) still apply
  after scoring and scale the range with the number.

## Interest: the posts we hold are the 100%

When the brief names a category, interest = posts naming it / posts analysed (5 of 12 = 42
points, 12 of 12 = 100). It enters at weight 0.5 against engagement's 1.0. Without post data
the roster tags give a keyword estimate at weight 0.15. No threshold of posts is needed.
