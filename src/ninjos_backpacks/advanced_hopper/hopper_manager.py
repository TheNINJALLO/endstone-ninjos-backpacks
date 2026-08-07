import math
import uuid
import traceback
import datetime
from typing import Dict, Any, Optional, List

from endstone import Player, ColorFormat
from endstone.inventory import ItemStack
from endstone.event import event_handler, PlayerInteractEvent, BlockPlaceEvent, BlockBreakEvent

from ninjos_backpacks.serializer import serialize_item, deserialize_item, nbt_to_dict
from ninjos_backpacks.advanced_hopper.hopper_config import HopperConfig
from ninjos_backpacks.advanced_hopper.hopper_data import HopperDatabase

def normalize_block_type(block_type: str) -> str:
    if not block_type:
        return ""
    return block_type.lower().replace("minecraft:", "")

class BackpackStorageAdapter:
    def __init__(self, plugin):
        self.plugin = plugin

    def is_block_container(self, dimension: str, x: int, y: int, z: int) -> bool:
        block_key = f"block:{dimension}:{x}:{y}:{z}"
        data = self.plugin.db.get_item_backpack(block_key)
        return data is not None

    def is_storage_block(self, dimension: str, x: int, y: int, z: int) -> bool:
        return self.is_block_container(dimension, x, y, z)

    def get_block_container_storage_id_at(self, dimension: str, x: int, y: int, z: int) -> Optional[str]:
        if self.is_block_container(dimension, x, y, z):
            return f"block:{dimension}:{x}:{y}:{z}"
        return None

    def get_storage_id_at(self, dimension: str, x: int, y: int, z: int) -> Optional[str]:
        return self.get_block_container_storage_id_at(dimension, x, y, z)

    def is_item_backpack_storage(self, storage_id: str) -> bool:
        if storage_id.startswith("block:"):
            return False
        data = self.plugin.db.get_item_backpack(storage_id)
        return data is not None

    def supports_virtual_stacks(self, storage_id: str) -> bool:
        is_block = storage_id.startswith("block:")
        cfg = getattr(self.plugin.cfg, "virtual_stacks", {})
        if not cfg.get("enabled", True):
            return False
        if is_block:
            return cfg.get("apply_to_block_containers", True)
        else:
            return cfg.get("apply_to_item_backpacks", False)

    def player_can_access_storage(self, player, storage_id: str) -> bool:
        data = self.plugin.db.get_item_backpack(storage_id)
        if not data:
            return False
        owner_uuid = data.get("owner_uuid")
        if not owner_uuid:
            return True
        return owner_uuid == str(player.unique_id) or player.is_op

    def get_inventory_for_storage(self, storage_id: str) -> Optional[tuple]:
        active_player_uuid = self.plugin.manager.active_item_sessions.get(storage_id)
        if active_player_uuid:
            try:
                active_player = self.plugin.server.get_player(uuid.UUID(active_player_uuid))
                if active_player is not None:
                    from endstone_inventoryui.manager.player_manager import find_session as find_ui_session
                    ui_session = find_ui_session(active_player)
                    if ui_session is not None and hasattr(ui_session, 'menu') and ui_session.menu:
                        size = ui_session.menu.inventory.size
                        return (ui_session.menu.inventory, size, True, active_player_uuid)
            except Exception:
                pass

        data = self.plugin.db.get_item_backpack(storage_id)
        if data:
            return (data.get("contents") or {}, data.get("size", 27), False, None)
        return None

    def save_inventory_for_storage(self, storage_id: str, inv_or_dict, is_active: bool, size: int):
        if is_active:
            active_player_uuid = self.plugin.manager.active_item_sessions.get(storage_id)
            if active_player_uuid:
                try:
                    active_player = self.plugin.server.get_player(uuid.UUID(active_player_uuid))
                    if active_player is not None:
                        from endstone_inventoryui.manager.player_manager import find_session as find_ui_session
                        ui_session = find_ui_session(active_player)
                        if ui_session is not None and hasattr(ui_session, 'menu') and ui_session.menu:
                            data = self.plugin.db.get_item_backpack(storage_id)
                            tier = data.get("type", "vault_small") if data else "vault_small"
                            owner_uuid = data.get("owner_uuid") if data else active_player_uuid
                            owner_name = data.get("owner_name") if data else active_player.name
                            use_pagination = size > 54
                            self.plugin.manager.save_backpack_contents(
                                storage_id, tier, size, owner_uuid, owner_name, ui_session.menu, use_pagination, active_player_uuid
                            )
                except Exception:
                    pass
        else:
            data = self.plugin.db.get_item_backpack(storage_id)
            if data:
                self.plugin.db.save_item_backpack(
                    storage_id,
                    data.get("type", "vault_small"),
                    size,
                    data.get("owner_uuid"),
                    data.get("owner_name"),
                    inv_or_dict
                )

    def can_insert_item(self, storage_id: str, item: ItemStack, amount: int) -> bool:
        return self.get_available_space(storage_id, item) >= amount

    def nbt_matches(self, item1: ItemStack, item2: ItemStack) -> bool:
        t1 = item1.nbt
        t2 = item2.nbt
        if t1 is None and t2 is None:
            return True
            
        # Compare display names
        name1 = item1.item_meta.display_name if item1.item_meta else ""
        name2 = item2.item_meta.display_name if item2.item_meta else ""
        if name1 != name2:
            return False

        # Compare lore (ignoring virtual stack lore)
        lore1 = [line for line in item1.item_meta.lore if "Stored Amount:" not in line] if (item1.item_meta and item1.item_meta.has_lore) else []
        lore2 = [line for line in item2.item_meta.lore if "Stored Amount:" not in line] if (item2.item_meta and item2.item_meta.has_lore) else []
        if lore1 != lore2:
            return False

        # Enforce strict NBT matching for all items (stackable and unstackable)
        if (t1 is None) != (t2 is None):
            return False
        if t1 and t2:
            try:
                if nbt_to_dict(t1) != nbt_to_dict(t2):
                    return False
            except Exception:
                return False

        return True

    def get_actual_amount_in_slot(self, storage_id: str, slot: int) -> int:
        active_player_uuid = self.plugin.manager.active_item_sessions.get(storage_id)
        if active_player_uuid and active_player_uuid in self.plugin.manager.contents_caches:
            cache = self.plugin.manager.contents_caches[active_player_uuid]
            curr_page = self.plugin.manager.active_pages.get(active_player_uuid, 0)
            db_slot_str = str(curr_page * 45 + slot)
            if db_slot_str in cache:
                return cache[db_slot_str].get("amount", 1)
        data = self.plugin.db.get_item_backpack(storage_id)
        if data:
            contents = data.get("contents") or {}
            db_slot_str = str(slot)
            if db_slot_str in contents:
                return contents[db_slot_str].get("amount", 1)
        return 0

    def get_available_space(self, storage_id: str, item: ItemStack) -> int:
        res = self.get_inventory_for_storage(storage_id)
        if not res:
            return 0
        inv_or_dict, size, is_active, _ = res
        
        supports_vs = self.supports_virtual_stacks(storage_id)
        cfg = getattr(self.plugin.cfg, "virtual_stacks", {}) if supports_vs else {}
        max_amount = cfg.get("max_amount_per_slot", 900) if supports_vs else 64
        allow_unstackable = cfg.get("allow_virtual_stacking_of_unstackables", False) if supports_vs else False
        
        is_stackable = item.max_stack_size > 1
        can_vs = supports_vs and (is_stackable or allow_unstackable)
        
        space = 0
        if is_active: # Inventory object
            for slot in range(size):
                existing = inv_or_dict.get_item(slot)
                if not existing or str(existing.type) == "minecraft:air":
                    space += max_amount if can_vs else (item.max_stack_size if is_stackable else 1)
                elif existing.type == item.type and self.nbt_matches(existing, item):
                    if can_vs:
                        actual_qty = self.get_actual_amount_in_slot(storage_id, slot)
                        space += max(0, max_amount - actual_qty)
                    else:
                        space += max(0, existing.max_stack_size - existing.amount)
        else: # contents dictionary
            for slot in range(size):
                slot_str = str(slot)
                if slot_str in inv_or_dict:
                    existing = deserialize_item(inv_or_dict[slot_str])
                    if existing and existing.type == item.type and self.nbt_matches(existing, item):
                        if can_vs:
                            actual_qty = inv_or_dict[slot_str].get("amount", 1)
                            space += max(0, max_amount - actual_qty)
                        else:
                            space += max(0, 64 - existing.amount)
                else:
                    space += max_amount if can_vs else 64
        return space

    def insert_item(self, storage_id: str, item: ItemStack, amount: int) -> int:
        active_player_uuid = self.plugin.manager.active_item_sessions.get(storage_id)
        is_active = False
        ui_session = None
        
        if active_player_uuid:
            try:
                active_player = self.plugin.server.get_player(uuid.UUID(active_player_uuid))
                if active_player is not None:
                    from endstone_inventoryui.manager.player_manager import find_session as find_ui_session
                    ui_session = find_ui_session(active_player)
                    if ui_session is not None and hasattr(ui_session, 'menu') and ui_session.menu:
                        is_active = True
            except Exception:
                pass

        if is_active:
            contents = self.plugin.manager.contents_caches.get(active_player_uuid, {})
            data = self.plugin.db.get_item_backpack(storage_id)
            size = data.get("size", 27) if data else 27
        else:
            data = self.plugin.db.get_item_backpack(storage_id)
            if not data:
                return 0
            contents = data.get("contents") or {}
            size = data.get("size", 27)

        supports_vs = self.supports_virtual_stacks(storage_id)
        cfg = getattr(self.plugin.cfg, "virtual_stacks", {}) if supports_vs else {}
        max_amount = cfg.get("max_amount_per_slot", 900) if supports_vs else 64
        allow_unstackable = cfg.get("allow_virtual_stacking_of_unstackables", False) if supports_vs else False
        
        is_stackable = item.max_stack_size > 1
        can_vs = supports_vs and (is_stackable or allow_unstackable)

        added = 0

        for slot in range(size):
            slot_str = str(slot)
            if slot_str in contents:
                existing = deserialize_item(contents[slot_str])
                if existing and existing.type == item.type and self.nbt_matches(existing, item):
                    current_qty = contents[slot_str].get("amount", existing.amount)
                    max_limit = max_amount if can_vs else existing.max_stack_size
                    space = max_limit - current_qty
                    if space > 0:
                        transfer = min(space, amount - added)
                        contents[slot_str]["amount"] = current_qty + transfer
                        added += transfer
                        if added >= amount:
                            break

        if added < amount:
            for slot in range(size):
                slot_str = str(slot)
                if slot_str not in contents:
                    max_limit = max_amount if can_vs else item.max_stack_size
                    transfer = min(max_limit, amount - added)
                    serialized = serialize_item(item)
                    if serialized:
                        serialized["amount"] = transfer
                        contents[slot_str] = serialized
                        added += transfer
                        if added >= amount:
                            break

        if is_active:
            self.plugin.manager.contents_caches[active_player_uuid] = contents
            curr_page = self.plugin.manager.active_pages.get(active_player_uuid, 0)
            ui_menu = ui_session.menu
            for i in range(45):
                db_slot = curr_page * 45 + i
                db_slot_str = str(db_slot)
                if db_slot < size:
                    if db_slot_str in contents:
                        if supports_vs:
                            ui_menu.inventory.set_item(i, self.plugin.manager.create_visual_item(contents[db_slot_str]))
                        else:
                            ui_menu.inventory.set_item(i, deserialize_item(contents[db_slot_str]))
                    else:
                        ui_menu.inventory.set_item(i, None)
            
            self.save_inventory_for_storage(storage_id, contents, True, size)
        else:
            self.save_inventory_for_storage(storage_id, contents, False, size)

        return added

    def is_full(self, storage_id: str) -> bool:
        res = self.get_inventory_for_storage(storage_id)
        if not res:
            return True
        inv_or_dict, size, is_active, _ = res
        
        supports_vs = self.supports_virtual_stacks(storage_id)
        cfg = getattr(self.plugin.cfg, "virtual_stacks", {}) if supports_vs else {}
        max_amount = cfg.get("max_amount_per_slot", 900) if supports_vs else 64
        
        for slot in range(size):
            actual_qty = self.get_actual_amount_in_slot(storage_id, slot)
            if actual_qty < max_amount:
                return False
        return True

    def is_valid_storage(self, storage_id: str) -> bool:
        if not storage_id.startswith("block:"):
            return False
        parts = storage_id.split(":")
        if len(parts) < 5:
            return False
        return self.is_block_container(parts[1], int(parts[2]), int(parts[3]), int(parts[4]))

