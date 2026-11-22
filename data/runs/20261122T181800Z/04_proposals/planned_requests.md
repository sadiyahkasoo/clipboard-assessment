# Planned CRM requests (dry run - nothing has been sent)

29 proposals. Each request below is sent only after a reviewer approves it.

## 1. Move under Bellhaven: Bellhaven Meadows of Findlay

- Kind: Move under Bellhaven  |  Confidence: high
- Why: "Bellhaven Meadows of Findlay" is listed under no owner but is now a Bellhaven community. It has revenue history but nothing owed, so the existing account is moved under Bellhaven directly.

    PATCH /accounts/001UKEFGADQ8YCZ4YM
    {"parent_id": "0015QAPLGS3FVYEEEM"}

## 2. Update details: Bellhaven Rehabilitation & Nursing of Grove City

- Kind: Update details  |  Confidence: high
- Why: The CRM account matches this community but differs from the website: name "Bellhaven Rehab and Nursing of Grove City" -> "Bellhaven Rehabilitation & Nursing of Grove City".

    PATCH /accounts/001TZCSTBZFM6K5BGN
    {"name": "Bellhaven Rehabilitation & Nursing of Grove City"}

## 3. Update details: Bellhaven at Sycamore Ridge

- Kind: Update details  |  Confidence: high
- Why: The CRM account matches this community but differs from the website: name "Bellhaven of Sycamore Ridge" -> "Bellhaven at Sycamore Ridge".

    PATCH /accounts/00191H7JR16471SZ34
    {"name": "Bellhaven at Sycamore Ridge"}

## 4. Update details: The Arbors at Bellhaven - Dayton

- Kind: Update details  |  Confidence: high
- Why: The CRM account matches this community but differs from the website: name "Arbors at Bellhaven Dayton" -> "The Arbors at Bellhaven - Dayton".

    PATCH /accounts/0010KJFP601YNTZVDA
    {"name": "The Arbors at Bellhaven - Dayton"}

## 5. Update details: Bellhaven Healthcare Centre of Ashland

- Kind: Update details  |  Confidence: high
- Why: The CRM account matches this community but differs from the website: name "Bellhaven Health Care Center of Ashland" -> "Bellhaven Healthcare Centre of Ashland".

    PATCH /accounts/001RJ0D7Z5MAZN5HX5
    {"name": "Bellhaven Healthcare Centre of Ashland"}

## 6. Mark duplicate: Harborview Nursing & Rehab of Port Clinton

- Kind: Mark duplicate  |  Confidence: high
- Why: "Harborview Nursing & Rehab of Port Clinton" (Harborview Care Group (Parent Account)) is at the same address as "Bellhaven of Port Clinton" and is the same facility as Bellhaven of Port Clinton. Keep "Bellhaven of Port Clinton" because it is already under Bellhaven. Mark this copy Inactive and point it at the kept account.

    PATCH /accounts/001JD2MWRA74LTSN24
    {"status": "Inactive", "duplicate_of_account": "001UELXDAKFRKB8932", "note": "Duplicate of account 001UELXDAKFRKB8932 (Bellhaven of Port Clinton)."}

## 7. Mark duplicate: Harborview Shores of Erie

- Kind: Mark duplicate  |  Confidence: high
- Why: "Harborview Shores of Erie" (Harborview Care Group (Parent Account)) is at the same address as "Bellhaven Shores of Erie" and is the same facility as Bellhaven Shores of Erie. Keep "Bellhaven Shores of Erie" because it is already under Bellhaven. Mark this copy Inactive and point it at the kept account.

    PATCH /accounts/001BLYF02K97SZLZHH
    {"status": "Inactive", "duplicate_of_account": "001CVBBCSDM7YHN220", "note": "Duplicate of account 001CVBBCSDM7YHN220 (Bellhaven Shores of Erie)."}

## 8. Move under Bellhaven: Bellhaven of Kettering

- Kind: Move under Bellhaven  |  Confidence: medium
- Why: "Kettering Care Centre" is listed under Harborview Care Group (Parent Account) but is now a Bellhaven community. It has no revenue history, so the existing account is moved under Bellhaven directly. Also: name "Kettering Care Centre" -> "Bellhaven of Kettering".

    PATCH /accounts/001WR41PYNWXCAE2X4
    {"parent_id": "0015QAPLGS3FVYEEEM", "name": "Bellhaven of Kettering"}

