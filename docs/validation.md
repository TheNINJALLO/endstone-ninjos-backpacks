# 1.0.92 validation

Backpacks 1.0.91 was reproduced failing to open an assigned gigantic backpack through a real `RIGHT_CLICK_AIR` interaction. The server stored the item as `minecraft:white_shulker_box`, while the configured material remained `minecraft:shulker_box`. No InventoryUI session was created. Version 1.0.92 matches both names and preserves the existing storage ID.

The Backpacks and InventoryUI unit suites pass all **49 tests**. Seven built-wheel scenarios passed on BDS 1.26.51.1 / Endstone 0.11.11 / Windows x64 / Python 3.11:

| Tier/configuration | Air interaction | Block interaction |
|---|---|---|
| Small (27 slots) | Passed | Passed |
| Large (54 slots) | Passed | Passed |
| Gigantic (90 slots, current name) | Passed | Passed |
| Gigantic (legacy `shulker_box`) | Passed using source | Passed using built wheel |

Each built-wheel scenario verifies the real interaction event, chest open acknowledgement and decoded inventory, item deposit/withdrawal, named/custom NBT preservation, SQLite close/reopen, and final save during shutdown with a normal server exit. The gigantic tier also verifies both page buttons. Small and large fit in a single menu and have no page actions.

The independently encoded Gophertunnel 1.62.0 client uses protocol 2193. It waits for an in-world spawn and selects the assigned backpack before using it. The probe seeds the client's initial inventory snapshot; native inventory refresh and retail UI rendering are outside this coverage. The tests do not establish touch/controller behavior, MySQL behavior, or production deployment.

See [machine-readable results and wheel hashes](validation/1.0.92.json) and the [reproduction guide](https://github.com/TheNINJALLO/endstone-inventoryui/blob/main/tests/live/README.md). The original 1.0.91 tests below called the manager directly and did not cover item interaction.

## Earlier 1.0.91 validation

BDS 1.26.51.1 / Endstone 0.11.11 / Windows x64 / Python 3.11, using an independently encoded Gophertunnel 1.62.0 client (protocol 2193).

- Menu opens through the latency acknowledgement without a packet violation warning.
- Named items retain full custom NBT while depositing, withdrawing, saving to SQLite, and reopening.
- Next/previous page actions preserve contents.
- Server stop with a menu open saves the last transfer and exits normally.
- Virtual vault deposits consume the requested source amount; withdrawals and pagination preserve the total across storage and player inventory.

The reproducible runner and client are in [InventoryUI tests/live](https://github.com/TheNINJALLO/endstone-inventoryui/tree/v2.0.7/tests/live). The runner creates disposable offline servers; it requires the supplied Windows BDS fixture and pinned client. This is a protocol integration test, not a retail-client visual test or a production rollout.
