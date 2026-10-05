"""UI setup and options; no helper entities."""
import math
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from .const import DOMAIN, DEFAULTS


def schema(values):
    fields = {vol.Required('power_entities', default=values.get('power_entities', [])):
        selector.EntitySelector(selector.EntitySelectorConfig(domain='sensor', device_class='power', multiple=True))}
    for key, default in DEFAULTS.items():
        fields[vol.Required(key, default=values.get(key, default))] = vol.All(vol.Coerce(float), vol.Range(min=0, max=100000 if key.endswith('_w') else 120))
    fields[vol.Optional('energy_entity', description={'suggested_value': values.get('energy_entity', '')})] = selector.EntitySelector(selector.EntitySelectorConfig(domain='sensor', device_class='energy'))
    return vol.Schema(fields)


def errors(values, hass):
    if not values['power_entities']:
        return {'base': 'no_power'}
    if not all(math.isfinite(values[k]) for k in DEFAULTS):
        return {'base': 'invalid_threshold'}
    if values['stop_w'] >= values['start_w']:
        return {'base': 'invalid_threshold'}
    for entity in values['power_entities']:
        state = hass.states.get(entity)
        if state is None or state.attributes.get('unit_of_measurement') not in ('W', 'kW', 'MW'):
            return {'base': 'invalid_power'}
    return {}


class SolarWindowConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errs = {}
        if user_input is not None:
            errs = errors(user_input, self.hass)
            if not errs:
                return self.async_create_entry(title='Solar Window', data=user_input)
        return self.async_show_form(step_id='user', data_schema=schema(user_input or {}), errors=errs)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SolarWindowOptionsFlow()


class SolarWindowOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        errs = {}
        if user_input is not None:
            errs = errors(user_input, self.hass)
            if not errs:
                return self.async_create_entry(title='', data=user_input)
        values = user_input if user_input is not None else (self.config_entry.options or self.config_entry.data)
        return self.async_show_form(step_id='init', data_schema=schema(values), errors=errs)
