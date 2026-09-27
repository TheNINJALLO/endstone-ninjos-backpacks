# 1.0.91 validation

BDS 1.26.51.1 / Endstone 0.11.11 / Windows x64 / Python 3.11, using an independently encoded Gophertunnel 1.62.0 client (protocol 2193).

- Menu opens through the latency acknowledgement without a packet violation warning.
- Named items retain full custom NBT while depositing, withdrawing, saving to SQLite, and reopening.
- Next/previous page actions preserve contents.
- Server stop with a menu open saves the last transfer and exits normally.
- Virtual vault deposits consume the requested source amount; withdrawals and pagination preserve the total across storage and player inventory.

The reproducible runner and client are in [InventoryUI tests/live](https://github.com/TheNINJALLO/endstone-inventoryui/tree/v2.0.7/tests/live). The runner creates disposable offline servers; it requires the supplied Windows BDS fixture and pinned client. This is a protocol integration test, not a retail-client visual test or a production rollout.
