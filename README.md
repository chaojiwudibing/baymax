# Baymax — Your Personal Nutrition Skill

**English** | [简体中文](README.zh-CN.md)

A conversational nutrition assistant for healthy eating, fat loss, muscle gain, and body recomposition. Its concise entry point, state-based workflow, local records, and validation scripts are inspired by [learn-by-building](https://github.com/chaojiwudibing/learn-by-building). It focuses on nutrition planning and does not create exercise programs.

## Installation and use

Clone this repository into your Codex skills directory under the name `baymax`, then invoke `$baymax`.

```sh
git clone https://github.com/chaojiwudibing/baymax.git ~/.codex/skills/baymax
```

If the directory already exists, inspect its contents first to avoid overwriting an existing installation. Python 3.9 or later is required. Nutrition calculations use the standard library; Excel export uses openpyxl. No nutrition API subscription is required. Prefer the bundled workspace runtime in Codex desktop; otherwise install `requirements.txt` in a local virtual environment.

The initial intake consists of six short question groups. Subsequent sessions use your local profile to continue planning. The final deliverable is one readable Excel workbook covering all 30 days: menus, ingredient weights, nutrients, shopping, meal prep, substitutions, actual daily records, and review dates. Chinese headers include units; sheets have filters, frozen headers, wrapped text, and an introduction. Light blue cells are for actual records. JSON, CSV, and Markdown remain local calculation records. Reviews on days 7, 14, 21, and 30 use your actual records.

## Database and accuracy

Baymax uses a local SQLite database. It supports importing the official USDA SR28 archive and specific product labels backed by evidence. The repository does not include the database or private profiles. Follow the [data contract](references/data-contract.md) to obtain and import the data.

```sh
python3 scripts/nutrition_db.py import-sr28 --archive /path/to/sr28asc.zip --db .baymax/data/nutrition.sqlite --accessed YYYY-MM-DD
python3 scripts/nutrition_db.py search --db .baymax/data/nutrition.sqlite --query "Chicken, broilers"
python3 scripts/calculate_plan.py --db .baymax/data/nutrition.sqlite --plan .baymax/plan-input.json --out .baymax/plans/new-version --strict
```

Replace `YYYY-MM-DD` with the actual date you obtained the archive. SR28 contains historical US food composition data; it does not represent actual Chinese product labels or the latest FoodData Central data. Licensed Chinese food composition tables and live Shenzhen prices are not integrated. Physiological outcomes are not guaranteed.

Nutrients are calculated from source entries and ingredient weights, preserving source IDs, versions, and file hashes. Unknown nutrients are not treated as zero. Inconsistent raw, cooked, or dry weight bases are rejected. Converting milliliters to grams requires density evidence. Shopping calculations account for edible yields, whole-package rounding, and inventory carryover.

With `--strict`, unmatched foods, unknown nutrients, unverified prices, or an incomplete execution review produce a saved draft and exit code 1. Invalid input formats produce exit code 2. Passing validation still provides a food composition estimate, not laboratory testing, clinical approval, or an outcome guarantee. Evidence for food and SKU matches still requires manual review.

## Privacy and validation

Health profiles, actual records, and plans are stored locally in the user's `.baymax/` directory by default. They are not uploaded or included in the public repository. The skill cannot independently sense body changes or monitor you automatically.

```sh
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -v
```

The tests cover provenance, missing values, weight bases, dates, prices, inventory, meal-prep consistency, strict mode, and actual records. They use synthetic data and contain no personal health information from the developer.

Entry point: [SKILL.md](SKILL.md). Storage and reviews: [local records](references/local-records.md). Full delivery requirements: [planning and review](references/plan-and-review.md).

When revising the same period, use `calculate_plan.py --journal /path/to/old.xlsx` to preserve actual records in a new workbook. Review Excel records directly with `review_logs.py --journal /path/to/plan.xlsx --start YYYY-MM-DD --out /path/to/new-review.json`. Planned intake is never treated as actual intake.

## Optional: time-gated reminders across devices

A Microsoft To Do delivery bridge supports Windows, Android and iPhone clients. A private cloud worker creates only tasks whose scheduled time has arrived; it does not import the entire 30-day queue or depend on a personal computer remaining awake.

The code has local simulated validation, not live account, cloud or phone-notification acceptance. Enabling it requires a personal Microsoft account, application registration, a chosen cloud runtime, and explicit consent to upload task details. Excel remains the default deliverable; completion is not actual intake and notes do not automatically flow back. See the [connection and acceptance guide](references/reminder-delivery.md).

Windows installation (PowerShell):

```powershell
git clone https://github.com/chaojiwudibing/baymax.git "$env:USERPROFILE\.codex\skills\baymax"
```

Generate or revise the plan in Codex on a desktop. Android and iPhone receive enabled cloud deliveries through Microsoft To Do; they do not install the Codex skill.
