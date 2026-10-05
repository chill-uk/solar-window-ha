"""Exercise frontend registration and safe Lovelace resource updates."""
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1] / 'custom_components' / 'solar_window'


class StorageResources:
    def __init__(self, items):
        self.persisted = [dict(item) for item in items]
        self.items = []
        self.loaded = False
        self.loads = 0
        self.mutations = 0

    async def async_get_info(self):
        if not self.loaded:
            self.items = [dict(item) for item in self.persisted]
            self.loaded = True
            self.loads += 1
        return {'resources': len(self.items)}

    def async_items(self):
        if not self.loaded:
            raise AssertionError('Read before loading existing resources')
        return self.items

    async def async_create_item(self, data):
        if not self.loaded:
            raise AssertionError('Creating before load would erase stored resources')
        self.items.append({'id': 'new', 'url': data['url'], 'type': data['res_type']})
        self.persisted = [dict(item) for item in self.items]
        self.mutations += 1

    async def async_update_item(self, item_id, data):
        item = next(item for item in self.items if item['id'] == item_id)
        item.update(url=data['url'], type=data['res_type'])
        self.persisted = [dict(item) for item in self.items]
        self.mutations += 1


class FrontendTests(unittest.IsolatedAsyncioTestCase):
    async def register(self, resources):
        modules = {name: ModuleType(name) for name in (
            'homeassistant', 'homeassistant.components',
            'homeassistant.components.frontend', 'homeassistant.components.http',
            'homeassistant.components.lovelace', 'homeassistant.components.lovelace.const',
            'homeassistant.components.lovelace.resources',
            '_solar_window_test', '_solar_window_test.const')}
        modules['_solar_window_test'].__path__ = [str(ROOT)]
        version = json.loads((ROOT / 'manifest.json').read_text())['version']
        modules['_solar_window_test.const'].VERSION = version
        register = Mock()
        modules['homeassistant.components.frontend'].add_extra_js_url = register
        modules['homeassistant.components.http'].StaticPathConfig = lambda url, path, cache: SimpleNamespace(url=url, path=path, cache=cache)
        modules['homeassistant.components.lovelace.const'].LOVELACE_DATA = 'lovelace'
        modules['homeassistant.components.lovelace.resources'].ResourceStorageCollection = StorageResources
        hass = SimpleNamespace(http=SimpleNamespace(async_register_static_paths=AsyncMock()),
                               data={'lovelace': SimpleNamespace(resources=resources)})
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
        return f'/solar_window/solar-window-card.js?v={version}'

    async def test_loads_and_preserves_other_resources_before_adding_card(self):
        other = {'id': 'other', 'url': '/hacsfiles/another-card.js', 'type': 'module'}
        resources = StorageResources([other])
        url = await self.register(resources)
        self.assertEqual(resources.persisted, [other, {'id': 'new', 'url': url, 'type': 'module'}])
        self.assertEqual(resources.loads, 1)

    async def test_updates_older_manual_resource_without_duplicates(self):
        resources = StorageResources([{'id': 'existing', 'url': '/solar_window/solar-window-card.js?v=0.1.0', 'type': 'js'}])
        url = await self.register(resources)
        self.assertEqual(resources.persisted, [{'id': 'existing', 'url': url, 'type': 'module'}])
        await self.register(resources)
        self.assertEqual(resources.mutations, 1)
        self.assertEqual(resources.loads, 1)

    async def test_yaml_resources_use_frontend_module_without_mutation(self):
        resources = SimpleNamespace(async_get_info=AsyncMock(), async_create_item=AsyncMock())
        await self.register(resources)
        resources.async_get_info.assert_not_awaited()
        resources.async_create_item.assert_not_awaited()
