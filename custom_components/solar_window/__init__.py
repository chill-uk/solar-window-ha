"""Solar Window: local recording and authenticated dashboard API."""
from __future__ import annotations
from datetime import timedelta
from pathlib import Path
import logging
import math
import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from .const import DOMAIN, VERSION, DEFAULTS
from .engine import SolarEngine

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config):
    hass.data.setdefault(DOMAIN, {})
    await hass.http.async_register_static_paths([StaticPathConfig(
        '/solar_window/solar-window-card.js', str(Path(__file__).parent / 'frontend' / 'solar-window-card.js'), False)])
    websocket_api.async_register_command(hass, ws_records)
    websocket_api.async_register_command(hass, ws_import)
    websocket_api.async_register_command(hass, ws_backfill)
    return True


async def async_setup_entry(hass, entry):
    options = entry.options or entry.data
    store = Store(hass, 1, f'{DOMAIN}.{entry.entry_id}')
    data = await store.async_load()
    engine = SolarEngine(hass.config.time_zone,
        options.get('start_w', DEFAULTS['start_w']), options.get('stop_w', DEFAULTS['stop_w']),
        options.get('start_minutes', 3) * 60, options.get('stop_minutes', 10) * 60, data)
    runtime = {'last_save_request': None, 'engine': engine, 'store': store, 'options': options, 'title': entry.title}
    hass.data[DOMAIN][entry.entry_id] = runtime

    @callback
    def sample(event=None):
        total = 0.0
        try:
            for entity_id in options['power_entities']:
                state = hass.states.get(entity_id)
                if state is None:
                    raise ValueError('Missing sensor')
                value = float(state.state)
                unit = state.attributes.get('unit_of_measurement')
                if not math.isfinite(value) or unit not in ('W', 'kW', 'MW'):
                    raise ValueError('Invalid power reading')
                total += value * {'W': 1, 'kW': 1000, 'MW': 1000000}[unit]
        except (ValueError, TypeError):
            total = None
        now = dt_util.utcnow()
        engine.sample(now, total)
        if runtime['last_save_request'] is None or (now - runtime['last_save_request']).total_seconds() >= 60:
            # Frequent state events must not indefinitely postpone the save timer.
            store.async_delay_save(engine.export, 5)
            runtime['last_save_request'] = now

    entry.async_on_unload(async_track_state_change_event(hass, options['power_entities'], sample))
    entry.async_on_unload(async_track_time_interval(hass, sample, timedelta(minutes=1)))
    entry.async_on_unload(entry.add_update_listener(_reload))
    sample()
    return True


async def _reload(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    runtime = hass.data[DOMAIN].pop(entry.entry_id)
    await runtime['store'].async_save(runtime['engine'].export())
    return True


def get_runtime(hass, connection, msg):
    runtime = hass.data[DOMAIN].get(msg['entry_id'])
    if runtime is None:
        connection.send_error(msg['id'], 'not_found', 'Solar Window entry is not loaded')
    return runtime


@websocket_api.websocket_command({vol.Required('type'): 'solar_window/records', vol.Optional('entry_id'): str,
    vol.Optional('year'): vol.All(vol.Coerce(int), vol.Range(min=1970, max=2100))})
@callback
def ws_records(hass, connection, msg):
    if 'entry_id' not in msg:
        connection.send_result(msg['id'], {'entries': [{'entry_id': key, 'title': value['title']}
            for key, value in hass.data[DOMAIN].items()], 'version': VERSION})
        return
    if (runtime := get_runtime(hass, connection, msg)) is None:
        return
    rows = runtime['engine'].days
    year = str(msg.get('year', dt_util.now().year))
    connection.send_result(msg['id'], {'days': [row for key, row in sorted(rows.items()) if key.startswith(year + '-')],
        'years': sorted({int(key[:4]) for key in rows}), 'timezone': hass.config.time_zone,
        'last_seen': runtime['engine'].last_seen, 'version': VERSION})


@websocket_api.websocket_command({vol.Required('type'): 'solar_window/import', vol.Required('entry_id'): str,
    vol.Required('days'): vol.All([dict], vol.Length(max=10000))})
@websocket_api.async_response
async def ws_import(hass, connection, msg):
    if not connection.user.is_admin:
        connection.send_error(msg['id'], 'unauthorized', 'Administrator access required')
        return
    if (runtime := get_runtime(hass, connection, msg)) is None:
        return
    try:
        count = runtime['engine'].merge(msg['days'])
    except (KeyError, ValueError, TypeError) as exc:
        connection.send_error(msg['id'], 'invalid_records', str(exc))
        return
    await runtime['store'].async_save(runtime['engine'].export())
    connection.send_result(msg['id'], {'imported': count})


@websocket_api.websocket_command({vol.Required('type'): 'solar_window/backfill', vol.Required('entry_id'): str,
    vol.Required('year'): vol.All(vol.Coerce(int), vol.Range(min=1970, max=2100))})
@websocket_api.async_response
async def ws_backfill(hass, connection, msg):
    """Read hourly change bins; keep their boundaries, never pretend they are exact."""
    if not connection.user.is_admin:
        connection.send_error(msg['id'], 'unauthorized', 'Administrator access required')
        return
    if (runtime := get_runtime(hass, connection, msg)) is None:
        return
    entity = runtime['options'].get('energy_entity')
    if not entity:
        connection.send_error(msg['id'], 'no_energy_entity', 'Select an energy sensor in integration options first')
        return
    try:
        from homeassistant.components.recorder import get_instance
        from homeassistant.components.recorder.statistics import statistics_during_period
        from .backfill import bins_to_days, month_ranges
        rows = []
        for start, end in month_ranges(msg['year'], hass.config.time_zone):
            if start >= dt_util.utcnow():
                break
            result = await get_instance(hass).async_add_executor_job(statistics_during_period,
                hass, start, min(end, dt_util.utcnow()), [entity], 'hour', None, {'change'})
            rows.extend(result.get(entity, []))
        records = bins_to_days(rows, hass.config.time_zone)
        count = runtime['engine'].merge(records)
        await runtime['store'].async_save(runtime['engine'].export())
        connection.send_result(msg['id'], {'imported': count, 'available_days': len(records)})
    except Exception:
        _LOGGER.exception('Solar Window statistics backfill failed')
        connection.send_error(msg['id'], 'backfill_failed', 'Cannot read energy statistics; see Home Assistant logs')
