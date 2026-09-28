from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from endstone.event import PlayerInteractEvent

from ninjos_backpacks.plugin import NinjOSBackpacks


@pytest.fixture
def interaction(monkeypatch):
    import endstone_inventoryui.manager.player_manager as ui

    monkeypatch.setattr(ui, "find_session", lambda player: None)
    item = SimpleNamespace(
        type="minecraft:white_shulker_box",
        item_meta=SimpleNamespace(has_lore=True, lore=["§8Backpack ID: ExistingOwner"]),
    )
    player = SimpleNamespace(
        unique_id="player-1", send_message=Mock(),
        inventory=SimpleNamespace(held_item_slot=4, get_item=Mock(return_value=item)),
    )
    event = SimpleNamespace(
        player=player, action=PlayerInteractEvent.Action.RIGHT_CLICK_AIR,
        block=None, is_cancelled=False,
    )
    plugin = SimpleNamespace(
        cfg=SimpleNamespace(item_backpacks={"gigantic": {"material": "minecraft:shulker_box"}}, block_storage={}),
        hopper_module=SimpleNamespace(manager=SimpleNamespace(linking_states={})),
        manager=Mock(), logger=Mock(),
    )
    return plugin, event, item


@pytest.mark.parametrize("action", [PlayerInteractEvent.Action.RIGHT_CLICK_AIR, PlayerInteractEvent.Action.RIGHT_CLICK_BLOCK])
@pytest.mark.parametrize("configured,stored", [
    ("minecraft:shulker_box", "minecraft:white_shulker_box"),
    ("shulker_box", "minecraft:white_shulker_box"),
    ("minecraft:white_shulker_box", "minecraft:shulker_box"),
    ("minecraft:white_shulker_box", "minecraft:white_shulker_box"),
    ("minecraft:chest", "minecraft:chest"),
    ("minecraft:ender_chest", "minecraft:ender_chest"),
])
def test_use_opens_existing_id_and_tier(interaction, action, configured, stored):
    plugin, event, item = interaction
    plugin.cfg.item_backpacks["gigantic"]["material"] = configured
    item.type = stored
    event.action = action
    NinjOSBackpacks.on_player_interact(plugin, event)
    assert event.is_cancelled
    plugin.manager.open_item_backpack.assert_called_once_with(event.player, "ExistingOwner", "gigantic", item)
    plugin.logger.error.assert_not_called()


@pytest.mark.parametrize("stored", ["minecraft:red_shulker_box", "custom:shulker_box", "minecraft:chest"])
def test_alias_does_not_match_other_materials(interaction, stored):
    plugin, event, item = interaction
    item.type = stored
    NinjOSBackpacks.on_player_interact(plugin, event)
    plugin.manager.open_item_backpack.assert_not_called()
    event.player.send_message.assert_called_once()


@pytest.mark.parametrize("reason", ["disabled", "ordinary_item", "left_click", "hopper_linking", "active_menu"])
def test_interaction_guards_still_apply(interaction, monkeypatch, reason):
    plugin, event, item = interaction
    if reason == "disabled":
        plugin.cfg.item_backpacks["gigantic"]["enabled"] = False
    elif reason == "ordinary_item":
        item.item_meta.lore = []
    elif reason == "left_click":
        event.action = PlayerInteractEvent.Action.LEFT_CLICK_AIR
    elif reason == "hopper_linking":
        plugin.hopper_module.manager.linking_states["player-1"] = True
    else:
        import endstone_inventoryui.manager.player_manager as ui
        monkeypatch.setattr(ui, "find_session", lambda player: object())
    NinjOSBackpacks.on_player_interact(plugin, event)
    plugin.manager.open_item_backpack.assert_not_called()
    plugin.logger.error.assert_not_called()
