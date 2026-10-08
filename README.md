# Job Search Kit

Give Codex a process for finding work that fits your life, then help it research and apply accurately under permissions you choose.

This is a local instruction kit, not a hosted service or an unattended application bot. It includes an interview method, several search methods, application guardrails, private tracking, and offline validation. It has no employer integrations and sends nothing itself.

## Start

Open this repository as your Codex workspace and say:

> Help me start my job search. Read AGENTS.md. First understand what I want and what experience I can substantiate. Use only sources I permit, and keep applications and outreach in preparation mode until I authorize specific actions.

Codex should read the job-search-guide skill and start a conversation. You do not need a finished brief, a particular career direction, or a specific resume format.

Python 3.10+ is needed only for the optional local helpers:

```sh
python3 tools/search_state.py init
python3 tools/search_state.py validate
python3 tools/search_state.py summary
python3 -m unittest discover -s tests -v
python3 tools/check_public.py
```

`init` creates `private/search.json` and `private/current.md`; it refuses to overwrite an existing workspace. All candidate documents, source exports, receipts, addresses and application drafts belong inside `private/`, which Git ignores. Ignoring files does not encrypt them or protect them from another application or a forced Git add.

## The process

1. Recover experience and preferences from sources you select. Ask about consequential gaps rather than making you repeat known facts.
2. Define the kind of working week and life you want, separating requirements, preferences, possibilities and unknowns.
3. Research contrasting real arrangements. Refine the brief from your reactions without replacing it with your newest example.
4. Search across roles, employers, places, schedules and entry routes. Keep the full relevant field alongside recommendations and show coverage gaps.
5. Verify promising opportunities, compare their practical economics, and prepare truthful materials.
6. Apply using your chosen permissions. Record actual confirmations, preserve blocked drafts, and handle replies and offers as separate steps.

Read [the interview method](docs/intake.md), [search methods](docs/discovery.md), [application workflow](docs/applications.md), and [replies and offers](docs/continuity.md) as needed. [The data contract](docs/data.md) explains the private tracker. [Acceptance scenarios](docs/acceptance.md) define what still needs behavioral testing.

## Capabilities and permissions

Codex needs authorized web access for current opportunity verification and computer use for operating application forms. Tool availability varies. It should inventory the tools it actually has, load their instructions, and report a missing capability rather than claim a form was operated. Without computer use, it can still research and prepare a manual application packet.

Research, form entry, uploads, submission, email applications, recruiter follow-ups, account creation, references, consents and offer acceptance are distinct actions. You can authorize an exact application or a clearly bounded batch. Permission persists within that scope until revoked or expired; Codex should not ask again for every routine click. New commitments or missing personal answers still require your input.

The permission ledger is an instruction and audit record. The checker does not enforce browser permissions, authenticate your approval, prove that a receipt is genuine, or establish that a website complies with its terms. Available technical controls must be evaluated separately.

## Sharing the repo

The shipped files contain generic methods and fictional examples. Never commit your private workspace. Run the public checker and review every staged file before publishing. The checker is a limited heuristic, not proof of de-identification. Do not import confidential employer material or someone else's private history to improve the kit.

No license has been chosen. Before public release, the maintainer should choose a license, perform an independent behavioral pilot, and review the publishing diff. No automatic schedules, browser settings, or global Codex configuration are installed.
