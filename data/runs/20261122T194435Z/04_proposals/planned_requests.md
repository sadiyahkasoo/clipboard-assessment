# Planned CRM requests (dry run - nothing has been sent)

1 proposals. Each request below is sent only after a reviewer approves it.

## 1. Address differs: Bellhaven of Ashtabula

- Kind: Address differs  |  Confidence: low
- Why: The CRM account matches this community but differs from the website: street "PO Box 517" -> "3156 W Prospect Rd". The CRM holds a PO Box, which can be a valid billing address; consider rejecting if billing mail goes there.

    PATCH /accounts/001NXP9X46CWEPSLSV
    {"billing_street": "3156 W Prospect Rd"}
