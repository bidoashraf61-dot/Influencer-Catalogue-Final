"""One video on several platforms is ONE video (owner, 2026-10-27).

A creator's video shared on Instagram, TikTok, Facebook and so on is a "piece": its posts share content.piece (the
lowest post id) and count as one video everywhere. A post added from its link alone (the chat assistant, the paste box,
the bulk list) used to start a piece of its own, so the same video counted twice (Dr. Hossam Selim, 27 Oct: TikTok 525
and Instagram 526, posted a minute apart).

auto_piece joins a new post to the creator's same video on another platform when the evidence is plain: the same
creator and campaign, a different platform, posted within 12 hours, and exactly one such video that has no post on this
platform yet. Anything less plain (two candidate videos, no posted time) is left alone for a person to group.
"""

SAME_VIDEO_SECONDS = 12 * 3600


def auto_piece(conn, content_id):
    """Group this post with the creator's same video, if there is exactly one plain match. Returns the piece id or None."""
    p = conn.execute("SELECT campaign_id, code, platform, posted_at, piece FROM content WHERE id = ?", (content_id,)).fetchone()
    if p is None or p[4] or not p[3]:
        return None
    cid, code, platform, posted = p[0], p[1], p[2], p[3]
    near = conn.execute("SELECT id, piece FROM content WHERE campaign_id = ? AND code = ? AND id != ? AND hidden = 0 "
                        "AND section = 'campaign' AND platform != ? AND posted_at IS NOT NULL AND ABS(posted_at - ?) <= ?",
                        (cid, code, content_id, platform, posted, SAME_VIDEO_SECONDS)).fetchall()
    videos = {r[1] or r[0] for r in near}
    if len(videos) != 1:
        return None
    key = next(iter(videos))
    members = conn.execute("SELECT id, platform FROM content WHERE campaign_id = ? AND (id = ? OR piece = ?)",
                           (cid, key, key)).fetchall()
    if any(m[1] == platform for m in members):
        return None                      # that video already has a post on this platform: this one is another video
    ids = sorted({m[0] for m in members} | {content_id})
    conn.execute("UPDATE content SET piece = ? WHERE id IN (%s)" % ",".join("?" * len(ids)), [ids[0]] + ids)
    return ids[0]
