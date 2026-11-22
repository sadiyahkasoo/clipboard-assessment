# Step: the daily schedule

**Status: live since 22 November 2026.** The entry is installed on this computer and runs every day at 07:00.

How it was proven: the scheduled command was first run by hand, then a one-off test entry was set two minutes ahead. It fired by itself at 20:18 (run 3 in `logs/daily.log`) and found nothing new to suggest. The test entry was then removed, leaving only the 07:00 entry.

## What runs each day

Once a day the computer runs the daily job by itself:

1. reads the website,
2. reads the CRM,
3. matches and classifies,
4. adds any **new** suggestions to the review queue.

It only reads. It can never change the CRM. New suggestions simply wait in the review app until a person approves or rejects them. Anything already decided is not raised again.

## The schedule entry

The entry is kept in `schedule/crontab.txt`:

    0 7 * * * cd /Users/ismail/_devsrc/gen_code/clipboard-assessment && PYTHONPATH=src .venv/bin/python -m bellhaven_sync.pipeline --mode live >> logs/cron.log 2>&1

In words: every day at 07:00, go to the project folder and run the daily job against the real CRM, saving anything it prints to `logs/cron.log`.

## Switching it on

    crontab schedule/crontab.txt

Check it is installed:

    crontab -l

Switch it off again:

    crontab -r

(This computer had no scheduled entries before, so these commands do not disturb anything else. If other entries are added later, edit with `crontab -e` instead of replacing the whole list.)

## How to see that it ran

- `logs/daily.log` gets one line per run, for example:

      2026-11-21T20:46:19Z mode=live run=1 status=ok communities=35 accounts=121 proposals_found=29 new=29 already_decided=0 withdrawn=0

- Each run also leaves a dated folder under `data/runs/` with the full trace.
- The Audit trail page in the review app lists every run.

## Limits worth knowing

- **The Mac must be awake at 07:00.** A sleeping laptop skips that day's run; the next run catches up, because each run compares the whole website with the whole CRM.
- **macOS may ask for permission** the first time a scheduled job touches the project folder.
- **In a real team setting** this would run on a server or a hosted scheduler rather than a laptop, with the audit database kept somewhere shared. The job itself would not change.

## Safety on a bad day

- If the website is down or suddenly lists far fewer communities, the run stops and records "aborted" instead of proposing anything.
- If the CRM cannot be reached, the run records an error line in the log and exits. Nothing is half-written, because the job never writes to the CRM.
