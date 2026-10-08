# Baymax — Community to a 30-Day Healthy Life Plan

**English** | [简体中文](README.zh-CN.md)

One Codex skill combines the health resource community, source-attributed plan modules, auditable nutrition planning, personal records, and phone calendar delivery. Choose entire modules or individual actions, adjust days and times, generate all 30 days, revise without losing actual records, and connect your existing calendar. No Microsoft or Google account is mandatory.

## Install

```sh
git clone https://github.com/chaojiwudibing/baymax.git ~/.codex/skills/baymax
cd ~/.codex/skills/baymax
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python community/server.py
```

On Windows use PowerShell, `$env:USERPROFILE\.codex\skills\baymax`, `py -m venv .venv`, and `.venv\Scripts\python`. Inspect existing installations first. Python 3.10+ is required; openpyxl provides Excel output and tzdata supplies IANA timezone data where needed.

Invoke `$baymax` in Codex and open [the local community](http://127.0.0.1:8848/). Use a private database path with `--database /PRIVATE/.baymax/community.sqlite3` for personal records. The browser cookie identifies a local session, not a hosted account; back up the SQLite file and exported plans/records before clearing browser data.

## A shared planning workflow

**Original source → attributed actions → personal selection → 30-day plan → calendar → actual records and revisions.**

The included community retains the resource directory, creator guides, discussions and topic paths, and adds a plan library and personal planner. The browser and CLI use the same Python composition engine. It rejects draft creator prescriptions, invalid schedules and unsupported timezones; duplicate goals and overlapping times remain visible as conflicts and cannot be exported to a calendar. Medical suitability and cumulative training load still require source and individual review.

The existing nutrition pipeline remains intact: evidence-backed food data → SQLite → ingredient calculations → readable 30-day Excel workbook. It preserves food provenance, unknown nutrients, weight bases, purchasing, storage, substitutions and actual records. Import a matching, fully checked nutrition audit into the life planner to add meal, shopping, preparation and review events. A habit template is not a complete meal plan. See [nutrition data](references/data-contract.md) and [source-to-plan rules](references/community-planning.md).

## Existing calendars, not a mandatory provider

- **CalDAV:** connect an existing compatible service or authorized self-hosted calendar. Once configured, saving a valid revision queues an automatic update. Stable UIDs and conditional writes prevent duplicates and protect remote manual edits; only tracked future events are removed.
- **ICS:** export all events with alarms for compatible calendar import. No account is needed for file generation. Import is a snapshot, not automatic synchronization; duplicate import behavior varies by client.
- **Subscription:** requires separately authorized HTTPS hosting and receiver support; refresh and notification behavior varies. This repository does not provision a subscription host.

[Device combinations and calendar setup](references/calendar-sync.md) cover all 15 nonempty combinations of Mac, Windows, iPhone and Android. Some Android devices need DAVx⁵ or a compatible calendar/import application. Phone-only users need an authorized external skill runtime to generate or revise plans; they can receive calendar files without running Codex locally. OAuth-only providers are not automatically supported by the included Basic/app-password CalDAV adapter. Microsoft To Do remains optional legacy functionality.

```sh
python scripts/life_plan.py --request /PRIVATE/request.json --out /PRIVATE/life-v1.json
python scripts/calendar_sync.py export --plan /PRIVATE/life-v1.json --out /PRIVATE/life-v1.ics
# After account setup and permission to upload selected event details:
python community/server.py --database /PRIVATE/community.sqlite3 --calendar-config /PRIVATE/caldav.json --calendar-state-dir /PRIVATE/calendar-state --allow-calendar-upload
```

## Content and acceptance status

The 2026-10-08 inventory tracks 1,359 repository sources and 10 creator videos. It includes 81 editorial tool-use workflows, 10 clearly labeled creator learning schedules, and 4 editorial life-organization templates. **1,278 repository candidates remain unreviewed; none of the 10 creator execution plans has a fully verified transcript.** Missing doses, repetitions and conditions are not invented. Reviewed content can be added with `scripts/import_plan_module.py`; source review is not clinical certification.

Composition, nutrition integration, local API isolation, calendar serialization, conditional CalDAV logic, revision/record preservation, and desktop/mobile-sized browser flows have automated checks. Actual cloud accounts, Windows execution and iOS/Android lock-screen notifications have not been accepted on real devices. This is a local community and installable skill, not a deployed multi-user service or native mobile app. See [verification](references/verification.md).

## Privacy and tests

Private health profiles, databases, workbooks, plans, credentials and sync state are excluded from the distribution. The server binds only to 127.0.0.1. Calendar uploads require the user's selected destination and authorization. Completion marks do not imply actual nutrient intake.

```sh
python -m unittest discover -s tests -v
python -m unittest discover -s community/tests -v
node community/tests/check_frontend.cjs
node community/tests/check_planner.cjs
node community/tests/check_browser.cjs
```

Browser tests require Playwright and Chrome (`PLAYWRIGHT_PATH`, `CHROME_PATH` overrides), use isolated data and generate ignored screenshots. Entry point: [SKILL.md](SKILL.md). The original concise skill/local-record workflow was inspired by [learn-by-building](https://github.com/chaojiwudibing/learn-by-building).
