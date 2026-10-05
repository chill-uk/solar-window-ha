# Solar Window for Home Assistant

[![GitHub release](https://img.shields.io/github/release/chill-uk/solar-window-ha?include_prereleases=&sort=semver&color=blue)](https://github.com/chill-uk/solar-window-ha/releases/)
[![issues - solar-window-ha](https://img.shields.io/github/issues/chill-uk/solar-window-ha)](https://github.com/chill-uk/solar-window-ha/issues)
[![GH-code-size](https://img.shields.io/github/languages/code-size/chill-uk/solar-window-ha?color=red)](https://github.com/chill-uk/solar-window-ha)
[![GH-last-commit](https://img.shields.io/github/last-commit/chill-uk/solar-window-ha?style=flat-square)](https://github.com/chill-uk/solar-window-ha/commits/main)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Validation](https://github.com/chill-uk/solar-window-ha/actions/workflows/validate.yml/badge.svg)](https://github.com/chill-uk/solar-window-ha/actions/workflows/validate.yml)
[![Tests](https://github.com/chill-uk/solar-window-ha/actions/workflows/tests.yml/badge.svg)](https://github.com/chill-uk/solar-window-ha/actions/workflows/tests.yml)
![GitHub Downloads](https://img.shields.io/github/downloads/chill-uk/solar-window-ha/total)

A local Home Assistant custom integration and bundled dashboard card that show when your solar panels produce throughout the year.

Select your existing PV power sensors. Solar Window records daily start and finish times internally and displays **Year → Month → Week** views. No helpers, automations, extra sensors or external chart libraries are required.

> [!NOTE]
> Version 0.1.0 is an initial preview. The recording and calendar logic has automated tests, but setup, live recording and historical backfill still need verification on a real Home Assistant instance. Home Assistant 2026.4.0 or later is the intended baseline.

# Installation

### HACS installation

The quickest way to install this integration is via [HACS](https://github.com/hacs/integration) by clicking the button below:

[![Add to HACS via My Home Assistant](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=chill-uk&repository=solar-window-ha&category=integration)

1. Click the button above to add this repository to HACS as a custom integration.
2. Install **Solar Window** from HACS.
3. Restart Home Assistant.
4. Go to **Settings → Devices & services** and add **Solar Window**.
5. Configure your sources and add the dashboard card as described below.

This is a HACS custom repository; it is not listed in the default HACS catalogue.

### Manual installation

1. Download `solar_window.zip` from [Releases](https://github.com/chill-uk/solar-window-ha/releases).
2. Create `/config/custom_components/solar_window` and extract the ZIP's contents into that folder. `manifest.json` and `__init__.py` should sit directly inside it.
3. Restart Home Assistant.
4. Add **Solar Window** from **Settings → Devices & services**.

Alternatively, copy `custom_components/solar_window` from this repository into your Home Assistant config directory's `custom_components` folder.

## Configuration

Select your **PV generation power sensor(s)**. Multiple sources are added together. Use generation power, not grid export or household consumption. Sensors must have power device class and use W, kW or MW.

Optionally select the cumulative solar **energy** sensor that already supplies your Energy dashboard. This is used for historical backfill; it needs recorded long-term statistics. A power source is still required for new recordings.

Open the integration's **Configure** dialog to change the sources or detection settings:

| Setting | Default |
| --- | --- |
| Start threshold | Above 20 W |
| Stop threshold | Below 10 W |
| Start confirmation | 3 minutes |
| Stop confirmation | 10 minutes |

Solar Window is managed under **Settings → Devices & services → Integrations**. If upgrading from v0.1.0 or v0.1.1, restart Home Assistant after updating; your saved configuration and history remain in place.

## Dashboard card

The integration automatically loads the bundled card and manages its version. No dashboard resource registration is needed.

1. After installing or updating the integration, restart Home Assistant and refresh your browser.
2. Edit your dashboard, select **Add card**, and search for **Solar Window**.
3. Use the visual editor to set the title, starting view (**Year**, **Month**, or **Week**), and Solar Window installation.

With one configured installation, selection is automatic. With multiple installations, choose one from the editor's **Installation** list. The integration registers and updates its dashboard resource automatically. Existing manual Solar Window resource entries are updated too; other resources are preserved. YAML resource configurations use the automatically loaded frontend module.

<details>
<summary>Optional YAML configuration</summary>

```yaml
type: custom:solar-window-card
title: Solar production window
view: year  # year, month or week
# entry_id: YOUR_CONFIG_ENTRY_ID  # optional with one installation
```

</details>

## Explore your history

- **Year:** one thin vertical window per day, with local clock time on the vertical axis. Click a month's name or a recorded day to open that month.
- **Month:** all days grouped into Monday-based weeks. Click **Week of …** to open its seven days. Weeks crossing month or year boundaries retain their full seven-day view.
- **Week:** individual days; live recordings show separate confirmed intervals for interruptions. Times underneath explain unusual or incomplete records.
- The arrows move by year, month or week. The mode buttons switch levels. Local dates and daylight saving use Home Assistant's configured timezone.
- Under **History & data**, use **Import CSV / JSON**, **Backfill YEAR**, or **Export YEAR**. Imports and backfill require a Home Assistant administrator; viewing does not.

### Import existing switch history

Import an on/off history CSV or a previously exported Solar Window JSON through the card. A CSV must contain `entity_id,state,last_changed`, one solar entity, and timezone-bearing timestamps. Leading off events without a preceding start are ignored. Multiple same-day sessions preserve the first start and final observed stop and are marked as interrupted. Legacy switch data cannot distinguish clouds from automation faults.

The test fixture in `tests/fixtures/solar-history.json` contains synthetic example data. No personal solar history is included in this repository.

### Backfill existing Energy data

Select your cumulative energy source in integration options, navigate to the year you want, then click **Backfill YEAR**. The integration reads hourly positive energy-change bins in monthly batches. The estimated daily window covers the beginning of the first positive bin through the end of the last positive bin.

These are **hourly bounds, not exact first/last timestamps**. Very small recorded energy changes may extend an estimate beyond the live power threshold. Days with no positive bins are left missing; they do not become fabricated zero-production days. No available statistics means zero imported days. Backfill is explicitly requested, not automatic.

Existing live records outrank switch imports, which outrank hourly estimates. Re-importing data of equal quality keeps the existing record. No historical energy statistics are modified.

## Recording behaviour

- State events and a one-minute confirmation timer read the configured sources. Confirmation requires continuous valid readings; the threshold-crossing observation is retained as the boundary.
- Hysteresis keeps the previous activity state between the stop and start thresholds. Production exactly at a threshold keeps the prior state.
- A short cloud dip does not close the interval. A confirmed dip closes it provisionally. If generation returns, the first start is kept, a new interval opens and the final finish is updated after the next confirmed stop.
- The broad daily window is first start to final stop. It includes midday interruptions; it is **not** total active time or energy yield.
- Missing/unavailable/nonnumeric sources break confirmation and mark a gap for an existing live record. Other sources are not silently treated as a substitute for a missing one.
- If HA starts while generation is already high, the observed start is marked `start_unobserved`. Restarts never invent an exact start or finish during the downtime. Open live intervals close at the last persisted observation and retain a `recording_gap` flag.
- Sensor states are assumed to be current. A sensor that freezes while remaining numerically available cannot be detected reliably by this preview.
- Daily boundaries use local midnight; intervals crossing midnight are split. Charts use civil clock time, so DST days can have 23 or 25 elapsed hours.
- Records are retained without time-based purging in HA's atomic `.storage` Store (`solar_window.CONFIG_ENTRY_ID`). Keep them in your HA backups. Saves are scheduled at most once a minute with a five-second delay, and flushed on orderly unload; an abrupt crash can lose about a minute of recent observations.
- Options changes reload the integration and preserve existing records. Changes to sources/thresholds affect future detection; previous records are not recalculated. A reload may create a recording-gap marker.
- Year export is also a portable JSON backup; import preserves interval boundaries. Imported records are labelled `import`, even when they originated from another installation's live recording.

## Development and verification

No third-party dependencies are needed for the recording engine or card tests:

```bash
python -m unittest discover -s tests -v
node --test tests/*.test.js
python -m compileall -q custom_components
node --check custom_components/solar_window/frontend/solar-window-card.js
```

GitHub Actions runs the Python and JavaScript tests, Home Assistant hassfest, HACS validation, Python static checks, and release packaging. The test fixture is synthetic.

Before treating this as a stable release, verify the config/options flows, permissions, storage across restart, sensor unit conversion, frontend rendering on desktop/mobile, and historical statistics queries on a real HA instance. The local frontend tests exercise rendering/navigation in a lightweight DOM stub; they do not certify browser layout or HA API compatibility.

## Releases

Release assets follow the same layout as `ecoflow-p1-ha`: `solar_window.zip` contains the integration files at the archive root, including the bundled frontend card. Repository tests and example data are excluded.

The **Release** workflow validates the version, runs the tests, builds the ZIP, and creates or updates the matching GitHub release. It runs for:

- `v*` tags, which must match `custom_components/solar_window/manifest.json`;
- changes to the manifest or release workflow on `main`, publishing the manifest version if that release does not already exist;
- a manual workflow run.

For a new version, update the manifest, `VERSION` in `const.py`, `package.json`, and the card version references together. A main-branch run leaves an existing release untouched. Tagged/manual runs can replace the ZIP asset for that release. Tags containing a hyphen produce a GitHub prerelease.

## License

MIT
