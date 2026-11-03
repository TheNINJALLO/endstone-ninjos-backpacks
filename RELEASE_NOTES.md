# 1.0.94 — release, 2026-11-02

Follow-up validation uses two independent server stores/managers connected to the same isolated MySQL database. The preserved 1.0.93 save handler reproduces a delayed empty overwrite after session close; the 1.0.94 session/menu guards prevent it. Reconnect, shared ownership, pending-save recovery, nested bundle contents and lore pass the seven-check handoff fixture. This matches the reported timing but is not proof of the production incident's cause.

Preserve typed NBT (including nested bundles and Essentials lore), auxiliary item data and hidden slots after tier size reductions. Abort unreadable loads/saves instead of silently replacing metadata or writing partial inventories. Validate all stored items before opening. Checkpoint ordinary accepted menu transactions before acknowledgement; retain failed primary writes in a local recovery journal, pause moves and replay before reopening. Reject callbacks from an old menu. Inventory Share can hold its handoff until pending backpack writes recover.

Virtual item displays now mark the exact appended counter line. Cleanup preserves original custom lore even when it contains “Stored Amount:”; metadata and auxiliary data must match before consolidation/merging. Offline inventory editors abort failed loads. Remove Backpacks' import-time InventoryUI patches and require InventoryUI 2.0.10 instead of downloading the older 2.0.8 tag.

The local review records actual nested-bundle, SQL, GUI and write-failure checks. Cross-server Backpacks still requires a shared Backpacks database. Virtual storage retains its following-tick reconciliation; no guarantee is made for arbitrary process/power loss between unrelated player-world and plugin database writes.

# 1.0.91

Install InventoryUI 2.0.7 alongside this release. Backpacks now require InventoryUI during plugin loading, wait for the menu-open acknowledgement before saving, block transactions during page changes, reject slots above the configured capacity, and release aborted sessions. Existing SQLite/MySQL storage and backpack IDs are preserved.

Virtual vault merges now remove the requested amount from the actual player/cursor source rather than a detached item copy. Shutdown saves occur before Endstone destroys player objects. Regression and live protocol/SQLite checks are documented in docs/validation.md.
