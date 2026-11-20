# Submitted idea deck (Round 1, shortlisted): extracted text

*Source: Arzi_Idea_Submission_1.pptx (8 slides; slide 8 is a closing image). Text is verbatim; the layout and diagrams aren't. The structured architecture is in file 02.*

<!-- Slide number: 1 -->

Team Name: Arzi
Team Size: 1  (Solo founder: Darshan Bhavsar)
Problem Statement: Indian health insurers rejected or deducted ₹29,933 crore of claims in FY2024-25, mostly through mechanical policy rules nobody checks before filing. Arzi audits every claim before submission and drafts clause-cited appeals after a cut.

<!-- Slide number: 2 -->

Problem StatementThe challenge or problem identified by the team.
₹29,933 Cr
of health claims rejected (₹11,412 Cr) or deducted (₹18,521 Cr) by insurers in FY25
Why the money is lost
Most cuts are mechanical policy rules: proportionate room-rent deductions, non-payable consumables, sub-limits, co-pays and waiting periods.
Hospital TPA desks are racing the clock: IRDAI's 1-hour pre-authorisation and 3-hour discharge rules, with a different workflow for every insurer and TPA. No one checks the bill against the specific policy before it goes out.
Families are short-paid and give up: they don't know why money was cut or how to appeal. Hospitals absorb the disputes, write-offs and slower discharges.
37,431
health insurance complaints to the Insurance Ombudsman in FY25, up from 34,203 a year earlier
41%
of decided Ombudsman health complaints went in the policyholder's favour, yet most families never appeal
Our user
The billing executive at a 150-bed private hospital at 6 pm on discharge day, and the family waiting at the counter to learn how much they have to pay out of pocket.
Sources: IRDAI Annual Report 2024-25 (as reported by Business Standard); Council for Insurance Ombudsmen data via Cafemutual; IRDAI Master Circular on Health Insurance Business, 2024.

<!-- Slide number: 3 -->

Proposed SolutionThe idea and how it addresses the identified problem.
Arzi is an AI claims auditor and appeals agent that sits between the hospital, the family and the insurer.

Audit before submission
For the hospital TPA desk
Appeal after a cut
For hospitals and families
Explain to the family
In their language
1
2
3
Upload policy, discharge summary and itemised bill (scan, photo or PDF)
Flags every likely deduction with the amount at risk and the exact policy clause or IRDAI rule
Tells the desk what to fix before filing
Reads the insurer's deduction or rejection letter
Drafts a clause-cited appeal to the insurer, Bima Bharosa or the Ombudsman
A human reviews and signs every appeal
Voice explanation in Gujarati, Hindi or English
What was cut, why, and the next step
Free “check my rejection” tool brings families in
Works before submission, not only after
Every flag and appeal cites a clause
Independent of HMIS, TPA and insurer

<!-- Slide number: 4 -->

Solution ArchitectureArchitecture of the proposed solution
1 · Capture
Hospital desk & families
2 · Protect
Before data moves
3 · Reason
Google ADK agents on Vertex AI Agent Engine
4 · Deliver
Outputs & insight
Powered by
Web app for TPA desk
Gemma on Cloud Run
Extractor
Cloud Run API + web dashboard
Gemini on Vertex AI: read, reason, draft
Policy Interpreter
Family upload via web / WhatsApp
Sensitive Data Protection
Firestore claim records
Document AI: OCR for poor scans
Bill Auditor
Bills, policies, discharge notes, insurer letters
Redacts patient identifiers
Gemini Live voice for families
Vertex AI Search: policy wordings & IRDAI circulars
Appeal Drafter
Cloud Storage (Mumbai) + Pub/Sub
Consent & audit log (DPDP)
BigQuery + Looker Studio analytics
Rules engine (Cloud Run): exact ₹ maths
Voice Explainer
Security & operations  Identity Platform, IAM and VPC Service Controls isolate each hospital · Cloud Logging, Trace and Vertex AI evaluation track accuracy and cost per claim · Terraform for repeatable onboarding · Fully serverless: scales per claim with near-zero idle cost · Next: claims in via NHCX (FHIR) APIs

<!-- Slide number: 5 -->

Google AI ToolsGoogle AI Studio, Google Antigravity and Google Agent Skills (used or planned to be used).
Google AI Studio
Prototype & evaluate  ·  planned
Prototype and test the extraction and audit prompts on anonymised bills, policies and rejection letters, tune the structured-output schemas, and build the first evaluation set before writing production code.
Google Antigravity
Build  ·  planned
Agent-first IDE to build the ADK agents, the deduction rules engine, the Cloud Run services and their tests quickly, so a solo founder can ship a working product in the two-day buildathon.
Google Agent Skills
Domain know-how  ·  planned
Package Arzi's claims expertise as reusable skills the agents load on demand: IRDAI non-payable items check, proportionate room-rent deduction calculator, sub-limit and co-pay checks, and appeal formats for insurer, Bima Bharosa and Ombudsman.
Build flow:  prototype in AI Studio  →  build in Antigravity  →  reuse checks as Agent Skills  →  deploy on Google Cloud

<!-- Slide number: 6 -->

Google AI ModelsGoogle AI model(s) used or planned for the proposed solution.

Gemini
via Gemini API on Vertex AI

Gemini Live
real-time voice

Gemma
open model, inside the hospital's cloud
Reads scanned bills, handwritten discharge summaries, policy PDFs and rejection letters into structured data
Maps each bill line to the exact clause and IRDAI rule, grounded in retrieved text
Drafts clause-cited appeals and powers the ADK agents
Explains to families what was cut, why, and what to do next
Gujarati, Hindi and English
Reaches people who will never read a policy document
Runs on Cloud Run in the hospital's own Google Cloud project
Redacts patient identifiers and classifies documents before the main pipeline
Keeps sensitive health data under the hospital's control
Supporting Google Cloud AI services
Vertex AI (model serving and evaluation)  ·  Vertex AI Agent Engine + Google ADK (agent runtime)  ·  Document AI (OCR for poor scans)  ·  Vertex AI Search (grounding on policy wordings and IRDAI circulars)

<!-- Slide number: 7 -->

Market, Business Model & CompetitionWho pays, how we reach them, and why Arzi is different.
3.26 Cr
health insurance claims paid in India in FY25
~40,000
cashless network hospitals: our buyers
₹326 Cr / yr
audit fees alone at an illustrative ₹100 per claim
Business model & go-to-market
Competition
Hospitals (SaaS): ₹15–40k per hospital per month, or a per-claim audit fee for small hospitals
Land with proof: free retrospective audit of past deductions shows recoverable value
Families: free “check my rejection” tool; 10–15% success fee only on money recovered
Go-to-market: founder-led pilots in 5–10 Gujarat hospitals (Ahmedabad, Surat, Rajkot), then HMIS and NHCX integrator partners; later UAE and Saudi Arabia
ClaimBuddy  Claim support for hospitals and patients (250+ hospitals)
fairClaims (Policygaido)  AI help to contest rejections, consumer only
Insurance Samadhan  Human-led complaint resolution
Chikitsa ClaimIQ, ClaimBook  Claims modules inside hospital software
Arzi  audits before submission and appeals after; every flag cites a clause; independent; serves hospital and family on one claim record
Sources: IRDAI / General Insurance Council data as reported in the press; competitor descriptions from company and press material. Pricing and market-size figures are hypotheses to validate in pilots.

<!-- Slide number: 8 -->

