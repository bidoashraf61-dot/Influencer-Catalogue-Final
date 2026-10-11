# Creator score (scoring v4, 2026-10-11)

Four parameters, all read from the posts we hold, scaled between two editable points and
weighted by the campaign objective. Source of truth: `admin/score_model.py`; formula:
`fit.score_core` in `admin/fit.py`. Editable in Admin > Settings > "Creator score model".

| Parameter | Read as | Scores 0 at | Scores 100 at |
|---|---|--:|--:|
| Engagement | median (likes + comments) / followers; per view on video platforms | 0.3% (feed) / 1.5% (video) | 3.5% / 7.0% |
| View rate | median views / followers | 3% | 50% |
| Interest | posts naming the brief's space / posts available (the posts are the 100%) | 0 posts | all posts |
| Consistency | std / mean of views over the posts (lower is steadier) | 2.0 | 0.5 |

Feed = Instagram, Facebook, X (per follower). Video = TikTok, YouTube, Snapchat (per view).
Linear between the two points. Consistency needs 10 or more posts.

## Weights by campaign objective (shares, normalised over what is available)

| Objective | Engagement | View rate | Interest | Consistency |
|---|--:|--:|--:|--:|
| Awareness | 20 | 45 | 20 | 15 |
| Engagement | 45 | 15 | 25 | 15 |
| Traffic | 30 | 25 | 30 | 15 |
| Balanced / several goals | the average of the goals chosen | | | |

A parameter with no data hands its weight to the others. Interest only exists when the brief
names a category. Interest read from profile tags only (no post data) counts at 30%.

## Bands

80+ Strong fit, 60-79 Good fit, 40-59 Possible fit, under 40 Not recommended.
`score_range` carries the interest range (hashtag overlap makes the matched posts a range).

## Checks beside the score (never inside it)

Audience country/gender/age, fake followers, our own campaign record, reach, posts analysed.
"Limited data" shows under 10 posts. The international benchmark is a reference line beside
engagement in the hover (`admin/intl_benchmarks.py`); it does not move the number.
