# Changelog

All notable changes to RHC Estimating Tool are documented here.

## [0.1.1] - 2026-06-29

### Added

- Private S3 storage for uploaded drawing images and PDFs.
- Temporary signed drawing URLs when loading a project.
- URL hash routing so refreshing keeps the current project open.
- Automatic restoration of the latest drawing, notes, and complete material table.
- Full-width drawing viewer with image zoom, pan, reset, and PDF support.
- Download controls and persisted drawing filename/type metadata.

### Changed

- Anthropic credentials are now supplied through a CloudFormation `NoEcho` parameter.
- Project drawing metadata remains in DynamoDB while binary files live in S3.
- Drawing and estimate form state survives tab changes within an open project.

### Fixed

- Prevented `Cannot read properties of undefined (reading 'map')` when an AI response omits the expected material list.
- Restored legacy drawing tables after refresh even when the original file is unavailable.

### Migration notes

- Deploy with `AnthropicApiKey` supplied as a parameter.
- Existing saved drawings have no stored source image; upload them again if the image must appear in the restored workspace.
