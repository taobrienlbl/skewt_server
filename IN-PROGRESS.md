# In Progress

## Branching / session handoff

This repository has uncommitted work to add launch-centric ingest and Globus transfer orchestration for radiosonde uploads. The intent of this file is to let a later session resume from the current state without rediscovering the design.

## What was implemented

- `app/processor.py`
  - Reworked from a simple `WORK_DIR` SHARPY scan into a launch-aware pipeline.
  - New flow:
    1. scan a flat ingest directory for receiver uploads
    2. group files by shared prefix
    3. require `SUMMARY`, `SHARPPY`, `TEMP`, and at least 4 `BUFR` files
    4. parse `Launched (UTC)` from `*_SUMMARY.txt`
    5. wait for a configurable quiet period before treating files as stable
    6. stage a per-launch delivery directory under `<SITE>/<YYYYMMDD_HHMM>/`
    7. submit/poll Globus transfer
    8. render PNG only after transfer succeeds, or immediately if Globus transfer is disabled
  - Persist launch state in `STATE_PATH` so transfer status survives cron runs.
  - Manifest entries are now launch-centric and include transfer status/detail fields.

- `app/globus_transfer.py`
  - New helper module for Globus configuration, transfer submission, and task polling.
  - Uses confidential-app credentials from environment variables.

- `templates/index.html` and `static/styles.css`
  - UI now shows launch transfer state.
  - Cards can render even when image generation is pending.

- Runtime/config files
  - `docker-compose.yml`, `Dockerfile`, and `scripts/entrypoint.sh` now define/create:
    - `/data/ingest`
    - `/data/deliveries`
    - `/data/state`
  - Added Globus-related env vars and upload stability settings.

- Documentation
  - `README.md` updated for the new ingest/delivery/state workflow and env vars.

## Expected operational model

- Receiver FTP software uploads flat files into `./data/ingest`.
- Processor groups them into launches.
- Summary file provides launch time, for example:
  - `Launched (UTC)           : 3/6/2026 23:29:15`
- Delivery directory naming currently uses:
  - `<SITE>/<YYYYMMDD_HHMM>/`
- Destination path target is expected to look like:
  - `/UCRP/USIUB/20260306_2328/`

## Important open point

There is a mismatch between the sample summary launch time and the provided destination path example:

- summary sample launch time: `2026-03-06 23:29:15 UTC`
- provided destination path: `/UCRP/USIUB/20260306_2328/`

Current code uses the parsed summary launch time rounded/truncated to minute precision, which would produce `20260306_2329` unless configured otherwise.

To avoid blocking work, an env var was added:

- `LAUNCH_DIR_MINUTE_OFFSET`

Set this to `-1` if the operational convention is intentionally one minute earlier than the summary timestamp.

## Validation performed

- `python3 -m py_compile app/processor.py app/globus_transfer.py app/web.py app/site_config.py`
  - passed

What was not validated in this session:

- end-to-end processor execution in a live environment
- Docker build/run after changes
- actual Globus transfer submission
- UI rendering in browser after manifest changes

Reason:

- the sandbox environment did not have the app runtime dependencies installed for direct execution
- no live Globus credentials/collections were available in-session

## Remaining work

1. Build and run the stack with Docker.
2. Decide whether `LAUNCH_DIR_MINUTE_OFFSET` should stay `0` or become `-1`.
3. Configure Globus environment variables:
   - `ENABLE_GLOBUS_TRANSFER=true`
   - `GLOBUS_CLIENT_ID`
   - `GLOBUS_CLIENT_SECRET`
   - `GLOBUS_SOURCE_COLLECTION_ID`
   - `GLOBUS_DEST_COLLECTION_ID`
   - `GLOBUS_DEST_BASE_PATH=/UCRP`
4. Ensure the source Globus collection root corresponds to `./data/deliveries`.
5. Drop the sample upload set into `./data/ingest` and confirm:
   - delivery directory is created as expected
   - transfer task is submitted
   - `data/state/launches.json` updates across cron runs
   - PNG is rendered only after transfer success
   - website shows transfer state correctly
6. Decide whether the summary file should remain excluded from the Globus payload.
7. Consider whether successful launches should be archived/moved out of `data/ingest` after transfer and rendering to avoid indefinite accumulation.

## Files changed in this session

- `Dockerfile`
- `README.md`
- `app/globus_transfer.py`
- `app/processor.py`
- `docker-compose.yml`
- `pyproject.toml`
- `scripts/entrypoint.sh`
- `static/styles.css`
- `templates/index.html`
- `data/ingest/.gitkeep`
- `data/deliveries/.gitkeep`
- `data/state/.gitkeep`

## Files intentionally left untracked

- `test_upload_data_no_git/`
  - sample input data used for design/inspection only
  - not added to git in this session
