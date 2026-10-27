"""Instagram / Facebook overlap in a campaign's views (owner, 2026-10-27)."""


def overlap_views(raw_metrics, facebook_views):
    """Plays of an Instagram reel that are also its Facebook copy's plays (owner, 2026-10-27). Instagram's app shows
    the two together; the Facebook copy is tracked as its own post, so a campaign total that adds both counts those
    plays twice. raw_metrics is the `metrics` block of data-slayer/instagram-post-details; facebook_views the latest
    views of the same creator's Facebook posts in the campaign. The overlap is the reel's fb_play_count, and only when
    a tracked Facebook post is within 5% of it: a Facebook copy we do not track is not counted anywhere else."""
    fb = (raw_metrics or {}).get("fb_play_count")
    if not isinstance(fb, (int, float)) or fb <= 0:
        return 0
    for v in facebook_views:
        if v and abs(v - fb) <= 0.05 * fb:
            return int(fb)
    return 0
