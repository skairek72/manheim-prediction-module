# Manheim Prediction Module

Owner: a used-car buyer at Manheim NY Metro Skyline (Tuesdays, code SKYA) and Manheim New Jersey
(Wednesdays, code NADE). New to software: explain in plain language, one step at a time, and do
the work yourself instead of asking them to move files around.

## One folder
Everything lives in this folder:
- code: `src/manheim_pm/` (Python), tests in `tests/`, buying rules template `criteria.toml`
- the user's data: `my-data/` (git-ignored, private Manheim data, never commit or upload it)
  - `my-data/manheim.db` history, `my-data/criteria.toml` their rules, `my-data/reports/` Excel output
  - `my-data/presale/` and `my-data/postsale/<sale date>/` for the Manheim PDFs
- `ManheimPrediction.exe` (git-ignored): the Windows app; it uses `my-data/` beside it

## Weekly routine (app buttons, or CLI with `--db my-data/manheim.db`)
1. Pre-sale PDF saved in `my-data/presale` -> import -> pre-sale report -> shortlist
2. After the sale, post-sale page PDFs in `my-data/postsale/<date>/` -> import folder -> scorecard
CLI: `python -m manheim_pm.cli --db my-data/manheim.db <import|presale|postsale|postsale-report|shortlist|scorecard|history>`
(`pip install -e ".[dev]"` once; run `pytest` after any change.)

## Rules
- Never automate downloads from Manheim (their terms; it is the partner's account). PDFs are printed by hand.
- Predictions: `predict.py`, condition + run-back status; only add factors the weekly scorecard shows help.
- Max bids depend on `[resale]` in criteria.toml, still a placeholder (MMR + $3,500) until the user gives real resale data.
- Pushing to `main` on GitHub rebuilds `ManheimPrediction.exe` (Releases -> latest) after tests and an .exe self-test.
