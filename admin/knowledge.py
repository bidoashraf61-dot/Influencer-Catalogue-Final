"""What the HELV Assistant knows about HelloVoice and the portal, beyond the live
data its tools read. Written from the portal itself and HelloVoice's answers
(2026-10-08). Facts here are stable policy and how-to; anything numeric about
creators, prices, selections or campaigns always comes from the tools.

Admins can add notes in Client portal → Settings (kb_text); they are appended.
"""

KNOWLEDGE = """
ABOUT HELLOVOICE
- HelloVoice is BlueHolding's film and media production house in Al-Olaya, Riyadh, working mainly with healthcare and pharma brands, plus FMCG, retail and tech.
- Services: (1) video production (brand, launch, patient-awareness and documentary films); (2) influencer campaigns end to end: casting, brief and script, production, compliance, tracking and reporting; (3) technology activations (mixed reality, VR, hologram, interactive screens, projection).
- Influencer markets: Saudi Arabia, UAE and Egypt.
- Contact: info@hellovoice.co.uk, +966 11 463 4518. Replies within one working day. NDA on request.

HOW A CAMPAIGN RUNS
- Steps: shortlist creators → request a quote → the account manager confirms creators, deliverables, dates and price → contract or PO → brief and script → production → compliance check → posting → tracking and report.
- Timeline: usually 2–3 weeks from an approved quote until the content is live.
- Revisions, content usage rights (including paid/ads use), payment terms and cancellation are agreed per campaign in the quote and contract. The account manager confirms them; never promise specific terms.

CREATORS AND VETTING
- Every creator in the catalogue is reviewed by the HelloVoice team for content quality and brand safety, and their follower numbers are checked against the live platform.
- Many creators have a full analysis (audience countries, gender and ages, engagement, average views, fake followers); others show public numbers only. Clients can press "Request full analysis" on a creator's page and the team adds it.
- Advertising licences are shown as "Verified ✓" stamps when checked: the Saudi Mawthooq licence and the UAE licence. The catalogue can be filtered by licence.
- Healthcare professionals (HCP) are a separate group of creators (doctors, pharmacists and similar), with their own tiers.

PRICES
- Catalogue prices are ranges per video, in SAR before 15% VAT, set by the creator's size tier; a creator's own rate can differ. Bundles are priced together. The final price is in the quote.
- A selection can be shown in other currencies (e.g. AED, USD); the amounts are converted at HelloVoice's set rates.

USING THE PORTAL
- Catalogue: browse vetted creators, filter by platform, size, city or country, topic and licence, and open any creator's analysis in a side panel.
- Shortlisting: tick creators and save them as a selection. A selection has its own link and is opened with its access code; colleagues on the same account share selections and campaigns.
- "Build a shortlist with AI": six quick questions (goal, platforms, audience, product space, budget, number of creators) produce a scored shortlist saved as a selection. The Campaign Power meter (out of 1000) shows how complete the brief is.
- Match score: each creator is scored out of 100 against the brief's goal and audience, from their analysis (engagement, views, audience in the target country, reach). Parts are marked as estimated when a creator has no full analysis yet. Labels run from "Strong fit" to "Not recommended".
- Selection page: the client's price per creator and the total range, tags and segments, the brief and the scores; "Score this selection" answers the brief questions for a selection that has none; "Request a quote" sends it to the account manager.
- Campaign report: shown for live campaigns. Lists every post with views, reach and engagement, progress against the goals, and an overall verdict (e.g. on track or behind target). Numbers refresh once every 24 hours. Figures marked as estimates are replaced by the creators' real insights once approved. There is also a one-screen dashboard view and a CSV download.

ACCOUNT AND CREDITS
- Clients sign in with their access code (or their work email where enabled). Each shared link asks for its own access code once per browser.
- In this chat, tapping options is free; a typed question uses 1 credit, building a scored shortlist uses 5, and common questions answered instantly are free. More credits can be requested from the account.

WHAT THE ASSISTANT CANNOT DO
- It cannot book creators, promise availability or dates, negotiate prices or discounts, or share anything about other clients. For these, offer to pass the request to the account manager.
""".strip()
