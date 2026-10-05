"""Exercise automatic module registration with the Home Assistant API boundary mocked."""
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1] / 'custom_components' / 'solar_window'


class FrontendTests(unittest.IsolatedAsyncioTestCase):
    async def test_serves_card_before_registering_versioned_module(self):
        modules = {name: ModuleType(name) for name in (
            'homeassistant', 'homeassistant.components',
            'homeassistant.components.frontend', 'homeassistant.components.http',
            '_solar_window_test', '_solar_window_test.const')}
        modules['_solar_window_test'].__path__ = [str(ROOT)]
        version = json.loads((ROOT / 'manifest.json').read_text())['version']
        modules['_solar_window_test.const'].VERSION = version
        register = Mock()
        modules['homeassistant.components.frontend'].add_extra_js_url = register
        modules['homeassistant.components.http'].StaticPathConfig = lambda url, path, cache: SimpleNamespace(url=url, path=path, cache=cache)
        hass = SimpleNamespace(http=SimpleNamespace(async_register_static_paths=AsyncMock()), data={})
        def verify_ready(*args):
            hass.http.async_register_static_paths.assert_awaited_once()
        register.side_effect = verify_ready
        with patch.dict(sys.modules, modules):
            spec = importlib.util.spec_from_file_location('_solar_window_test.frontend', ROOT / 'frontend.py')
            frontend = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(frontend)
            await frontend.async_register_frontend(hass)
        register.assert_called_once_with(hass, f'/solar_window/solar-window-card.js?v={version}')
        static = hass.http.async_register_static_paths.call_args.args[0][0]
        self.assertEqual(static.url, '/solar_window/solar-window-card.js')
        self.assertTrue(Path(static.path).is_file())
        self.assertFalse(static.cache)
        self.assertEqual(hass.data, {})
