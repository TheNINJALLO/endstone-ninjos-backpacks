import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from endstone.nbt import CompoundTag, ListTag, StringTag, IntTag, ByteTag, ShortTag

from ninjos_backpacks import serializer
from ninjos_backpacks.database import Database
from ninjos_backpacks.manager import BackpackManager
from ninjos_backpacks.recovery import PendingSave
from ninjos_backpacks.manager import item_identity, different_storage_items, VISUAL_MARKER


class Item:
    def __init__(self, kind='minecraft:diamond', amount=1, data=0):
        self.type, self.amount, self.data = kind, amount, data
        self.nbt = CompoundTag()


@pytest.fixture(autouse=True)
def fake_item_constructor(monkeypatch):
    monkeypatch.setattr(serializer, 'ItemStack', Item)


def filled_bundle():
    nested = CompoundTag({'Name': StringTag('minecraft:diamond'), 'Count': ByteTag(7),
                          'Damage': ShortTag(0), 'Slot': ByteTag(0),
                          'tag': CompoundTag({'display': CompoundTag({'Lore': ListTag([StringTag('§dEssentials quest reward')])})})})
    return CompoundTag({'storage_item_component_content': ListTag([nested]), 'bundle_weight': IntTag(7),
                        'display': CompoundTag({'Name': StringTag('§6Treasure'),
                                                'Lore': ListTag([StringTag('§aOwner: Ninja'), StringTag('Unicode ✔')])})})


def test_bundle_contents_and_essentials_lore_round_trip_json():
    item = Item('minecraft:red_bundle')
    item.nbt = filled_bundle()
    saved = json.loads(json.dumps(serializer.serialize_item(item)))
    restored = serializer.deserialize_item(saved)
    assert serializer.nbt_to_dict(restored.nbt) == serializer.nbt_to_dict(item.nbt)


def test_auxiliary_item_data_survives_save_and_load():
    item = Item('minecraft:potion', data=13)
    assert serializer.deserialize_item(serializer.serialize_item(item)).data == 13


def test_nbt_read_failure_does_not_become_a_plain_item():
    class Broken:
        type, amount, data = 'minecraft:red_bundle', 1, 0
        @property
        def nbt(self):
            raise RuntimeError('native NBT read failed')
    with pytest.raises(ValueError, match='NBT'):
        serializer.serialize_item(Broken())


def test_nbt_write_failure_does_not_return_a_plain_item(monkeypatch):
    class Broken(Item):
        @property
        def nbt(self):
            return CompoundTag()
        @nbt.setter
        def nbt(self, value):
            if value:
                raise RuntimeError('native NBT write failed')
    monkeypatch.setattr(serializer, 'ItemStack', Broken)
    with pytest.raises(ValueError, match='NBT'):
        serializer.deserialize_item({'type': 'minecraft:red_bundle', 'nbt': serializer.nbt_to_dict(filled_bundle())})


def test_unknown_saved_tag_cannot_be_coerced_to_a_string():
    with pytest.raises(ValueError):
        serializer.dict_to_nbt({'_type': 'unknown', 'value': 'lost original type'})


def test_backpack_read_error_is_distinct_from_missing_record(tmp_path):
    db = Database(tmp_path / 'backpacks.db', Mock())
    assert db.get_item_backpack('not-created') is None
    db._get_connection = Mock(side_effect=OSError('offline'))
    with pytest.raises(OSError):
        db.get_item_backpack('existing-pack')


def test_serialization_failure_never_replaces_saved_contents(monkeypatch):
    plugin = SimpleNamespace(db=Mock(), cfg=SimpleNamespace(), logger=Mock())
    manager = BackpackManager(plugin)
    manager.supports_virtual_stacks = lambda _: False
    manager.contents_caches['player'] = {'0': {'type': 'minecraft:diamond', 'amount': 9}}
    monkeypatch.setattr('ninjos_backpacks.manager.serialize_item', Mock(side_effect=ValueError('NBT failed')))
    menu = SimpleNamespace(inventory=SimpleNamespace(get_item=lambda _: Item()))
    with pytest.raises(ValueError):
        manager.save_backpack_contents('pack', 'small', 1, 'player', 'Player', menu, False, 'player')
    plugin.db.save_item_backpack.assert_not_called()
    assert manager.contents_caches['player']['0']['amount'] == 9


def test_shrunken_tier_preserves_hidden_slots():
    plugin = SimpleNamespace(db=Mock(), cfg=SimpleNamespace(), logger=Mock())
    manager = BackpackManager(plugin)
    manager.supports_virtual_stacks = lambda _: False
    hidden = {'type': 'minecraft:diamond', 'amount': 9}
    manager.contents_caches['player'] = {'40': hidden}
    menu = SimpleNamespace(inventory=SimpleNamespace(get_item=lambda _: None))
    manager.save_backpack_contents('pack', 'small', 27, 'player', 'Player', menu, False, 'player')
    assert plugin.db.save_item_backpack.call_args.args[-1]['40'] == hidden


def test_failed_primary_write_recovers_complete_bundle_after_restart(tmp_path, monkeypatch):
    path = tmp_path / 'backpacks.db'
    db = Database(path, Mock())
    db.save_item_backpack('pack', 'large', 90, 'owner', 'Owner', {})
    item = Item('minecraft:red_bundle')
    item.nbt = filled_bundle()
    contents = {'0': serializer.serialize_item(item)}
    monkeypatch.setattr(db, '_write_item_backpack', Mock(side_effect=OSError('database offline')))
    with pytest.raises(PendingSave):
        db.save_item_backpack('pack', 'large', 90, 'owner', 'Owner', contents)
    assert db.recovery.get('pack')['contents'] == contents
    with pytest.raises(OSError):
        db.get_item_backpack('pack')
    restarted = Database(path, Mock())
    assert restarted.get_item_backpack('pack')['contents'] == contents
    assert restarted.recovery.entries() == []