## 9. Mark duplicate: Kettering Senior Campus

- Kind: Mark duplicate  |  Confidence: medium
- Why: "Kettering Senior Campus" (Cedar Trail Communities (Parent Account)) is at the same address as "Kettering Care Centre" and is the same facility as Bellhaven of Kettering. Keep "Kettering Care Centre" because no copy is under Bellhaven, so the tie-break rule chose it (billing history, then contacts, then having an owner, then score). Mark this copy Inactive and point it at the kept account.

    PATCH /accounts/001B7XZAA3AFALS9GP
    {"status": "Inactive", "duplicate_of_account": "001WR41PYNWXCAE2X4", "note": "Duplicate of account 001WR41PYNWXCAE2X4 (Bellhaven of Kettering)."}

## 10. Mark duplicate: Kettering Nursing & Rehabilitation

- Kind: Mark duplicate  |  Confidence: medium
- Why: "Kettering Nursing & Rehabilitation" (no owner) is at the same address as "Kettering Care Centre" and is the same facility as Bellhaven of Kettering. Keep "Kettering Care Centre" because no copy is under Bellhaven, so the tie-break rule chose it (billing history, then contacts, then having an owner, then score). Mark this copy Inactive and point it at the kept account.

    PATCH /accounts/0016KTS1UAWBRXS09J
    {"status": "Inactive", "duplicate_of_account": "001WR41PYNWXCAE2X4", "note": "Duplicate of account 001WR41PYNWXCAE2X4 (Bellhaven of Kettering)."}

## 11. Mark duplicate: Monroe Gardens Care Center

- Kind: Mark duplicate  |  Confidence: high
- Why: "Monroe Gardens Care Center" (Harborview Care Group (Parent Account)) is at the same address as "Bellhaven Gardens of Monroe" and is the same facility as Bellhaven Gardens of Monroe. Keep "Bellhaven Gardens of Monroe" because it is already under Bellhaven. Mark this copy Inactive and point it at the kept account.

    PATCH /accounts/00159PL81N38KM4FHM
    {"status": "Inactive", "duplicate_of_account": "001U1750VLVJAGG1S5", "note": "Duplicate of account 001U1750VLVJAGG1S5 (Bellhaven Gardens of Monroe)."}

## 12. Mark duplicate: Cedar Trail of Monroe

- Kind: Mark duplicate  |  Confidence: high
- Why: "Cedar Trail of Monroe" (Cedar Trail Communities (Parent Account)) is at the same address as "Bellhaven Gardens of Monroe" and is the same facility as Bellhaven Gardens of Monroe. Keep "Bellhaven Gardens of Monroe" because it is already under Bellhaven. Mark this copy Inactive and point it at the kept account.

    PATCH /accounts/0011AB44D05WLA9HTX
    {"status": "Inactive", "duplicate_of_account": "001U1750VLVJAGG1S5", "note": "Duplicate of account 001U1750VLVJAGG1S5 (Bellhaven Gardens of Monroe)."}

## 13. Change of ownership: Bellhaven of Tiffin

- Kind: Change of ownership (billing rule)  |  Confidence: high
- Why: "Bellhaven of Tiffin" is listed under Cedar Trail Communities (Parent Account) but is now a Bellhaven community. It has revenue history (84,000) and money still owed (12,400), so the old account is left untouched. A new account is created under Bellhaven and the old one is pointed at it.

    POST /accounts
    {"name": "Bellhaven of Tiffin", "parent_id": "0015QAPLGS3FVYEEEM", "billing_street": "45 St Lawrence Dr", "billing_city": "Tiffin", "billing_state": "OH", "billing_zip": "44883", "care_type": "Skilled Nursing", "status": "Active", "phone": "(260) 589-2589", "note": "Created by Bellhaven ownership sync. Change of ownership from account 001U6RW32TY0WSXZZB (Cedar Trail Communities (Parent Account)), which is preserved for billing."}

    PATCH /accounts/001U6RW32TY0WSXZZB
    {"chow_current_account": "{{new_account}}"}

## 14. Change of ownership: Bellhaven of Marietta

