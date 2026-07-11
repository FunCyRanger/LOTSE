from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MeshData
from .calibration import CalibrationModel
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class LOTSEForecastResetButton(ButtonEntity):
    _attr_entity_category = "config"
    _attr_name = "Reset Forecast Model"
    _attr_unique_id = "lotse_forecast_reset_model"
    _attr_icon = "mdi:restore"

    def __init__(self, model: CalibrationModel) -> None:
        self._model = model

    async def async_press(self) -> None:
        self._model.reset()
        _LOGGER.warning("Calibration model reset to defaults")

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(DOMAIN, "forecast")},
            "name": "LOTSE Solar Forecast",
            "manufacturer": "LOTSE",
            "model": "Solar Forecast",
            "via_device": (DOMAIN, "coordinator"),
        }


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    model: CalibrationModel | None = hass.data[DOMAIN].get("calibration")
    if model:
        async_add_entities([LOTSEForecastResetButton(model)])
