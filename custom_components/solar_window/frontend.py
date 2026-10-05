"""Serve and automatically load the bundled dashboard card."""
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig

from .const import VERSION

CARD_URL = '/solar_window/solar-window-card.js'


async def async_register_frontend(hass):
    """Register the module without editing users' Lovelace resources."""
    await hass.http.async_register_static_paths([
        StaticPathConfig(CARD_URL, str(Path(__file__).parent / 'frontend' / 'solar-window-card.js'), False)
    ])
    add_extra_js_url(hass, f'{CARD_URL}?v={VERSION}')
