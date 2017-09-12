"""
Offer numeric state listening automation rules.

For more details about this automation rule, please refer to the documentation
at https://home-assistant.io/docs/automation/trigger/#numeric-state-trigger
"""
import asyncio
import logging

import voluptuous as vol

from homeassistant.core import callback
from homeassistant.const import (
    CONF_VALUE_TEMPLATE, CONF_PLATFORM, CONF_ENTITY_ID,
    CONF_BELOW, CONF_ABOVE, CONF_FOR)
from homeassistant.helpers.event import (
    async_track_state_change, async_track_same_state)
from homeassistant.helpers import condition, config_validation as cv

TRIGGER_SCHEMA = vol.All(vol.Schema({
    vol.Required(CONF_PLATFORM): 'numeric_state',
    vol.Required(CONF_ENTITY_ID): cv.entity_ids,
    vol.Optional(CONF_BELOW): vol.Coerce(float),
    vol.Optional(CONF_ABOVE): vol.Coerce(float),
    vol.Optional(CONF_VALUE_TEMPLATE): cv.template,
    vol.Optional(CONF_FOR): vol.All(cv.time_period, cv.positive_timedelta),
}), cv.has_at_least_one_key(CONF_BELOW, CONF_ABOVE))

_LOGGER = logging.getLogger(__name__)


@asyncio.coroutine
def async_trigger(hass, config, action):
    """Listen for state changes based on configuration."""
    entity_id = config.get(CONF_ENTITY_ID)
    below = config.get(CONF_BELOW)
    above = config.get(CONF_ABOVE)
    time_delta = config.get(CONF_FOR)
    value_template = config.get(CONF_VALUE_TEMPLATE)
    async_remove_track_same = None

    if value_template is not None:
        value_template.hass = hass

    @callback
    def check_numeric_state(entity, from_s, to_s):
        """Return True if they should trigger."""
        if to_s is None:
            return False

        variables = {
            'trigger': {
                'platform': 'numeric_state',
                'entity_id': entity,
                'below': below,
                'above': above,
            }
        }

        # If new one doesn't match, nothing to do
        if not condition.async_numeric_state(
                hass, to_s, below, above, value_template, variables):
            return False

        return True

    @callback
    def state_automation_listener(entity, from_s, to_s):
        """Listen for state changes and calls action."""
        nonlocal async_remove_track_same

        if not check_numeric_state(entity, from_s, to_s):
            return

        variables = {
            'trigger': {
                'platform': 'numeric_state',
                'entity_id': entity,
                'below': below,
                'above': above,
                'from_state': from_s,
                'to_state': to_s,
            }
        }

        # Only match if old didn't exist or existed but didn't match
        # Written as: skip if old one did exist and matched
        if from_s is not None and condition.async_numeric_state(
                hass, from_s, below, above, value_template, variables):
            return

        @callback
        def call_action():
            """Call action with right context."""
            hass.async_run_job(action, variables)

        if not time_delta:
            call_action()
            return

        async_remove_track_same = async_track_same_state(
            hass, True, time_delta, call_action, entity_ids=entity_id,
            async_check_func=check_numeric_state)

    unsub = async_track_state_change(
        hass, entity_id, state_automation_listener)

    @callback
    def async_remove():
        """Remove state listeners async."""
        unsub()
        if async_remove_track_same:
            async_remove_track_same()  # pylint: disable=not-callable

    return async_remove
