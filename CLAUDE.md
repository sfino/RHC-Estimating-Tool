# RHC Estimating Tool — Claude Session Context

## Project overview
A contractor field-estimating web app. Estimators upload job drawings (photos/PDFs), extract material lists via Claude's vision API, and generate AI-powered labor/materials estimates calibrated against historical job data with qualifier-based comp matching.

## Tech stack
- **Frontend**: Single-file `frontend/index.html` — vanilla React 18 via ESM CDN (no build step), HTM for JSX-like templating, IBM Plex Mono + Inter fonts
- **Backend**: AWS Lambda (Python 3.12, arm64) behind API Gateway (HTTP API)
- **Database**: DynamoDB (pay-per-request), one table for projects
- **AI**: Claude `claude-sonnet-4-6` via Anthropic API — two uses: drawing extraction (`/read-drawing`) and estimate generation (`/estimate`)
- **IaC**: AWS SAM (`template.yaml` + `samconfig.toml`), stack name `fieldquote`, region `us-east-1`

## File structure
```
fieldquote/
├── frontend/
│   └── index.html          # Entire frontend — edit this file for all UI changes
├── lambda/
│   └── handler.py          # All backend logic — routes, Claude calls, DynamoDB CRUD
├── template.yaml           # SAM template (Lambda, API GW, DynamoDB, S3)
├── samconfig.toml          # SAM deploy config (stack: fieldquote, region: us-east-1)
├── CLAUDE.md               # This file
└── README.md
```

## API endpoints (API GW URL: https://3htfajhzp4.execute-api.us-east-1.amazonaws.com)
| Method | Path | Purpose |
|--------|------|---------|
| POST | /read-drawing | Claude vision → extract material list from image/PDF |
| POST | /estimate | Claude text → generate labor/materials estimate |
| GET | /projects | List all projects (DynamoDB scan) |
| POST | /projects | Create project |
| GET | /projects/{id} | Get single project with drawings + estimates |
| POST | /projects/{id}/drawing | Append drawing result to project |
| POST | /projects/{id}/estimate | Append estimate result to project |

## Key features
- **Drawing reader**: Upload photo/PDF → Claude extracts material list as editable table → auto-saves to project
- **Estimate generator**: Select job type + sqft + qualifiers → qualifier-filtered comp matching → Claude estimate → comp cards
- **Qualifier system**: Jobs tagged with `finishLevel`, `demoScope`, `layoutChange`, `homeAge`, `cabinetType` (kitchen only). Hard filters on finishLevel/demoScope; soft scoring on the rest. Relaxes to nearest comps if < 2 exact matches.
- **Job History**: Editable tag editor per row (inline dropdowns). Tags update live and affect estimate comp matching.
- **Dashboard**: Variance stats, labor variance bars by job type, recent jobs

## Design system
- Dark slate background `#1C2127`, card `#222831`, darker `#141820`
- Amber accent `#D4822A` (primary buttons, badges, highlights)
- Teal `#3AAFA9` (positive/under-estimate), red `#E05252` (over-estimate)
- Monospace numbers: IBM Plex Mono; UI text: Inter
- No build tooling — all styles are inline JS objects in the `S` constant

## SAMPLE_JOBS
12 hardcoded jobs in `index.html` used as comparable job history. All have qualifier fields. Realistic: kitchen full guts = High-End/Custom, budget jobs = Stock/Cosmetic, older homes have layout changes.

## Deploy workflow
Frontend and backend deploy separately:

**Backend (Lambda + infra)**:
```bash
sam build && sam deploy
```
`confirm_changeset = true` in samconfig so it will prompt before applying.

**Frontend (S3)**:
```bash
aws s3 cp frontend/index.html s3://fieldquote-<ACCOUNT_ID>-us-east-1/index.html
```
Or find the bucket name from the SAM stack outputs: `aws cloudformation describe-stacks --stack-name fieldquote --query "Stacks[0].Outputs"`

**ANTHROPIC_API_KEY**: Set in Lambda environment variables via AWS Console or:
```bash
aws lambda update-function-configuration --function-name fieldquote-api \
  --environment "Variables={ANTHROPIC_API_KEY=sk-ant-...,PROJECTS_TABLE=fieldquote-projects-fieldquote}"
```

## GitHub
Repo: https://github.com/sfino/RHC-Estimating-Tool  
User: sfino

## Important notes
- The Lambda's `_estimate()` reads `qualifiers` and `compMatchInfo` from the POST body — the frontend sends these with every estimate request. If you change the qualifier fields in the frontend, update the prompt-building logic in `handler.py` too.
- DynamoDB stores Decimals — `_to_dynamo` / `_from_dynamo` helpers handle float↔Decimal conversion. Don't skip these when adding new numeric fields.
- The frontend uses `jobs` state (lifted to `App`) — both `JobsTable` and `EstimateTab` (via `ProjectDetail`) consume it so tag edits propagate to comp matching.
- No auth layer currently. API Gateway is open with CORS `*`.
