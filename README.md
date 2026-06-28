# RHC Estimating Tool

A field estimating web app for contractors. Upload job drawings, extract material lists with AI vision, and generate labor/materials estimates calibrated against your own historical job data.

## Features

- **Drawing Reader** — Upload a photo or PDF of a handwritten drawing. Claude extracts every material, product code, quantity, and spec into an editable table. Saves to the project automatically.
- **AI Estimates** — Enter job type, square footage, and qualifiers. The tool filters your job history to find comparable jobs, then uses Claude to produce a labor + materials estimate with a confidence range.
- **Qualifier Matching** — Tag every job with finish level, demo scope, layout change, home age, and cabinet type (kitchens). Estimates only compare against jobs with matching qualifiers so you're not averaging a budget cosmetic refresh against a high-end full gut.
- **Job History** — View all historical jobs with inline tag editing. Tag changes propagate immediately to the estimator's comp pool.
- **Dashboard** — Labor variance stats by job type, over/under performance, recent jobs.

## Tech stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 (ESM CDN), HTM, inline styles — single `index.html`, no build step |
| Backend | AWS Lambda (Python 3.12), API Gateway HTTP API |
| Database | DynamoDB (pay-per-request) |
| AI | Anthropic Claude (`claude-sonnet-4-6`) |
| Infrastructure | AWS SAM |

## Project structure

```
fieldquote/
├── frontend/
│   └── index.html       # Full frontend — React components, styles, sample data
├── lambda/
│   └── handler.py       # Lambda handler — routing, Claude API calls, DynamoDB CRUD
├── template.yaml        # SAM template
├── samconfig.toml       # SAM deploy config
└── CLAUDE.md            # AI session context (loaded automatically by Claude Code)
```

## Getting started

### Prerequisites
- AWS CLI configured with appropriate permissions
- AWS SAM CLI installed
- Anthropic API key

### Deploy backend

```bash
sam build && sam deploy
```

This creates:
- Lambda function `fieldquote-api`
- API Gateway HTTP API
- DynamoDB table
- S3 bucket for the frontend

After deploy, note the `ApiUrl` and `BucketName` outputs.

### Set the Anthropic API key

```bash
aws lambda update-function-configuration \
  --function-name fieldquote-api \
  --environment "Variables={ANTHROPIC_API_KEY=sk-ant-YOUR_KEY,PROJECTS_TABLE=fieldquote-projects-fieldquote}"
```

### Deploy frontend

Update `API_URL` in `frontend/index.html` if your API Gateway URL has changed, then:

```bash
aws s3 cp frontend/index.html s3://YOUR_BUCKET_NAME/index.html
```

Open the `FrontendUrl` output from the SAM deploy in a browser.

## Qualifier fields

Each job in the history can be tagged with:

| Field | Options | Notes |
|-------|---------|-------|
| Finish Level | Budget / Mid-Range / High-End | |
| Demo Scope | Cosmetic / Partial / Full Gut | |
| Layout Change | Yes / No | Walls moved, plumbing relocated |
| Home Age | Modern (post-1980) / Older (pre-1980) | |
| Cabinet Type | Stock / Semi-Custom / Custom | Kitchen Remodel only |

**Matching logic:** Finish Level and Demo Scope are hard filters (exact match required). Layout Change, Home Age, and Cabinet Type add bonus weight. If fewer than 2 exact matches exist, the tool relaxes filters and warns you, showing the closest comps with differences highlighted in amber.

## Local development

The frontend runs without any build step — just open `frontend/index.html` in a browser. It calls the deployed API Gateway URL directly. For backend changes, redeploy with `sam build && sam deploy`.
