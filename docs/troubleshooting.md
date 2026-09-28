# Opening backpacks

Install Backpacks **1.0.92** and InventoryUI **2.0.7** in the server's `plugins/` directory. Stop the server before replacing wheels, keep one wheel per plugin, and preserve the plugin data directories. Startup should report both plugins enabled at those versions.

Hold the assigned backpack in the selected hotbar slot and use it against air or a block. `/backpack` displays help; it does not open storage. Staff can issue an item with `/backpack assign <player> <small|large|gigantic>`. `/backpack info` reads the identity of the held backpack.

Existing `minecraft:shulker_box` configurations and issued gigantic backpacks work in 1.0.92 without changing the config or reissuing items. The current item name is `minecraft:white_shulker_box`. Keep the `§8Backpack ID: {id}` line in custom lore templates so issued items retain their storage identity.

Finish hopper linking and close any existing inventory menu before opening another backpack. A configured block vault takes priority when that vault is clicked. Ownership restrictions and disabled tiers still apply.

If the item still does nothing, check the startup log for plugin enable failures, confirm the two versions above, and check `/backpack info` while holding it. Report the player's device, the configured tier/material, and any `[Backpack ERROR]` entry. The automated coverage and its limits are listed in [validation](validation.md).
