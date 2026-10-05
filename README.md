# Solar Window for Home Assistant — v0.1.0 preview

A local Home Assistant custom integration and bundled dashboard card that show when your solar panels produce throughout the year. No helpers, automations, extra sensors or external chart libraries are required.

**Status:** first installable preview. Detection, imports and calendar calculations have automated tests. This build has not been run against a live Home Assistant instance. Intended baseline: Home Assistant 2026.4; verify setup, recording, options reload and Recorder backfill on your instance before relying on it.

## Install

1. Extract this archive. Copy `custom_components/solar_window` into `/config/custom_components/solar_window` in Home Assistant. Do not copy the outer `solar-window` project folder into `custom_components`.
2. Restart Home Assistant.
3. Open **Settings → Devices & services → Add integration → Solar Window**.
4. Select your **PV generation power sensor(s)**. Multiple sources are added together. Use generation power, not grid export or household consumption. Sensors must have power device class and use W, kW or MW.
5. Optionally select the cumulative solar **energy** sensor that already supplies your Energy dashboard. This is used only for historical backfill; it needs recorded long-term statistics. The power source is still required for new recordings.
6. Keep the defaults initially: start above 20 W for 3 minutes; stop below 10 W for 10 minutes. Change them later through the integration's options.
7. In **Settings → Dashboards → ⋮ → Resources**, add:
   - URL: `/solar_window/solar-window-card.js?v=0.1.0`
   - Type: **JavaScript Module**
   Enable Advanced Mode on your user profile if Resources is hidden. Resource registration is manual in this preview.
8. Add a Manual card to a dashboard:

```yaml
type: custom:solar-window-card
title: Solar production window
```

A card with one configured integration selects it automatically. If you configure multiple installations, specify `entry_id`. You can find it by opening the integration's configuration entry page and copying its ID from the URL:

```yaml
type: custom:solar-window-card
entry_id: YOUR_CONFIG_ENTRY_ID
view: year  # year, month or week
```

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

The project includes the source, tests and an example GitHub Actions workflow. It supports manual installation from this repository. HACS distribution is not configured yet.

Before treating this as a stable release, verify the config/options flows, permissions, storage across restart, sensor unit conversion, frontend rendering on desktop/mobile, and historical statistics queries on a real HA instance. The local frontend tests exercise rendering/navigation in a lightweight DOM stub; they do not certify browser layout or HA API compatibility.
