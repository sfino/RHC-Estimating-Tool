# RHC Estimating Tool — Claude Session Context

Current release: **v0.1.1**

## Project overview
A contractor field-estimating web app. Estimators upload job drawings (photos/PDFs), extract material lists via Claude's vision API, and generate AI-powered labor/materials estimates calibrated against historical job data with qualifier-based comp matching.

## Tech stack
- **Frontend**: Single-file `frontend/index.html` — vanilla React 18 via ESM CDN (no build step), HTM for JSX-like templating, IBM Plex Mono + Inter fonts
- **Backend**: AWS Lambda (Python 3.12, arm64) behind API Gateway (HTTP API)
- **Database**: DynamoDB (pay-per-request), one table for project metadata and extracted results
- **Drawing storage**: Private S3 bucket; project reads generate temporary signed URLs
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
├── CHANGELOG.md            # Version history and migration notes
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
| GET | /projects/{id} | Get project and attach signed URLs to stored drawings |
| POST | /projects/{id}/drawing | Store the source file in S3 and append drawing metadata/results |
| POST | /projects/{id}/estimate | Append estimate result to project |

## Key features
- **Drawing reader**: Upload photo/PDF → Claude extracts material list as editable table → source file saves to private S3 → result metadata saves to DynamoDB
- **Refresh restoration**: Hash routes retain the selected project; the latest saved drawing and complete material table are rehydrated on load
- **Drawing viewer**: Full-width image zoom/pan controls, embedded PDF display, download link, and legacy-record fallback
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
export ANTHROPIC_API_KEY="sk-ant-YOUR-KEY"
sam build
sam deploy --parameter-overrides "AnthropicApiKey=${ANTHROPIC_API_KEY}"
```
`confirm_changeset = true` in samconfig so it will prompt before applying.

**Frontend (S3)**:
```bash
aws s3 cp frontend/index.html s3://fieldquote-<ACCOUNT_ID>-us-east-1/index.html
```
Or find the bucket name from the SAM stack outputs: `aws cloudformation describe-stacks --stack-name fieldquote --query "Stacks[0].Outputs"`

**ANTHROPIC_API_KEY**: `template.yaml` declares this as the `AnthropicApiKey` `NoEcho` parameter. Pass it at deployment time from a shell environment variable; never place it in the template, `samconfig.toml`, or Git.

## GitHub
Repo: https://github.com/sfino/RHC-Estimating-Tool  
User: sfino

## Important notes
- The Lambda's `_estimate()` reads `qualifiers` and `compMatchInfo` from the POST body — the frontend sends these with every estimate request. If you change the qualifier fields in the frontend, update the prompt-building logic in `handler.py` too.
- DynamoDB stores Decimals — `_to_dynamo` / `_from_dynamo` helpers handle float↔Decimal conversion. Don't skip these when adding new numeric fields.
- Drawing binaries must stay out of DynamoDB's project records. `_save_drawing()` removes base64 input, writes the file to S3, and stores only `fileKey`, `mediaType`, and extracted result metadata.
- `_get_project()` generates signed drawing URLs; never persist those temporary URLs in DynamoDB.
- Pre-v0.1.1 drawing records have no `fileKey`. The frontend restores their tables and intentionally displays an image-unavailable notice.
- The frontend uses `jobs` state (lifted to `App`) — both `JobsTable` and `EstimateTab` (via `ProjectDetail`) consume it so tag edits propagate to comp matching.
- No auth layer currently. API Gateway is open with CORS `*`.