def test_failed_recovery_journal_never_replaces_the_primary_snapshot(tmp_path, monkeypatch):
    db = Database(tmp_path / 'backpacks.db', Mock())
    original = {'0': {'type': 'minecraft:diamond', 'amount': 9}}
    db.save_item_backpack('pack', 'large', 90, 'owner', 'Owner', original)
    monkeypatch.setattr(db.recovery, 'put', Mock(side_effect=OSError('disk full')))
    with pytest.raises(OSError):
        db.save_item_backpack('pack', 'large', 90, 'owner', 'Owner', {})
    assert db.get_item_backpack('pack')['contents'] == original


def test_bad_saved_item_blocks_open_without_overwriting_storage(monkeypatch):
    plugin = SimpleNamespace(db=Mock(), logger=Mock(), cfg=SimpleNamespace(
        item_backpacks={'large': {'size': 90}}, rules={}, virtual_stacks={}))
    plugin.db.get_item_backpack.return_value = {'contents': {'0': {'type': 'minecraft:paper',
        'nbt': {'_type': 'unknown', 'value': 'corrupt'}}}}
    manager = BackpackManager(plugin)
    player = SimpleNamespace(unique_id='owner', name='Owner', send_message=Mock())
    menu = Mock()
    monkeypatch.setattr('ninjos_backpacks.manager.Menu', menu)
    manager.open_item_backpack(player, 'pack', 'large')
    menu.assert_not_called()
    plugin.db.save_item_backpack.assert_not_called()
    assert manager.contents_caches == {}


def test_old_delayed_save_cannot_overwrite_a_new_session():
    plugin = SimpleNamespace(db=Mock(), cfg=SimpleNamespace(), logger=Mock())
    manager = BackpackManager(plugin)
    manager.active_menus['player'] = object()
    manager.contents_caches['player'] = {'0': {'type': 'minecraft:diamond', 'amount': 9}}
    manager.save_backpack_contents('old', 'small', 1, 'player', 'Player', object(), False, 'player')
    plugin.db.save_item_backpack.assert_not_called()


def test_closed_session_cannot_write_an_empty_snapshot_over_shared_storage():
    plugin = SimpleNamespace(db=Mock(), cfg=SimpleNamespace(), logger=Mock())
    manager = BackpackManager(plugin)
    menu = SimpleNamespace(inventory=SimpleNamespace(get_item=lambda _: None))
    # The old server's callback runs after its cache was released. Another
    # server may already have saved newer contents under this same storage ID.
    manager.save_backpack_contents('SharedOwner_small', 'small', 27,
                                   'owner', 'SharedOwner', menu, False, 'owner')
    plugin.db.save_item_backpack.assert_not_called()


def test_virtual_cleanup_never_removes_unmarked_custom_lore():
    plugin = SimpleNamespace(db=Mock(), logger=Mock(), cfg=SimpleNamespace(virtual_stacks={}))
    manager = BackpackManager(plugin)
    item = Item()
    item.nbt = CompoundTag({'display': CompoundTag({'Lore': ListTag([
        StringTag('§eStored Amount: custom Essentials lore'), StringTag('Keep this line')])})})
    before = serializer.nbt_to_dict(item.nbt)
    inv = SimpleNamespace(size=1, get_item=lambda _: item, set_item=Mock())
    manager.clean_player_inventory(SimpleNamespace(inventory=inv))
    assert serializer.nbt_to_dict(item.nbt) == before
    inv.set_item.assert_not_called()


def test_virtual_display_restores_original_lore_even_when_text_matches_counter():
    plugin = SimpleNamespace(db=Mock(), logger=Mock(), cfg=SimpleNamespace(virtual_stacks={}))
    manager = BackpackManager(plugin)
    item = Item()
    item.nbt = CompoundTag({'display': CompoundTag({'Lore': ListTag([
        StringTag('§7Stored Amount: §e123'), StringTag('§dEssentials custom owner')])})})
    record = serializer.serialize_item(item)
    visual = manager.create_visual_item(record)
    assert VISUAL_MARKER in visual.nbt
    assert item_identity(visual) == item_identity(item)
    inv = SimpleNamespace(size=1, get_item=lambda _: visual, set_item=Mock())
    manager.clean_player_inventory(SimpleNamespace(inventory=inv))
    assert serializer.nbt_to_dict(visual.nbt) == serializer.nbt_to_dict(item.nbt)


def test_virtual_consolidation_never_merges_different_potion_data():
    manager = BackpackManager(SimpleNamespace(db=Mock(), logger=Mock(), cfg=SimpleNamespace()))
    contents = {'0': {'type': 'minecraft:potion', 'amount': 1, 'data': 13},
                '1': {'type': 'minecraft:potion', 'amount': 1, 'data': 14}}
    assert len(manager.consolidate_cache(contents, 900)) == 2


def test_empty_air_destination_does_not_reject_virtual_withdrawal():
    item = Item('minecraft:diamond')
    assert not different_storage_items(item, None)
    assert not different_storage_items(item, Item('minecraft:air'))
    assert different_storage_items(item, Item('minecraft:emerald'))
