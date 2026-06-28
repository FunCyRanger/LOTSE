DOMAIN = "lotse_forecast"

PLATFORMS = ["energy"]


async def async_setup_entry(hass, entry):
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {}
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass, entry):
    await hass.config_entries.async_forward_entry_unload(entry, "energy")
    hass.data[DOMAIN].pop(entry.entry_id, None)
    return True
