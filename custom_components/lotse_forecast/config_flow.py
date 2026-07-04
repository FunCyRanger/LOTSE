from __future__ import annotations

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from . import DOMAIN


class LotseForecastConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2

    async def async_step_user(self, user_input=None) -> FlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(
                title="LOTSE Solar Forecast",
                data={"weather_entity": user_input["weather_entity"]},
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("weather_entity"): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="weather"),
                ),
            }),
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        return LotseForecastOptionsFlow(config_entry)


class LotseForecastOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None) -> FlowResult:
        panels = self.config_entry.options.get("panels", [])

        if user_input is not None:
            removed = user_input.get("remove_panels", [])
            if removed:
                indices = {int(i) for i in removed}
                panels = [p for i, p in enumerate(panels) if i not in indices]

            if user_input.get("add_panel"):
                new_options = {**self.config_entry.options, "panels": panels}
                new_data = {
                    **self.config_entry.data,
                    "weather_entity": user_input["weather_entity"],
                }
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=new_data, options=new_options,
                )
                return await self.async_step_add_panel()

            new_options = {"panels": panels}
            new_data = {
                **self.config_entry.data,
                "weather_entity": user_input["weather_entity"],
            }
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=new_data, options=new_options,
            )
            return self.async_create_entry(title="", data={})

        weather_entity = self.config_entry.data.get("weather_entity", "")
        schema = {
            vol.Required("weather_entity", default=weather_entity): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="weather"),
            ),
        }

        if panels:
            choices = {
                str(i): f"{p['name']} ({p['kwp']} kWp, {p['angle']}°, {p['azimuth']}°)"
                for i, p in enumerate(panels)
            }
            schema[vol.Optional("remove_panels", default=[])] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[{"value": k, "label": v} for k, v in choices.items()],
                    multiple=True,
                    mode="list",
                ),
            )

        schema[vol.Optional("add_panel", default=False)] = selector.BooleanSelector()

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema),
        )

    async def async_step_add_panel(self, user_input=None) -> FlowResult:
        if user_input is not None:
            panels = list(self.config_entry.options.get("panels", []))
            panels.append({
                "name": user_input["name"],
                "kwp": user_input["kwp"],
                "angle": user_input["angle"],
                "azimuth": user_input["azimuth"],
            })
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                options={**self.config_entry.options, "panels": panels},
            )
            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="add_panel",
            data_schema=vol.Schema({
                vol.Required("name", default="Panel"): str,
                vol.Required("kwp"): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0.1, max=100, step=0.1, mode="box",
                                                   unit_of_measurement="kWp"),
                ),
                vol.Required("angle", default=35): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=90, step=1, mode="box",
                                                   unit_of_measurement="°"),
                ),
                vol.Required("azimuth", default=180): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=360, step=1, mode="box",
                                                   unit_of_measurement="°"),
                ),
            }),
        )
