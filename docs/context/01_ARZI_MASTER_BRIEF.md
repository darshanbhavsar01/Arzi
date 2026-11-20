# Arzi: master brief

*Context pack for the Claude Project. Last updated 20 Nov 2026 (City Buildathon, Day 1).*

---

## 1. The event: Startup Buildathon India 2026

| Item | Detail |
|---|---|
| Organisers | Hack2skill, with support from nasscom and HeadStart. Technology partners: **Google DeepMind and Google Cloud**. |
| Website | https://startupbuildathon.com/ · T&Cs: hack2skill.com/event/buildathon/tnc |
| Support | support+Buildathon-GDMxGCS@hack2skill.com |
| Applications | 23 Oct – 15 Nov 2026 (idea, solution, architecture, pitch deck). **Done: Arzi was shortlisted.** |
| **City Buildathon** | **20–21 Nov 2026**, 2 days, in 10 cities (Ahmedabad, Bengaluru, Chennai, Delhi, Hyderabad, Jaipur, Kochi, Kolkata, Mumbai, Pune). My city: `[fill in]` |
| Regional showcases | 23 Nov Gurugram · 25 Nov Mumbai · 27 Nov Hyderabad |
| Grand Finale | 2 Dec 2026 at Google Bengaluru. Top 10 winners announced. |
| Prize | Top 10 teams each get USD 10k (USD 5k cash plus USD 5k in Google AI/Cloud credits), access to Google experts, VC and mentor feedback, and eligibility for Google startup programmes. |
| Eligibility | Early-stage startups or aspiring founders. Solo founders allowed. **The product must be AI-powered.** |

### City Buildathon format
- **Day 1, ideate and design:** kick-off and rules, hands-on time with Google AI tools, problem selection, mentor rounds.
- **Day 2, build and showcase:** build, **submit**, **present to the jury** (technical and non-technical jurors), shortlist announcement.
- Expected deliverable: a **working AI product built at the event**, ideally showing **initial customer validation or traction**.

### Judging criteria (optimise for every one)
1. **Founder profile**: why me
2. **Product potential**
3. **Market viability**: a buyer, a price, a channel
4. **Technical architecture**: it has to be able to scale
5. **Use of Google AI**: how deeply Google AI and Google Cloud power the product

### Google stack named by the organisers
- Models: Gemini, Gemini Omni, Nano Banana, Gemini Live, Lyria, Gemma
- Tools: Google AI Studio, Google Antigravity, Google Agent Skills
- Deployment: Google Cloud

---

## 2. Founder
- **Darshan Bhavsar**, solo founder (team name: Arzi, team size 1).
- Cloud and AI/MLOps engineer with about 5 years' experience; AI/MLOps Engineer at Intuitive.AI on enterprise client engagements. Works across GCP, AWS and Azure, with depth in document intelligence, agentic AI (Google ADK), AI pipelines, compliance and security reviews, and FinOps/AI observability.
- Community credibility: gave a Google ADK session at GDG Gandhinagar Build with AI, guest lectures on AI/ML at Charusat University, and has judged hackathons several times.
- **Gap to close:** healthcare domain knowledge. *Action:* name a hospital TPA-desk manager or a doctor as an advisor, and add a personal or family claim story if there is one.
- Placeholders for the pitch: `[personal/family claim story]` · `[advisor name + role]`

---

## 3. Name and brand
- The product name is **Arzi** (अर्ज़ी / અરજી, "petition" or "application"). It replaced the working name *ClaimShield*, which sounded too generic for an AI product.
- The logo is a document with a red approved-check badge and the wordmark "arzi".
- Colours: navy `#1E2A44` (primary/text), red-orange `#D9482B` (accent/CTA/alerts), cream `#F7F2E8` (background), slate `#CDD3E0` (lines/muted).
- Tagline: *"Your claim, defended before and after the insurer says no."*

---

## 4. Problem (as in the submitted deck)
- **₹29,933 crore** of health claims were cut in FY2024-25: **₹11,412 Cr repudiated** (rejected outright) and **₹18,521 Cr disallowed** (deducted "as per terms and conditions", 13.98% of the amount claimed).
- Most cuts are **mechanical policy rules**: proportionate room-rent deductions, non-payable consumables, sub-limits, co-pays and waiting periods.
- Hospital TPA desks race IRDAI's **1-hour cashless pre-authorisation** and **3-hour discharge** timelines (Master Circular on Health Insurance, 29 May 2024), each insurer and TPA has a different workflow, and nobody checks the bill against the specific policy before it goes out. One HMIS vendor says a 200-bed hospital runs **4–9 parallel workflows, one per major TPA**.
- Families get short-paid and give up. Hospitals absorb the disputes, write-offs and slower discharges.
- **37,431** health complaints went to the Insurance Ombudsman in FY25, up from 34,203. About **41%** of decided health complaints went in the **policyholder's favour**, so pushing back often works.
- Bima Bharosa logged 1,17,979 health-insurance grievances in FY26 (Lok Sabha reply, 27 Jul 2026). IRDAI issued show-cause notices to eight major health insurers over delays, wrongful rejections and "unwarranted deductions".
- The Ministry of Finance told Parliament that partial disallowance happens when room-rent or proportionate limits are exceeded, sub-limits, co-pays or deductibles apply, or non-medical expenses are included. **These are all rules a machine can check.**

**Named user:** *the billing executive at a 150-bed private hospital at 6 pm on discharge day, and the family at the counter waiting to hear how much they'll pay out of pocket.*

