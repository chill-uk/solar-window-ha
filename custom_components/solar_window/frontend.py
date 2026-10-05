"""Serve and automatically load the bundled dashboard card."""
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.components.lovelace.resources import ResourceStorageCollection

from .const import VERSION

CARD_URL = '/solar_window/solar-window-card.js'


async def async_register_frontend(hass):
    """Serve the module and register it for both frontend and Lovelace loading."""
    await hass.http.async_register_static_paths([
        StaticPathConfig(CARD_URL, str(Path(__file__).parent / 'frontend' / 'solar-window-card.js'), False)
    ])
    url = f'{CARD_URL}?v={VERSION}'
    add_extra_js_url(hass, url)
    resources = hass.data[LOVELACE_DATA].resources
    if not isinstance(resources, ResourceStorageCollection):
        # YAML resources are read-only; the extra module handles those dashboards.
        return
    # Lovelace loads storage lazily. Load before creating anything so existing
    # user resources cannot be replaced by an incomplete in-memory collection.
    await resources.async_get_info()
    matches = [item for item in resources.async_items()
               if item['url'].split('?')[0] == CARD_URL]
    if not matches:
        await resources.async_create_item({'url': url, 'res_type': 'module'})
    else:
        for item in matches:
            if item['url'] != url or item['type'] != 'module':
                await resources.async_update_item(item['id'], {'url': url, 'res_type': 'module'})
