# Demonstration script (about 15 minutes)

Prepare: start MySQL, the fraud service, Django and the frontend (see README), then run
`python manage.py seed_demo --reset`. Keep the Django terminal visible: verification and reset emails print there.
Use a separate browser profile or incognito window per role so the sessions don't collide.

All demo accounts use the password **`Demo@1234`**.

| Role | Email | What's waiting |
|---|---|---|
| Customer | `customer@claims.local` (Rohan Mehta) | 4 vehicles, a Partially Claimed policy, a fresh claim, a rejected claim he can appeal, a pending policy request |
| Customer | `meera.joshi@example.com` | A rejected claim with a pending appeal |
| Claim Adjuster | `adjuster@claims.local` (Priya Sharma) | Queue with new, documents-pending, under-review and appeal items |
| Claim Adjuster | `adjuster2@claims.local` | Second adjuster (shows the assignment lock) |
| SIU Investigator | `siu@claims.local` (Vikram Rao) | One open high-risk investigation (CLM-2026-000008, score 72) |
| Administrator | `admin@claims.local` (Anita Desai) | Analytics, a pending policy request, reports, audit log |

## 1. Onboarding and security (3 min)
1. **Register** a new customer. Point out the live password-rule checklist, then try a weak password: the server rejects it as well.
2. Try to **sign in** before verifying: it's refused. Copy the verification link from the Django terminal, open it, then sign in.
3. *(Optional)* Sign in with a wrong password 4 times to show the 20-minute lock. Unlock from Admin › Staff accounts or Customers.

## 2. Vehicle and policy (2 min)
4. Add a vehicle, then try the same registration number again: the server returns "already registered".
5. Request a policy and note the estimated premium.
6. As **admin**, open Policy requests › Approve › Issue policy.
7. Back as the customer: the policy is **Active**, and the vehicle shows "Details locked after policy association".

## 3. Claim submission (3 min)
8. Submit a claim → choose the policy → enter incident details. Use today's date and an earlier time, because the policy starts today.
9. On the documents step, press Continue with nothing uploaded: the mandatory-document check blocks you. Upload KYC, address proof, RC and a photo.
10. Submit. Show the **30-minute countdown** and edit the amount. Mention that Django checks the window, not the browser.
11. Optional: upload a `.jpg` that is really a PDF. It is rejected by the content check.

## 4. Adjuster review (3 min)
12. As **adjuster**, open the claim. Show the **fraud score** and the explained contributing factors.
13. **Start review**. Refresh the customer tab: the Edit button is gone.
14. Reject one document with a reason. As the customer, see the notification and **Replace** it.
15. As the adjuster, upload a repair estimate, verify all documents, then **Approve** a smaller amount than requested.
16. As the customer, both amounts are shown. The policy is now **Partially Claimed** and the notification arrived.

## 5. Fraud review and SIU (2 min)
17. As **SIU**, open the investigation queue → CLM-2026-000008 (score 72, a 9-day-old policy, a 2 am fire on a 12-year-old car). Take the investigation, record findings and a recommendation, then complete it.
18. As the **adjuster**, the claim is back in Under Review with the SIU findings, and the decision is still the adjuster's. A high score never auto-rejects.
19. Sign in as **Neha** (`neha.kapoor@example.com`) to show that the customer only ever saw "Under Review": no score and no reasons.

## 6. Appeals (1 min)
20. As **adjuster**, open Appeals → Meera's claim → Decide: accept to reopen it, or decline with "no further appeal" to make the rejection permanent.

## 7. Administration (2 min)
21. **Analytics**: every number is a live database query. Refresh after an approval to see it change.
22. **Reports**: filter (for example Claim type = Fire, or Risk = High), then export CSV, Excel and PDF. The files contain the filtered rows.
23. **Audit log**: filter `CLAIM_APPROVED` to see who approved what, when and from which IP.
24. Show that the admin **cannot approve claims**: the claim page is read-only, and the API returns 403.

## Talking points
- Fraud detection is a separate Flask service with a swappable engine (`docs/ENGINEERING.md`).
- Approval is one database transaction: claim, policy totals, history, audit and notification succeed or fail together.
- 104 backend tests run on MySQL, plus the Flask tests, a browser end-to-end test and a load check.
- Stop the fraud service, submit a claim (it still succeeds), and show the "assessment failed — re-run" warning. Restart the service and re-run.
