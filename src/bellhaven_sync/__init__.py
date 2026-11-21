"""
Bellhaven ownership sync.

Keeps the CRM's facility-to-parent-company links in step with the list of
communities on the Bellhaven Senior Living website:

    backup    -> save a full copy of the CRM before anything else
    scraper   -> read every community from the website
    matcher   -> score each community against CRM accounts
    classify  -> turn matches into proposed changes
    audit_db  -> remember proposals, reviews and CRM changes (SQLite)
    apply     -> send an approved change to the CRM and verify it
    pipeline  -> the daily job that ties the read-only steps together
    review_app-> the local web app where a person approves or rejects
"""
