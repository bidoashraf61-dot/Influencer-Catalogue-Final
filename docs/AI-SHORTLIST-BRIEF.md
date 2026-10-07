# Brief: AI shortlist section on the catalogue

Stage 1 output of `/brainstorming`, 2026-10-08. Built with `/impeccable:impeccable` (hard rule).

```
=== BRIEF ===
PROJECT:   "Build a shortlist with AI": a section in the catalogue's controls band, beside the filters
USER:      Signed-in client (email account or access code); admin preview too
TAKEAWAY:  "I answered six taps and watched HelloVoice build my campaign list. It felt like progress, not a form."
LOOK:      Catalogue world (DESIGN.md): ink / lime / linen, Bebas + DM Sans, pills, pressed stamps
```

## Locked

1. **Placement:** an inline card in the controls section, beside the filter bar. It expands in place, with no popup.
2. **Journey (gamified):**
   - six steps (goal, platforms, audience country, product space, budget, creator count);
   - a step track that lights up as the client answers, with a "Brief 3 / 6" counter;
   - one question at a time as chips, and a Back button;
   - a review step styled as a brief ticket.
3. **Waiting:** an animated stage while the server works.
   - The HELV character searches through his camera (a Higgsfield loop on lime).
   - Shapes and platform marks orbit around him.
   - Named progress steps run: *Reading your brief → Scoring every creator (live counter) → Fitting the budget → Writing the reasons*.
   - A small celebration plays when the shortlist is ready.
4. **Result in the grid:**
   - the grid narrows to the picks, best first, each with a rank;
   - the picks are pre-ticked in the selection tray;
   - a result bar offers **Open as selection**, **Request a quote** and **Show all creators**.
5. **Scores per platform:** each pick shows one score per platform it is on (e.g. IG 87 · TT 64). The single portal "Fit" badge is hidden while the AI result is shown, so a card never carries two different numbers.
6. **Name from the brief:** e.g. "Skincare · KSA · Reach" instead of "AI shortlist" or "Voice shortlist".
7. **Honest cost label:** the Build button says what it costs for this viewer: free, or N credits for the AI reasons, or "Admin preview · free".

## Implementation notes

- **Client:** `assets/js/portal.js` and `assets/css/portal.css` (portal layer), mounted into `.cat-controls .cat-container` on the catalogue page only. The catalogue's own filter code is untouched. The grid is narrowed with CSS (`order` and a class), not by moving cards.
- **Server:** `/api/brief/run` adds `platform_scores` = `{code: {platform: score}}` for the picks, scored per platform with the same matcher.
- **Assets:** `assets/brand/voice/voice-scan.{webm,mp4}`, the searching loop.
- **Reduced motion:** no orbit, no loops. The steps still read in order.
