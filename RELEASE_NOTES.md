# 1.0.91

Install InventoryUI 2.0.7 alongside this release. Backpacks now require InventoryUI during plugin loading, wait for the menu-open acknowledgement before saving, block transactions during page changes, reject slots above the configured capacity, and release aborted sessions. Existing SQLite/MySQL storage and backpack IDs are preserved.

Virtual vault merges now remove the requested amount from the actual player/cursor source rather than a detached item copy. Shutdown saves occur before Endstone destroys player objects. Regression and live protocol/SQLite checks are documented in docs/validation.md.