### Stat hygiene (read before quoting on stage)
- The ₹11,412 Cr and ₹18,521 Cr figures come from **secondary reporting** of the IRDAI Annual Report 2024-25. Check Table I.29 of the primary report if possible. One outlet uses ₹18,521 Cr for a different FY24 aggregate.
- Don't say "₹30,000 Cr rejected". Only ₹11,412 Cr was rejected outright; the rest was deducted. Say **"rejected or deducted"**.
- FY24 Ombudsman counts differ by source (31,490 vs 34,203).
- Don't use the claims that NHCX authorises "in under 60 seconds" or covers "12,606 hospitals"; neither is verified. The last official figure is about 300 hospitals ramping up (Jul 2024).
- The Accel "70% were wrappers" quote and the vertical-AI funding drop (87%, $319M to $41M, Tracxn via Elets CIO) came from snippets. Verify them before quoting.

---

## 5. Solution
Arzi sits **between the hospital, the family and the insurer** and does three jobs:

1. **Audit before submission** (hospital TPA desk): upload the policy, discharge summary and itemised bill as a scan, photo or PDF. Arzi flags every likely deduction with the **₹ at risk** and the **exact policy clause or IRDAI rule**, and tells the desk **what to fix before filing**.
2. **Appeal after a cut** (hospitals and families): Arzi reads the insurer's deduction or rejection letter and drafts a **clause-cited appeal** to the insurer's GRO, to **Bima Bharosa** or to the **Insurance Ombudsman**. **A human reviews and signs every appeal.**
3. **Explain to the family** in their language: a **voice explanation in Gujarati, Hindi or English** (Gemini Live) covering what was cut, why, and the next step. A free **"check my rejection"** tool brings families in.

**Differentiators:** it works *before* submission, not only after; every flag and appeal cites a clause; it's independent of the HMIS, the TPA and the insurer; and it serves the hospital and the family on one claim record.

---

## 6. Market and business model (hypotheses to validate)
- **3.26 crore** health claims paid in India in FY25 · about **40,000** cashless network hospitals, who are the buyers.
- An illustrative ₹100 per audited claim across all claims comes to **about ₹326 Cr a year** in audit fees alone, before appeals.
- **Hospitals (SaaS):** ₹15–40k per hospital per month, or a per-claim audit fee for small hospitals. Primary ICP: mid-size private hospitals with **50–300 beds**.
- **Land with proof:** a free retrospective audit of past deductions shows how much is recoverable.
- **Families:** a free "check my rejection" tool, plus a **10–15% success fee** only on money recovered.
- **Go-to-market:** founder-led pilots in **5–10 Gujarat hospitals** (Ahmedabad, Surat, Rajkot). The Ahmedabad Ombudsman office alone saw 3,540 health complaints in FY25, 82% of its caseload. After that, HMIS and NHCX integrator partners, and later UAE and Saudi Arabia.
- Investor climate: vertical-AI funding in India has fallen because pilots didn't convert to paying customers, so **show the buyer, the price and the first 10 customers**.

## 7. Competition
| Player | What they do | Arzi's edge |
|---|---|---|
| ClaimBuddy | Claim support for hospitals and patients (250+ hospitals) | Policy-wording-aware pre-submission audit with clause citations |
| fairClaims (Policygaido) | AI help to contest rejections, consumer only | Arzi covers the hospital side too, and works before submission |
| Insurance Samadhan | Human-led complaint resolution | Software economics, instant, at scale |
| Chikitsa ClaimIQ, ClaimBook | Claims modules inside hospital software, post-hoc reconciliation | Independent of the HMIS; works for any hospital and any family |

**Positioning line:** *Arzi audits before submission and appeals after. Every flag cites a clause, it's independent, and it serves the hospital and the family on one claim record.*

## 8. Key risks and mitigations
| Risk | Mitigation |
|---|---|
| Hospitals are slow buyers | Free retrospective deduction-recovery audit; per-claim pricing for small hospitals |
| Insurer pushback and medico-legal liability | Decision support only; a human signs every appeal; citations only |
| Patient health data under DPDP | Gemma/SDP redaction before reasoning, Mumbai-region storage, consent and audit log, per-hospital isolation |
| Uneven NHCX adoption | Document upload works today; NHCX (FHIR) is a later channel |
| LLM hallucinating rules or amounts | Deterministic rules engine for ₹; RAG grounding; evaluation set; "unverified" labels |

## 9. Why this idea (from my earlier research)
Arzi (as ClaimShield) scored **24/25** on the judging rubric across six candidate ideas. The alternates were CBAM Passport 21, Saathi 21, DPDP Autopilot 20, Section 16 19 and NoticeDesk 18. It fits YC's Winter 2027 "$15-an-Hour Expert" request, which names insurance claims and medical billing, and its "Own Your Intelligence" and "Air-Gapped" themes (Gemma inside the hospital's cloud). It also matches Accel's "Services-as-Software" and vertical-AI theses. The research rule for passing rounds: **one named user, one painful workflow, a rupee-quantified problem, a paying buyer, and load-bearing Google AI. No chatbot wrappers and no overscoping.**

## 10. Open to-dos (non-code)
- [ ] Fill in the city, personal claim story and advisor name
- [ ] **Traction on Day 1:** call 3–5 hospital billing/TPA-desk people or families and collect quotes. Aim for one LOI or a "yes, pilot with us" WhatsApp message.
- [ ] Collect public policy wordings for 2–3 popular retail health policies, plus the IRDAI non-payable items list (PDF)
- [ ] Prepare 3 anonymised or synthetic demo cases (see file 02)
