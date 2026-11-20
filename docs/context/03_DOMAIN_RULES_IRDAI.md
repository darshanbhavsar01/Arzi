# Domain rules: Indian health-insurance claims (for the rules engine and appeals)

> Status key: ✅ verified against a regulator document or several consistent sources · ⚠️ verify the primary text before citing on stage or in a letter. Arzi is **decision support**. A human signs every appeal. Always prefer the **specific policy wording** when it's more favourable to the insured.

## 1. Glossary
- **Cashless claim:** the hospital's TPA/insurance desk sends a pre-authorisation request to the insurer or TPA and the insurer pays the hospital directly. **Reimbursement claim:** the family pays and claims afterwards.
- **TPA:** Third-Party Administrator that processes claims for insurers. **HMIS:** hospital management software. **NHCX:** National Health Claims Exchange (FHIR-based standard claim exchange).
- **Repudiation:** outright rejection. **Disallowance/deduction:** partial cut "as per terms and conditions".
- **Sum insured (SI), co-pay, deductible, sub-limit, room-rent cap, PED** (pre-existing disease), **moratorium**.
- **GRO:** insurer's Grievance Redressal Officer. **Bima Bharosa:** IRDAI's grievance portal (formerly IGMS). **Insurance Ombudsman (Bima Lokpal):** free quasi-judicial forum.

## 2. Key regulations
| Ref | What it says (paraphrased) | Status |
|---|---|---|
| **IRDAI Master Circular on Health Insurance Products, IRDAI/HLT/CIR/PRO/84/5/2024, 29 May 2024** | Consolidates and repeals 55 earlier circulars. Sets policyholder-friendly norms including cashless timelines. | ✅ |
| Cashless timelines (Master Circular 2024) | Insurer decides on cashless pre-authorisation **within 1 hour** and final discharge authorisation **within 3 hours** of the hospital's request | ⚠️ widely reported; confirm the para number |
| **IRDAI/HLT/REG/CIR/151/06/2020 (11 Jun 2020), norms on proportionate deductions** | Proportionate deduction may apply only to defined **"associated medical expenses"** when a higher room category is chosen. **Excluded** from associated expenses: (a) **pharmacy and consumables**, (b) **implants and medical devices**, (c) **diagnostics**. Insurers may not recover proportionate deductions on anything other than defined associated expenses. **No proportionate deduction on ICU charges.** | ✅ (circular text) |
| Proportionate deduction under the 2024 Master Circular | Some secondary sources claim the 2024 circular limits proportionate deduction to the room-rent line only | ⚠️ unverified, so **don't** encode it. Use the 2020 rule. |
| PED definition and waiting (effective 1 Apr 2024) | PED look-back is 36 months (was 48). **Maximum PED waiting period is 36 months.** **Specific waiting periods are capped at 36 months.** | ✅ (multiple consistent sources) |
| **Moratorium** (effective 1 Apr 2024) | After **60 months** of continuous cover (was 96), the insurer cannot contest a claim or policy for non-disclosure or misrepresentation **except proven fraud** | ✅ |
| **IRDAI non-payable items: Annexure I (standardisation guidelines; carried into the Master Circular)** | **List I:** items not payable unless the insurer offers an optional cover (e.g., baby food, beauty services, laundry, cold/hot pack, crepe bandage, service charges where nursing is also charged). **List II:** items **subsumed into room charges**. **List III:** items **subsumed into procedure charges**. **List IV:** items **subsumed into the cost of treatment** (e.g., admission/registration charges). Lists II–IV shouldn't be deducted as separate "non-payables" because they're part of the room, procedure or treatment cost. | ✅ structure; ⚠️ load the full item list from the official PDF into `irdai_non_payable.json` |
| Insurer grievance timeline | The insurer should resolve a grievance within **about 14–15 days** | ⚠️ sources say 14 or 15; use "within 15 days" and verify |
| **Insurance Ombudsman Rules, 2017** (as amended) | Complain only after a written complaint to the insurer is rejected, gets an unsatisfactory reply, or gets **no reply within 1 month**. File **within 1 year** of the rejection or of that month ending. Claim value **up to ₹50 lakh** (raised from ₹30 lakh). Free. The award binds the insurer. | ✅ |
| Bima Bharosa | Open to all, no claim-amount limit. Forwards the complaint to the insurer and tracks it. | ✅ |

**Escalation ladder:** Hospital/TPA query → **Insurer GRO** (written complaint) → **Bima Bharosa** (IRDAI) → **Insurance Ombudsman** (≤ ₹50 lakh, within 1 year) → Consumer Commission.

## 3. Top deduction and rejection patterns (what Arzi checks)
1. **Proportionate room-rent deduction:** the patient stayed in a room above the cap, so associated expenses are cut by the ratio. *Common errors:* applying the ratio to pharmacy, diagnostics, implants or ICU.
2. **Non-payable consumables:** gloves, masks, admission kits, attendant charges and so on. *Common errors:* deducting List II/III/IV items separately; ignoring a non-payable add-on the policy includes.
3. **Sub-limits:** cataract, knee replacement or specific procedures capped per policy.
4. **Co-pay and deductibles:** age-based or zone-based co-pay; check which base it applies to.
5. **Waiting periods:** initial 30 days (typical, per policy), PED (max 36 months), specific diseases (max 36 months). *Common errors:* rejection after the waiting period has finished; non-disclosure rejection after 60 months.
6. **Documentation queries:** a missing discharge summary, investigation reports or implant invoice or sticker.

## 4. Data sources to load
- Official IRDAI non-payable items list (Annexure I, Lists I–IV), from irdai.gov.in or an insurer's annexure PDF
- Master Circular on Health Insurance Products, 29 May 2024 (irdai.gov.in)
- Circular IRDAI/HLT/REG/CIR/151/06/2020 (proportionate deductions)
- 2–3 public retail policy wordings (room-rent cap, co-pay, sub-limits, waiting-period clauses)
- Insurance Ombudsman office contacts (cioins.co.in) and the complaint format
