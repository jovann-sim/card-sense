# Your clone needs a reset — read before you push

On 17 August the history of this repository was rewritten to strip a trailer
from every commit message. The change was cosmetic, but rewriting history gives
every commit a new SHA, so **the copy on your machine no longer matches the one
on GitHub** even though the files are identical.

Nothing of yours was lost. All thirteen of your commits are present in the new
history, contents unchanged — only their hashes and the trailer differ.

## Why this matters before you do anything else

If you `git push` from your current clone, git will treat the old commits as
new work and push them back, restoring the history that was just removed. If
you `git pull`, you will get a merge of two histories that contain the same
changes twice.

So: reset before you push or pull.

## The reset

**1. Check whether you have work that has not reached GitHub.**

```bash
git status --short && git stash list
```

Anything listed is uncommitted or stashed and is *not* affected by the reset —
but note it down, and commit or stash it before continuing.

**2. Keep a backup branch. This costs nothing and makes every later step safe.**

```bash
git branch backup-$(date +%Y%m%d) && git branch --list 'backup-*'
```

Your entire current history now lives on that branch. If anything below goes
wrong, nothing is gone.

**3. Fetch the rewritten history.**

```bash
git fetch --all --prune
```

**4. Reset each branch you use to match GitHub.**

```bash
git checkout main && git reset --hard origin/main
```

`main` now carries everything: your work, Han's work, and fourteen commits
adding the forecast horizons, bill routing, welcome-bonus tracking, the full
card simulation, the browser extension and the Cloud Run deploy setup.

If you have other local branches, delete and recreate them from the remote —
they carry old hashes too:

```bash
git branch -D feat/adk 2>/dev/null; git checkout -b feat/adk origin/feat/adk
```

**5. Confirm it worked.**

```bash
git log --oneline -3 && git status -sb
```

You should see `## main...origin/main` with no ahead/behind counts.

## If you had commits that were never pushed

They are on the backup branch from step 2. Find them and replay them onto the
new history:

```bash
git log --oneline backup-$(date +%Y%m%d) --not origin/main --author="$(git config user.email)"
```

That lists your commits which are not in the new history. Some will be
duplicates whose contents already arrived by another route — check the subjects
before replaying. For each one you genuinely still need:

```bash
git cherry-pick <sha>
```

Cherry-picking applies the change onto the new history and gives it a fresh
hash, which is exactly what you want.

## Starting over instead

If your clone has nothing unpushed and you would rather not think about it:

```bash
cd .. && mv card-up card-up-old && git clone https://github.com/jovann-sim/card-up.git
```

Then copy your `backend/.env` across — it is untracked, so a fresh clone will
not have it, and the backend refuses to start without it.

## One new requirement

The backend now refuses to start in real mode unless `INTERNAL_RUN_SECRET` is
set to something other than the placeholder. It gates the endpoints that wipe
and reseed the account, which are now reachable on a deployed instance. Add a
value to `backend/.env`:

```bash
cd backend && printf '\nINTERNAL_RUN_SECRET=%s\n' "$(openssl rand -hex 32)" >> .env
```

Any random value works for local development; it does not need to match anyone
else's.

## Sorry about the disruption

Rewriting shared history is disruptive by nature, and this was avoidable — the
trailer is also preserved in pull requests #1 to #5, which a rewrite cannot
reach, so the rewrite did not fully achieve what it set out to do. It will not
be repeated.
