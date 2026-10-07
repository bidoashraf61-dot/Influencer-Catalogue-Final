# Brief: "Voice", the catalogue chat bot

Stage 1 output of `/brainstorming`, 2026-10-08. Design and build run through `/impeccable:impeccable` (hard rule).

```
=== BRIEF ===
PROJECT:     "Voice": animated chat bot for the influencer catalogue (influencer-catalogue.hellovoice.co.uk)
SURFACES:    Catalogue roster (/), selection pages (/selection/), creator passport (/creator/)
USER:        Every signed-in viewer: email accounts and access-code guests
CHARACTER:   HelloVoice mascot (User Assets/Char PNG copy.tiff): red speech-bubble head, maroon beanie,
             black sunglasses, maroon fleece jacket, white hoodie with lime cords, camera in hand
PERSONA:     Name "Voice". Friendly pro: short, warm, confident; one emoji max per message.
             English UI; replies in the client's language (Arabic when they write Arabic).
TAKEAWAY:    "I told Voice what I need and it got it done: creators found, shortlist saved, quote on its way."
LOOK:        HelloVoice catalogue theme (DESIGN.md: ink / lime / linen, Bebas + DM Sans, pill controls)
```

## Locked decisions

1. **Launcher.** The character sits in a round button at the bottom-right.
   - It is animated in code from a still cut-out: idle bob, an occasional head tilt and wave, and a speech
     bubble ("Need a hand?") that pops out once per visit after a short delay.
   - On click it bounces and the chat panel springs open from the corner. Clicking again closes it.
   - Unread-dot when Voice has said something while closed.
   - Reduced motion: everything static.
2. **Auto-greeting on open.** Voice types (typing dots) then greets by first name when known:
   "Hi Sara 👋 I'm Voice from HelloVoice. What can I help you with today?", followed by quick-reply chips.
3. **Guided questions first (free), AI after (credits).** The chips route into short tap-to-answer flows.
   Free text at any point goes to the AI assistant, which uses the existing Gemini setup, credits and monthly
   budget. Credits are refunded on failure.
4. **Tasks Voice can carry out:**
   - **Build & save a shortlist.** Uses the existing brief questions and the scorer, and saves a real selection
     with a link to open it.
   - **Drive the catalogue.** "Show me micro mums in Riyadh" applies the filters on the page behind the chat, live.
   - **Edit my selection.** Add or remove creators, rename it, compare two creators.
   - **Quote & human handoff.** Request a quote, request a creator's full analysis, or "talk to my account
     manager". These are sent to the KAM and the team list with the chat transcript attached.
5. **Existing buttons stay.** "Find creators" and "Ask" stay as they are; Voice is an extra entry point that
   shares the same back end, so a shortlist built in either place is the same selection.

## Quick replies on the greeting (assumed copy, correct me)

- Find creators for a campaign
- Show creators on the page
- Work on my selection
- Get a quote
- Talk to my account manager
- Just browsing

## Assumptions (correct if wrong)

- **Back-to-top button:** moves up to stack above the launcher, so the bottom-right corner holds one control.
  The selection tray already lifts that button.
- **Chat history:** kept per account (the existing chat store), so Voice remembers the last conversation.
  "New chat" clears it.
- **Panel size:** 380×600 on desktop; full-screen sheet on phones.
- **Character asset:** cut from the 94 MB TIFF into WebP. That gives a head-and-shoulders avatar (launcher and
  message avatar) and a waist-up figure for the panel header, plus 2x versions. The TIFF itself never ships.
- **Gated pages:** no bot on the gate (before sign-in), on the admin, or in print.
- **Safety:** client tools stay read-only on data except the four tasks above. Selection edits only touch the
  client's own selections. Quote and handoff use the existing request and notify paths.

## Out of scope

Main website (hellovoice.co.uk), video-loop animation of the character, voice input, booking a call.

=== WORKFLOW PLAN ===
TASK TYPE:   Product UI feature (launcher + chat panel) with new assistant tools
ROUTE:       brainstorming (done) → asset cut (character WebP) → impeccable build → impeccable inspect → deploy (on your go)
SKILLS IN:   impeccable:impeccable — launcher, motion, panel, messages, chips, mobile sheet
SKILLS OUT:  film-workflow, lira-image-prompts, motion-design — the still is cut out and animated in code, not generated
NEXT STEP:   /impeccable:impeccable