class HopperManager:
    def __init__(self, plugin):
        self.plugin = plugin
        self.logger = plugin.logger
        self.cfg = HopperConfig(plugin.cfg)
        self.db = HopperDatabase(plugin.db.db_path, plugin.logger)
        self.adapter = BackpackStorageAdapter(plugin)
        
        # Player linking states
        # Key: player_uuid, Value: dict containing source_hopper coordinates
        self.linking_states: Dict[str, Dict[str, Any]] = {}
        self.last_close_times: Dict[str, float] = {}
        self.last_open_times: Dict[str, float] = {}

    def perform_link(self, player: Player, source_key: str, dest_key: str):
        hopper_data = self.db.get_hopper(source_key)
        if not hopper_data:
            player.send_message(f"{ColorFormat.RED}The selected source hopper is no longer registered.")
            return

        if self.cfg.ownership_enabled and hopper_data.get("owner_uuid") != str(player.unique_id) and not player.is_op:
            player.send_message(f"{ColorFormat.RED}You do not own this hopper.")
            return

        if dest_key == source_key or self.db.get_hopper(dest_key) is not None:
            player.send_message(f"{ColorFormat.RED}Linking failed: Destination cannot be a hopper.")
            return

        if not dest_key.startswith("block:"):
            player.send_message(f"{ColorFormat.RED}Linking failed: Destination must be a placed block-container storage block.")
            return

        dest_parts = dest_key.split(":")
        if len(dest_parts) < 5:
            player.send_message(f"{ColorFormat.RED}Linking failed: Invalid destination block coordinates.")
            return

        dest_dim = dest_parts[1]
        try:
            dx, dy, dz = int(dest_parts[2]), int(dest_parts[3]), int(dest_parts[4])
        except ValueError:
            player.send_message(f"{ColorFormat.RED}Linking failed: Invalid destination block coordinates.")
            return

        if not self.adapter.is_block_container(dest_dim, dx, dy, dz):
            player.send_message(f"{ColorFormat.RED}Linking failed: Destination block is not a registered block-container storage vault.")
            return

        dest_data = self.plugin.db.get_item_backpack(dest_key)
        if not dest_data:
            player.send_message(f"{ColorFormat.RED}Linking failed: Destination block data could not be retrieved.")
            return

        dest_owner_uuid = dest_data.get("owner_uuid")
        if self.cfg.prevent_linking_to_other_players_storage:
            if dest_owner_uuid and dest_owner_uuid != str(player.unique_id) and not player.is_op:
                player.send_message(f"{ColorFormat.RED}Linking failed: You do not have access to this storage container.")
                return

        source_parts = source_key.split(":")
        source_dim = source_parts[1]
        if self.cfg.require_same_dimension and source_dim != dest_dim:
            player.send_message(f"{ColorFormat.RED}Linking failed: Source and destination must be in the same dimension.")
            return

        try:
            sx, sy, sz = int(source_parts[2]), int(source_parts[3]), int(source_parts[4])
            dist = math.sqrt((sx - dx)**2 + (sy - dy)**2 + (sz - dz)**2)
            
            is_admin_bypass = self.cfg.admin_bypass_link_distance and player.is_op
            if dist > self.cfg.max_link_distance and not is_admin_bypass:
                player.send_message(f"{ColorFormat.RED}Linking failed: Destination is too far away ({dist:.1f} blocks, max allowed: {self.cfg.max_link_distance} blocks).")
                return
        except Exception as e:
            player.send_message(f"{ColorFormat.RED}Linking failed: Coordinates parsing error: {e}")
            return

        hopper_data["linked_storage"] = {
            "type": "ninjos_backpacks_block_container",
            "dimension": dest_dim,
            "x": dx,
            "y": dy,
            "z": dz,
            "storage_id": dest_key
        }
        self.db.save_hopper(source_key, hopper_data)
        player.send_message(f"{ColorFormat.GREEN}✓ Successfully linked hopper to block storage at {dx}, {dy}, {dz}!")

    @event_handler
    def on_block_place(self, event: BlockPlaceEvent) -> None:
        try:
            player = event.player
            if not player:
                return

            placed_block = event.block
            if hasattr(event, 'block_placed_state') and event.block_placed_state:
                placed_block = event.block_placed_state

            if not placed_block:
                return

            norm_type = normalize_block_type(str(placed_block.type))
            if norm_type != normalize_block_type(self.cfg.block_id):
                return

            player_uuid = str(player.unique_id)
            block_key = f"block:{placed_block.location.dimension.name}:{int(placed_block.location.x)}:{int(placed_block.location.y)}:{int(placed_block.location.z)}"

            # Safety limits: Per-chunk limit check
            chunk_x = int(placed_block.location.x) >> 4
            chunk_z = int(placed_block.location.z) >> 4
            chunk_count = self.db.count_hoppers_in_chunk(placed_block.location.dimension.name, chunk_x, chunk_z)
            if chunk_count >= self.cfg.max_hoppers_per_chunk and not player.is_op:
                player.send_message(f"{ColorFormat.RED}You cannot place more than {self.cfg.max_hoppers_per_chunk} advanced hoppers in a single chunk!")
                event.is_cancelled = True
                return

            # Safety limits: Per-player limit check
            player_count = self.db.count_hoppers_by_owner(player_uuid)
            if player_count >= self.cfg.max_hoppers_per_player and not player.is_op:
                player.send_message(f"{ColorFormat.RED}You have reached your maximum limit of {self.cfg.max_hoppers_per_player} advanced hoppers!")
                event.is_cancelled = True
                return

            # Register hopper block
            hopper_data = {
                "owner_uuid": player_uuid,
                "owner_name": player.name,
                "enabled": self.cfg.default_enabled,
                "mode": self.cfg.default_mode,
                "horizontal_range": self.cfg.default_horizontal_range,
                "vertical_up": self.cfg.default_vertical_up,
                "vertical_down": self.cfg.default_vertical_down,
                "max_items_moved_per_scan": self.cfg.default_max_items_moved,
                "max_stacks_moved_per_scan": self.cfg.default_max_stacks_moved,
                "linked_storage": None,
                "filters": {},
                "stats": {"items_moved_total": 0}
            }
            self.db.save_hopper(block_key, hopper_data)
            player.send_message(f"{ColorFormat.GREEN}Placed Advanced Hopper. Use '/hopper link' to connect it to a storage block.")
            self.logger.info(f"[Hopper] Registered new hopper at {block_key} for owner {player.name}.")
        except Exception as e:
            self.logger.error(f"[Hopper ERROR] Exception in on_block_place: {e}\n{traceback.format_exc()}")

    @event_handler
    def on_player_interact(self, event: PlayerInteractEvent) -> None:
        try:
            player = event.player
            if not player:
                return

            # Check if player already has an active inventory UI session open
            try:
                from endstone_inventoryui.manager.player_manager import find_session as find_ui_session
                if find_ui_session(player):
                    return
            except Exception:
                pass

            action = event.action
            block = event.block
            if block is None:
                return
            
            player_uuid = str(player.unique_id)

            # Check close and open cooldowns to prevent residual interact reopen loops
            import time
            last_open = self.last_open_times.get(player_uuid, 0.0)
            if time.time() - last_open < 1.0:
                return

            last_close = self.last_close_times.get(player_uuid, 0.0)
            if time.time() - last_close < 1.0:
                return
            block_key = f"block:{block.location.dimension.name}:{int(block.location.x)}:{int(block.location.y)}:{int(block.location.z)}"
            norm_type = normalize_block_type(str(block.type))
            config_hopper_type = normalize_block_type(self.cfg.block_id)


            # 1. Handle linking state clicks
            if player_uuid in self.linking_states:
                state = self.linking_states[player_uuid]
                if not state.get("source_hopper"):
                    # First click: must be a ninjos:hopper!
                    if norm_type == normalize_block_type(self.cfg.block_id):
                        state["source_hopper"] = block_key
                        event.is_cancelled = True
                        player.send_message(f"{ColorFormat.GOLD}Source hopper selected: {block_key}. Now right-click the destination backpack/block-container storage block to link them.")
                    else:
                        player.send_message(f"{ColorFormat.RED}Invalid block! You must right-click a {self.cfg.block_id} to start linking.")
                        self.linking_states.pop(player_uuid, None)
                        event.is_cancelled = True
                    return
                else:
                    # Second click: must be a valid backpack block-container!
                    source_key = state["source_hopper"]
                    dest_key = block_key
                    if dest_key == source_key:
                        # Ignore rapid clicking the same block
                        event.is_cancelled = True
                        return

                    event.is_cancelled = True
                    self.perform_link(player, source_key, dest_key)
                    self.linking_states.pop(player_uuid, None)
                    return

            # 2. Handle standard right-click to open configuration UI
            if norm_type == normalize_block_type(self.cfg.block_id):
                if player.is_sneaking:
                    return

                event.is_cancelled = True
                
                hopper_data = self.db.get_hopper(block_key)
                if not hopper_data:
                    # Self-heal register if somehow placed but not in DB
                    hopper_data = {
                        "owner_uuid": player_uuid,
                        "owner_name": player.name,
                        "enabled": self.cfg.default_enabled,
                        "mode": self.cfg.default_mode,
                        "horizontal_range": self.cfg.default_horizontal_range,
                        "vertical_up": self.cfg.default_vertical_up,
                        "vertical_down": self.cfg.default_vertical_down,
                        "max_items_moved_per_scan": self.cfg.default_max_items_moved,
                        "max_stacks_moved_per_scan": self.cfg.default_max_stacks_moved,
                        "linked_storage": None,
                        "filters": {},
                        "stats": {"items_moved_total": 0}
                    }
                    self.db.save_hopper(block_key, hopper_data)

                # Permission check for UI configuration
                if self.cfg.ownership_enabled and hopper_data.get("owner_uuid") != player_uuid and not player.is_op:
                    player.send_message(f"{ColorFormat.RED}You do not have permission to configure this hopper.")
                    return

                # Open the UI menu
                self.last_open_times[player_uuid] = time.time()
                from ninjos_backpacks.advanced_hopper.hopper_ui import HopperUI
                HopperUI.open_menu(player, block_key, self)
        except Exception as e:
            self.logger.error(f"[Hopper ERROR] Exception in on_player_interact: {e}\n{traceback.format_exc()}")

    @event_handler
    def on_block_break(self, event: BlockBreakEvent) -> None:
        try:
            player = event.player
            block = event.block
            if not block:
                return

            norm_type = normalize_block_type(str(block.type))
            if norm_type != normalize_block_type(self.cfg.block_id):
                return

            block_key = f"block:{block.location.dimension.name}:{int(block.location.x)}:{int(block.location.y)}:{int(block.location.z)}"
            
            # Check ownership before breaking (if ownership protection is enabled)
            hopper_data = self.db.get_hopper(block_key)
            if hopper_data:
                if self.cfg.ownership_enabled and player and not player.is_op:
                    if hopper_data.get("owner_uuid") != str(player.unique_id):
                        player.send_message(f"{ColorFormat.RED}You do not own this hopper!")
                        event.is_cancelled = True
                        return

                self.db.delete_hopper(block_key)
                if player:
                    player.send_message(f"{ColorFormat.YELLOW}Advanced Hopper broken and unlinked successfully.")
                self.logger.info(f"[Hopper] Deleted hopper at {block_key} (broken).")
        except Exception as e:
            self.logger.error(f"[Hopper ERROR] Exception in on_block_break: {e}\n{traceback.format_exc()}")