- Kind: Change of ownership (billing rule)  |  Confidence: high
- Why: "Bellhaven of Marietta" is listed under Cedar Trail Communities (Parent Account) but is now a Bellhaven community. It has revenue history (51,250) and money still owed (3,800), so the old account is left untouched. A new account is created under Bellhaven and the old one is pointed at it.

    POST /accounts
    {"name": "Bellhaven of Marietta", "parent_id": "0015QAPLGS3FVYEEEM", "billing_street": "805 Colegate Dr", "billing_city": "Marietta", "billing_state": "OH", "billing_zip": "45750", "care_type": "Skilled Nursing", "status": "Active", "phone": "(614) 337-1967", "note": "Created by Bellhaven ownership sync. Change of ownership from account 001A34WFSUYHCRBLFT (Cedar Trail Communities (Parent Account)), which is preserved for billing."}

    PATCH /accounts/001A34WFSUYHCRBLFT
    {"chow_current_account": "{{new_account}}"}

## 15. Move under Bellhaven: Bellhaven Crossings of Lima

- Kind: Move under Bellhaven  |  Confidence: high
- Why: "Bellhaven Crossings of Lima" is listed under Harborview Care Group (Parent Account) but is now a Bellhaven community. It has revenue history but nothing owed, so the existing account is moved under Bellhaven directly.

    PATCH /accounts/001LGFPBJY4N9MB6KL
    {"parent_id": "0015QAPLGS3FVYEEEM"}

## 16. Move under Bellhaven: Bellhaven of Zanesville

- Kind: Move under Bellhaven  |  Confidence: medium
- Why: "Cedar Trail of Zanesville" is listed under Cedar Trail Communities (Parent Account) but is now a Bellhaven community. It has no revenue history, so the existing account is moved under Bellhaven directly. Also: name "Cedar Trail of Zanesville" -> "Bellhaven of Zanesville".

    PATCH /accounts/001H1JMVZWP46D5VUF
    {"parent_id": "0015QAPLGS3FVYEEEM", "name": "Bellhaven of Zanesville"}

## 17. Update details: Bellhaven of Chagrin Falls

- Kind: Update details  |  Confidence: medium
- Why: The CRM account matches this community but differs from the website: name "Riverbend Manor Care Center" -> "Bellhaven of Chagrin Falls".

    PATCH /accounts/001RJU1X4NBWC1Q0G7
    {"name": "Bellhaven of Chagrin Falls"}

## 18. Update details: Bellhaven Willow Creek

- Kind: Update details  |  Confidence: medium
- Why: The CRM account matches this community but differs from the website: name "Sunny Acres Retirement Home" -> "Bellhaven Willow Creek".

    PATCH /accounts/0017MN2JYAJBDS8WQZ
    {"name": "Bellhaven Willow Creek"}

## 19. Address differs: Bellhaven of Ashtabula

- Kind: Address differs  |  Confidence: low
- Why: The CRM account matches this community but differs from the website: street "PO Box 517" -> "3156 W Prospect Rd". The CRM holds a PO Box, which can be a valid billing address; consider rejecting if billing mail goes there.

    PATCH /accounts/001NXP9X46CWEPSLSV
    {"billing_street": "3156 W Prospect Rd"}

## 20. Mark duplicate: Bellhaven of Owosso

- Kind: Mark duplicate  |  Confidence: high
- Why: "Bellhaven of Owosso" (Bellhaven Senior Living (Parent Account)) is at the same address as "Bellhaven of Owosso" and is the same facility as Bellhaven of Owosso. Keep "Bellhaven of Owosso" because it is already under Bellhaven. Mark this copy Inactive and point it at the kept account.

    PATCH /accounts/001QU150PM4Z15UA71
    {"status": "Inactive", "duplicate_of_account": "001EGU7BMJ942ZTRE6", "note": "Duplicate of account 001EGU7BMJ942ZTRE6 (Bellhaven of Owosso)."}

## 21. Update details: Bellhaven of Portsmouth

- Kind: Update details  |  Confidence: high
- Why: The CRM account matches this community but differs from the website: zip "45626" -> "45662".

    PATCH /accounts/001CF3LDWVRGL09P4F
    {"billing_zip": "45662"}

## 22. Create account: Bellhaven of Batavia

- Kind: Create new account  |  Confidence: high
- Why: Bellhaven of Batavia (Batavia, OH) is on the website but has no CRM account. Create one under Bellhaven.

    POST /accounts
    {"name": "Bellhaven of Batavia", "parent_id": "0015QAPLGS3FVYEEEM", "billing_street": "2000 Hospital Dr", "billing_city": "Batavia", "billing_state": "OH", "billing_zip": "45103", "care_type": "Skilled Nursing", "status": "Active", "phone": "(231) 698-3092", "note": "Created by Bellhaven ownership sync from website listing https://analyst-assessment-production.up.railway.app/communities/bellhaven-of-batavia."}

