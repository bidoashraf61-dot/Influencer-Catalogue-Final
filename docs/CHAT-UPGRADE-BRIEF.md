# HELV Assistant chat upgrade: brief (locked 2026-10-08)

This is the catalogue's chat panel (`mountVoice()` in `assets/js/portal.js`, the "voice" styles in `assets/css/portal.css`, and `/api/chat` in `admin/portal_api.py`).

It is built on branch `chat-upgrade`. **Do not deploy until Bido says the other session's chat work is finished.**

## Multiple-choice questions
- **Layout:** the options appear inside the assistant's message as a grid of cards. A small "Question 2 of 5" line and a Back link sit with them.
- **Tapping fills the message box; it does not send.** Tapping an option adds its label to the box. Tapping it again removes it. The client can pick several options (e.g. 1 and 4), type their own words alongside, and then press Send.
- **No Next button.**
- **Skip** stays as a small link on optional questions.
- **Menus are different.** Menu actions ("Find creators", "Get a quote", …) are not questions, so they still run on tap.

## Speed
- **Streaming:** the answer streams in word by word (`/api/chat/stream`), so the first words show in about a second.
- **Visible progress:** live steps show while the assistant works (e.g. "Searching 2,100 creators…", "Checking engagement…").
- **Instant answers:** common questions are answered at once from stored answers, with no AI call and no credit. These cover:
  - prices and tiers (read live from the tier table);
  - how it works and how to book;
  - credits;
  - contact;
  - analyses;
  - campaign reports.
- **Lighter model for chat:** typed chat uses a lighter, faster model (`chat_model` setting). Shortlists keep the stronger model.

## Creator results
- **Swipeable cards:** photo cards in a horizontal row, each showing the match score, tier, followers and city.
- **Card actions:** tap to open the profile; "+ Add" collects creators in the chat.
- **Saving:** a "Save N as a selection" button saves the collected creators.

## Extras
- **Suggested next steps:** 2–3 follow-up buttons after each answer, e.g. "Cheaper options", "Only Riyadh", "Save all as a selection".
- **Bigger window:** taller on desktop, with an expand-to-large toggle. Full screen on phones.
- **Remember the conversation:** the chat carries across pages and visits for 7 days, in this browser and per account.
- **Voice input:** a mic button using the browser's speech recognition (Arabic or English). The transcript lands in the box to check before sending. It is hidden where the browser doesn't support it.

## Constraints
- Same world as today: the HELV Assistant character and the catalogue theme (DESIGN.md).
- Tapping stays free; typed questions cost 1 credit, except instant answers, which are free.
- Writes happen only on the client's button press.
- Respect reduced motion.
- Keyboard and screen-reader friendly (`role="log"`, live region).