## 23. Create account: Bellhaven at Union Square

- Kind: Create new account  |  Confidence: medium
- Why: Bellhaven at Union Square (New Albany, OH) is on the website but has no CRM account. Create one under Bellhaven. Lookalikes left alone: "Union Square Senior Living" (New Albany, score 38).

    POST /accounts
    {"name": "Bellhaven at Union Square", "parent_id": "0015QAPLGS3FVYEEEM", "billing_street": "118 Union Square Dr", "billing_city": "New Albany", "billing_state": "OH", "billing_zip": "43054", "care_type": "Assisted Living", "status": "Active", "phone": "(330) 519-9639", "note": "Created by Bellhaven ownership sync from website listing https://analyst-assessment-production.up.railway.app/communities/bellhaven-at-union-square."}

## 24. Create account: Bellhaven of Carlisle

- Kind: Create new account  |  Confidence: high
- Why: Bellhaven of Carlisle (Carlisle, PA) is on the website but has no CRM account. Create one under Bellhaven.

    POST /accounts
    {"name": "Bellhaven of Carlisle", "parent_id": "0015QAPLGS3FVYEEEM", "billing_street": "640 Walnut Bottom Rd", "billing_city": "Carlisle", "billing_state": "PA", "billing_zip": "17015", "care_type": "Skilled Nursing", "status": "Active", "phone": "(260) 386-7765", "note": "Created by Bellhaven ownership sync from website listing https://analyst-assessment-production.up.railway.app/communities/bellhaven-of-carlisle."}

## 25. Create account: Amberly Manor

- Kind: Create new account  |  Confidence: high
- Why: Amberly Manor (Hudson, OH) is on the website but has no CRM account. Create one under Bellhaven.

    POST /accounts
    {"name": "Amberly Manor", "parent_id": "0015QAPLGS3FVYEEEM", "billing_street": "4390 Darrow Rd", "billing_city": "Hudson", "billing_state": "OH", "billing_zip": "44236", "care_type": "Assisted Living", "status": "Active", "phone": "(330) 228-4392", "note": "Created by Bellhaven ownership sync from website listing https://analyst-assessment-production.up.railway.app/communities/amberly-manor."}

## 26. Update details: Bellhaven of Chesterton

- Kind: Update details  |  Confidence: high
- Why: The CRM account matches this community but differs from the website: name "Chesterton Senior Commons" -> "Bellhaven of Chesterton".

    PATCH /accounts/0013NUZQHQUEZ8DXEG
    {"name": "Bellhaven of Chesterton"}

## 27. No longer on website: Bellhaven Care Center of Alliance

- Kind: No longer on website  |  Confidence: medium
- Why: "Bellhaven Care Center of Alliance" sits under Bellhaven in the CRM but is not on the Bellhaven website, and no other owner's account exists at its address. We cannot tell whether it was sold or closed, so flag it for a person to confirm rather than guess.

    PATCH /accounts/00116ETS45BL7DTQP7
    {"status": "Needs Review", "note": "No longer listed on the Bellhaven website (found by the daily ownership sync). Ownership needs confirming: may have been sold or closed."}

## 28. No longer on website: Bellhaven of Coldwater

- Kind: No longer on website  |  Confidence: medium
- Why: "Bellhaven of Coldwater" sits under Bellhaven in the CRM but is not on the Bellhaven website, and no other owner's account exists at its address. We cannot tell whether it was sold or closed, so flag it for a person to confirm rather than guess.

    PATCH /accounts/0016PVXH4B25HWR7QE
    {"status": "Needs Review", "note": "No longer listed on the Bellhaven website (found by the daily ownership sync). Ownership needs confirming: may have been sold or closed."}

## 29. Sold to another owner: Bellhaven of Sandusky

- Kind: Sold to another owner  |  Confidence: medium
- Why: "Bellhaven of Sandusky" is under Bellhaven but no longer on the Bellhaven website. "Millstone Care of Sandusky" under Millstone Health Partners (Parent Account) is at the same address, so the facility appears to have changed hands. This account has revenue history (130,000) and money still owed (5,200), so it is left as it is and pointed at the new owner's account.

    PATCH /accounts/001SXSF4ELF0Z2LGDM
    {"chow_current_account": "0017JP8Z1UQ763BVK3"}
