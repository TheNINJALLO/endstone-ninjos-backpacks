import re
import traceback
import uuid
import datetime
import math
from typing import Dict, Any, Optional, List, Tuple

from endstone import Player, ColorFormat
from endstone.inventory import ItemStack
from endstone_inventoryui import Menu, MenuType, MenuTransaction, MenuTransactionResult

from ninjos_backpacks.serializer import serialize_item, deserialize_item, get_backpack_id_from_item, CompoundTag, ListTag, StringTag

class BackpackManager:
    def __init__(self, plugin):
        self.plugin = plugin
        self.db = plugin.db
        self.config = plugin.cfg
        self.logger = plugin.logger

        # Active item sessions tracking
        # key: backpack_id (player name), value: player_uuid
        self.active_item_sessions: Dict[str, str] = {}

        # Tracking if a session opened successfully to prevent empty content overwriting
        # key: player_uuid, value: bool
        self.session_opened_successfully: Dict[str, bool] = {}

        # Pagination state
        # key: player_uuid, value: current page (0-indexed)
        self.active_pages: Dict[str, int] = {}
        # key: player_uuid, value: contents cache dict
        self.contents_caches: Dict[str, dict] = {}
        # Track pending page changes to prevent double-clicks/multi-action triggers
        self.pending_page_changes = set()

    def supports_virtual_stacks(self, storage_id: str) -> bool:
        """Returns True if the storage ID supports virtual stacks under active config settings."""
        is_block = storage_id.startswith("block:")
        cfg = getattr(self.config, "virtual_stacks", {})
        if not cfg.get("enabled", True):
            return False
        if is_block:
            return cfg.get("apply_to_block_containers", True)
        else:
            return cfg.get("apply_to_item_backpacks", False)

    def create_visual_item(self, item_data: dict) -> Optional[ItemStack]:
        """Creates a visual ItemStack from item data with virtual stack lore and count 1."""
        item = deserialize_item(item_data)
        if not item:
            return None

        cfg = getattr(self.config, "virtual_stacks", {})
        if not cfg.get("enabled", True):
            return item

        show_lore = cfg.get("show_virtual_amount_in_lore", True)
        display_amount = cfg.get("display_stack_amount", 1)
        
        item.amount = display_amount
        if show_lore:
            try:
                tag = item.nbt
                if tag is None:
                    tag = CompoundTag()
                
                if "display" not in tag:
                    tag["display"] = CompoundTag()
                display_tag = tag["display"]
                if not isinstance(display_tag, CompoundTag):
                    display_tag = CompoundTag()
                    tag["display"] = display_tag
                
                if "Lore" not in display_tag:
                    display_tag["Lore"] = ListTag()
                lore_tag = display_tag["Lore"]
                if not isinstance(lore_tag, ListTag):
                    lore_tag = ListTag()
                    display_tag["Lore"] = lore_tag
                
                existing_lore_lines = []
                for i in range(lore_tag.size()):
                    child = lore_tag[i]
                    if isinstance(child, StringTag):
                        existing_lore_lines.append(child.value)
                    elif hasattr(child, "value"):
                        existing_lore_lines.append(str(child.value))
                    else:
                        existing_lore_lines.append(str(child))
                
                new_lines = [line for line in existing_lore_lines if not line.startswith("§7Stored Amount:")]
                new_lines.append(f"§7Stored Amount: §e{item_data.get('amount', 1)}")
                
                new_lore_tag = ListTag()
                for line in new_lines:
                    new_lore_tag.append(StringTag(line))
                display_tag["Lore"] = new_lore_tag
                
                item.nbt = tag
            except Exception as e:
                self.logger.error(f"Error setting visual lore via NBT: {e}")
                # Fallback to standard meta just in case
                meta = item.item_meta
                if meta:
                    lore = meta.lore if meta.has_lore else []
                    # Clear existing amount info to avoid duplication
                    lore = [line for line in lore if not line.startswith("§7Stored Amount:")]
                    lore.append(f"§7Stored Amount: §e{item_data.get('amount', 1)}")
                    meta.lore = lore
                    item.set_item_meta(meta)
        return item

    def items_are_equal(self, item1: Optional[ItemStack], item2: Optional[ItemStack]) -> bool:
        if item1 is None and item2 is None:
            return True
        if item1 is None or item2 is None:
            return False
        if str(item1.type) != str(item2.type):
            return False
        if item1.amount != item2.amount:
            return False
        
        m1 = item1.item_meta
        m2 = item2.item_meta
        if (m1 is None) != (m2 is None):
            return False
        if m1 and m2:
            if m1.display_name != m2.display_name:
                return False
            lore1 = m1.lore if m1.has_lore else []
            lore2 = m2.lore if m2.has_lore else []
            if lore1 != lore2:
                return False

        t1 = item1.nbt
        t2 = item2.nbt
        if (t1 is None) != (t2 is None):
            return False
        if t1 and t2:
            from ninjos_backpacks.serializer import nbt_to_dict
            try:
                if nbt_to_dict(t1) != nbt_to_dict(t2):
                    return False
            except Exception:
                return False
        return True

    def consolidate_cache(self, cache: dict, max_amount: int) -> dict:
        """Consolidates the cache slots: stacks items of the same type/name/NBT into the first possible slots up to max_amount, and places new items logically."""
        ordered_items = []
        for slot_str in sorted(cache.keys(), key=lambda x: int(x)):
            item_data = cache[slot_str]
            if item_data and item_data.get("amount", 0) > 0:
                ordered_items.append(item_data)
        
        consolidated = []
        for item in ordered_items:
            qty_to_distribute = item.get("amount", 0)
            if qty_to_distribute <= 0:
                continue
            
            # Find any existing consolidated stacks that are not full
            for cons_item in consolidated:
                if cons_item.get("type") == item.get("type") and cons_item.get("nbt") == item.get("nbt"):
                    current = cons_item.get("amount", 0)
                    space = max_amount - current
                    if space > 0:
                        add = min(qty_to_distribute, space)
                        cons_item["amount"] = current + add
                        qty_to_distribute -= add
                        if qty_to_distribute <= 0:
                            break
            
            # If there's still quantity left, create new stacks of max_amount
            while qty_to_distribute > 0:
                chunk = min(qty_to_distribute, max_amount)
                new_item = item.copy()
                new_item["amount"] = chunk
                consolidated.append(new_item)
                qty_to_distribute -= chunk
        
        new_cache = {}
        for idx, item in enumerate(consolidated):
            new_cache[str(idx)] = item
        return new_cache

    def clean_player_inventory(self, player: Player) -> None:
        try:
            inv = player.inventory
            for i in range(inv.size):
                item = inv.get_item(i)
                if item:
                    tag = item.nbt
                    if tag is not None and "display" in tag:
                        display_tag = tag["display"]
                        if isinstance(display_tag, CompoundTag) and "Lore" in display_tag:
                            lore_tag = display_tag["Lore"]
                            if isinstance(lore_tag, ListTag):
                                existing_lore_lines = []
                                for idx in range(lore_tag.size()):
                                    child = lore_tag[idx]
                                    if isinstance(child, StringTag):
                                        existing_lore_lines.append(child.value)
                                    elif hasattr(child, "value"):
                                        existing_lore_lines.append(str(child.value))
                                    else:
                                        existing_lore_lines.append(str(child))
                                
                                is_visual = any("Stored Amount:" in line for line in existing_lore_lines)
                                if is_visual:
                                    new_lines = [line for line in existing_lore_lines if "Stored Amount:" not in line]
                                    new_lore_tag = ListTag()
                                    for line in new_lines:
                                        new_lore_tag.append(StringTag(line))
                                    display_tag["Lore"] = new_lore_tag
                                    item.nbt = tag
                                    inv.set_item(i, item)
        except Exception as e:
            self.logger.error(f"Error cleaning player inventory: {e}")

    def reconcile_virtual_stacks(self, player: Player, menu: Menu, storage_id: str, scheduled_page: int = -1) -> None:
        """Synchronizes GUI menu inventory slots with the in-memory virtual cache and player's inventory."""
        player_uuid = str(player.unique_id)
        if player_uuid not in self.contents_caches:
            return

        curr_page = self.active_pages.get(player_uuid, 0)
        if scheduled_page != -1 and scheduled_page != curr_page:
            # Page changed since this check was scheduled! Abort to prevent corruption.
            return

        cache = self.contents_caches[player_uuid]
        
        # Load the size of the container
        data = self.db.get_item_backpack(storage_id)
        if not data:
            return
        size = data.get("size", 27)
        use_pagination = size > 54
        storage_slots = 45 if use_pagination else size

        cfg = getattr(self.config, "virtual_stacks", {})
        max_amount = cfg.get("max_amount_per_slot", 900)
        display_amount = cfg.get("display_stack_amount", 1)
        withdraw_stack = cfg.get("withdraw_stack_at_a_time", True)
        default_withdraw = cfg.get("default_withdraw_amount", 64)
        use_max_stack = cfg.get("use_item_max_stack_size_for_withdraw", True)
        allow_unstackable = cfg.get("allow_virtual_stacking_of_unstackables", False)

        for i in range(storage_slots):
            db_slot_str = str(curr_page * 45 + i)
            cache_item = cache.get(db_slot_str)
            gui_item = menu.inventory.get_item(i)

            # Case 1: Slot is empty in GUI but cache has item (withdrew)
            if gui_item is None or str(gui_item.type) == "minecraft:air":
                if cache_item is not None:
                    stored_qty = cache_item.get("amount", 1)
                    item_example = deserialize_item(cache_item)
                    if not item_example:
                        cache.pop(db_slot_str, None)
                        continue

                    # Decide max withdraw quantity
                    max_stack = item_example.max_stack_size if use_max_stack else default_withdraw
                    withdraw_qty = max_stack if withdraw_stack else 1
                    withdraw_qty = min(stored_qty, withdraw_qty)

                    # Subtract already received GUI stack
                    extra_qty = withdraw_qty - display_amount
                    if extra_qty > 0:
                        give_stack = deserialize_item(cache_item)
                        if give_stack:
                            give_stack.amount = extra_qty
                            leftovers = player.inventory.add_item(give_stack)
                            for leftover in leftovers.values():
                                if leftover.amount > 0:
                                    player.dimension.drop_item(player.location, leftover)
                    
                    new_qty = stored_qty - withdraw_qty
                    if new_qty <= 0:
                        cache.pop(db_slot_str, None)
                    else:
                        cache_item["amount"] = new_qty
                        visual_item = self.create_visual_item(cache_item)
                        if not self.items_are_equal(gui_item, visual_item):
                            menu.inventory.set_item(i, visual_item)

            # Case 2: Slot is not empty in GUI
            else:
                if cache_item is None:
                    # New item placed in slot
                    is_stackable = gui_item.max_stack_size > 1
                    if not is_stackable and not allow_unstackable:
                        cache[db_slot_str] = serialize_item(gui_item)
                    else:
                        cache[db_slot_str] = serialize_item(gui_item)
                        visual_item = self.create_visual_item(cache[db_slot_str])
                        if not self.items_are_equal(gui_item, visual_item):
                            menu.inventory.set_item(i, visual_item)
                else:
                    # Type changed/swapped or quantity changed
                    if str(gui_item.type) != cache_item.get("type"):
                        # Swapped items! Return the old virtual stack to the player
                        old_qty = cache_item.get("amount", 1)
                        old_item_example = deserialize_item(cache_item)
                        if old_item_example:
                            extra_old = old_qty - display_amount
                            if extra_old > 0:
                                old_item_example.amount = extra_old
                                leftovers = player.inventory.add_item(old_item_example)
                                for leftover in leftovers.values():
                                    if leftover.amount > 0:
                                        player.dimension.drop_item(player.location, leftover)

                        # Now save the new item in the cache
                        cache[db_slot_str] = serialize_item(gui_item)
                        is_stackable = gui_item.max_stack_size > 1
                        if is_stackable or allow_unstackable:
                            visual_item = self.create_visual_item(cache[db_slot_str])
                            if not self.items_are_equal(gui_item, visual_item):
                                menu.inventory.set_item(i, visual_item)
                    else:
                        # Quantity change or stack merge
                        delta = gui_item.amount - display_amount
                        if delta > 0:
                            # Deposited items
                            current_qty = cache_item.get("amount", 1)
                            new_qty = current_qty + delta
                            if new_qty > max_amount:
                                excess = new_qty - max_amount
                                give_back = ItemStack(str(gui_item.type), excess)
                                if gui_item.nbt:
                                    give_back.nbt = gui_item.nbt
                                leftovers = player.inventory.add_item(give_back)
                                for leftover in leftovers.values():
                                    if leftover.amount > 0:
                                        player.dimension.drop_item(player.location, leftover)
                                new_qty = max_amount
                            cache_item["amount"] = new_qty
                            visual_item = self.create_visual_item(cache_item)
                            if not self.items_are_equal(gui_item, visual_item):
                                menu.inventory.set_item(i, visual_item)
                        elif delta < 0:
                            # Split stack / single withdrawal
                            taken = -delta
                            current_qty = cache_item.get("amount", 1)
                            new_qty = current_qty - taken
                            if new_qty <= 0:
                                cache.pop(db_slot_str, None)
                                if not self.items_are_equal(gui_item, None):
                                    menu.inventory.set_item(i, None)
                            else:
                                cache_item["amount"] = new_qty
                                visual_item = self.create_visual_item(cache_item)
                                if not self.items_are_equal(gui_item, visual_item):
                                    menu.inventory.set_item(i, visual_item)
                        else:
                            # delta == 0. Verify visual item is identical (e.g. check lore)
                            visual_item = self.create_visual_item(cache_item)
                            if not self.items_are_equal(gui_item, visual_item):
                                menu.inventory.set_item(i, visual_item)
        
        # Consolidate cache and redraw GUI slots to match consolidated state
        cache = self.consolidate_cache(cache, max_amount)
        self.contents_caches[player_uuid] = cache

        for i in range(storage_slots):
            db_slot_str = str(curr_page * 45 + i)
            cache_item = cache.get(db_slot_str)
            visual_item = self.create_visual_item(cache_item) if cache_item else None
            
            gui_item = menu.inventory.get_item(i)
            if not self.items_are_equal(gui_item, visual_item):
                menu.inventory.set_item(i, visual_item)

        # Clean visual items from player inventory
        self.clean_player_inventory(player)

    def _create_item_safely(self, item_id: str, fallback_item_id: str) -> ItemStack:
        """Create an ItemStack, falling back to a vanilla ID if the custom ID is unregistered/unknown."""
        try:
            return ItemStack(item_id, 1)
        except Exception as e:
            self.logger.error(f"[Backpack WARNING] Failed to create item '{item_id}', falling back to '{fallback_item_id}': {e}")
            return ItemStack(fallback_item_id, 1)

    def get_configured_backpack_materials(self) -> List[str]:
        """Get all materials configured for item backpacks."""
        materials = []
        for bp in self.config.item_backpacks.values():
            if bp.get("enabled", True):
                materials.append(bp.get("material"))
        return materials

    def populate_menu_page(self, menu: Menu, page: int, total_pages: int, contents: dict, storage_id: str = "") -> None:
        """Clear and populate slots for the given page index."""
        # 1. Clear slots 0-44 (the storage slot region)
        for i in range(45):
            menu.inventory.set_item(i, None)

        # 2. Populate slots 0-44 with page items
        start_idx = page * 45
        supports_vs = self.supports_virtual_stacks(storage_id) if storage_id else False
        for i in range(45):
            db_slot_str = str(start_idx + i)
            if db_slot_str in contents:
                try:
                    if supports_vs:
                        item = self.create_visual_item(contents[db_slot_str])
                    else:
                        item = deserialize_item(contents[db_slot_str])
                    if item:
                        menu.inventory.set_item(i, item)
                except Exception as e:
                    self.logger.error(f"Failed to deserialize slot {db_slot_str}: {e}")

        # 3. Clear slots 45-53 (the navigation region)
        for slot in range(45, 54):
            menu.inventory.set_item(slot, None)

        # 4. Add previous page button (slot 45)
        if page > 0:
            prev_item_id = self.config.navigation.get("previous_item", "ninjos:back")
            prev_btn = self._create_item_safely(prev_item_id, "minecraft:arrow")
            meta = prev_btn.item_meta
            if meta:
                meta.display_name = "§e\ue066 Previous Page"
                meta.lore = [f"§7Go back to page {page}"]
                prev_btn.set_item_meta(meta)
            menu.inventory.set_item(45, prev_btn)

        # 5. Add page indicator (slot 49)
        page_item_id = self.config.navigation.get("page_item", "ninjos:page")
        page_indicator = self._create_item_safely(page_item_id, "minecraft:paper")
        meta = page_indicator.item_meta
        if meta:
            meta.display_name = f"§bPage {page + 1} of {total_pages}"
            meta.lore = [f"§7Showing items {start_idx + 1} - {start_idx + 45}"]
            page_indicator.set_item_meta(meta)
        menu.inventory.set_item(49, page_indicator)

        # 6. Add next page button (slot 53)
        if page < total_pages - 1:
            next_item_id = self.config.navigation.get("next_item", "ninjos:next")
            next_btn = self._create_item_safely(next_item_id, "minecraft:arrow")
            meta = next_btn.item_meta
            if meta:
                meta.display_name = "§eNext Page \ue068"
                meta.lore = [f"§7Go forward to page {page + 2}"]
                next_btn.set_item_meta(meta)
            menu.inventory.set_item(53, next_btn)

    def save_current_page_to_cache(self, menu: Menu, page: int, contents_cache: dict) -> None:
        """Reads storage slots 0-44 from the GUI and writes them into the cache dictionary."""
        start_idx = page * 45
        for i in range(45):
            db_slot_str = str(start_idx + i)
            item = menu.inventory.get_item(i)
            if item and str(item.type) != "minecraft:air":
                serialized = serialize_item(item)
                if serialized:
                    contents_cache[db_slot_str] = serialized
                else:
                    contents_cache.pop(db_slot_str, None)
            else:
                contents_cache.pop(db_slot_str, None)

    def open_item_backpack(self, player: Player, backpack_id: str, bp_type: str, item_stack: Optional[ItemStack] = None) -> None:
        """Open an item-based backpack for a player with pagination support."""
        try:
            player_uuid = str(player.unique_id)
            player_name = player.name

            # 1. Prevent concurrent open sessions
            if backpack_id in self.active_item_sessions:
                active_player_uuid = self.active_item_sessions[backpack_id]
                
                # Self-healing check: check if the lock holder is online and still has an active GUI session open
                from endstone_inventoryui.manager.player_manager import find_session as find_ui_session
                has_active_session = False
                try:
                    active_player = player.server.get_player(uuid.UUID(active_player_uuid))
                    if active_player is not None:
                        ui_session = find_ui_session(active_player)
                        if ui_session is not None:
                            has_active_session = True
                except Exception as se:
                    pass
                    
                if not has_active_session:
                    # Clear stale lock
                    self.active_item_sessions.pop(backpack_id, None)
                    self.session_opened_successfully.pop(active_player_uuid, None)
                else:
                    # Block double open
                    if active_player_uuid != player_uuid:
                        player.send_message(f"{ColorFormat.RED}This backpack is already open by another player!")
                        return
                    else:
                        player.send_message(f"{ColorFormat.RED}You already have this backpack open!")
                        return

            # 2. Retrieve config details
            bp_def = self.config.item_backpacks.get(bp_type)
            if not bp_def or not bp_def.get("enabled", True):
                player.send_message(f"{ColorFormat.RED}This backpack tier ({bp_type}) is disabled.")
                return

            size = bp_def.get("size", 27)
            display_name = bp_def.get("display_name", "Backpack")

            # Load from DB using combined key to separate inventory per tier type
            db_key = f"{backpack_id}_{bp_type}"
            data = self.db.get_item_backpack(db_key)
            contents = {}
            owner_uuid = player_uuid
            owner_name = player_name

            if data:
                contents = data.get("contents", {})
                owner_uuid = data.get("owner_uuid", player_uuid)
                owner_name = data.get("owner_name", player_name)
                # Use the active configured tier size to support upgrading/downgrading backpack items with the same ID
                
                # Check ownership rules
                if self.config.rules.get("require_owner_for_item_backpacks", True):
                    if owner_uuid != player_uuid and owner_name != player_name and not player.has_permission("ninjosbackpacks.admin.bypass"):
                        player.send_message(f"{ColorFormat.RED}You do not own this backpack!")
                        return
            else:
                # First open: Register
                self.db.save_item_backpack(db_key, bp_type, size, owner_uuid, owner_name, {})

            # 3. Determine if Pagination is Required
            use_pagination = size > 54
            total_pages = math.ceil(size / 45) if use_pagination else 1

            # Track state
            self.active_pages[player_uuid] = 0
            self.contents_caches[player_uuid] = contents

            # GUI initialization
            menu_type = MenuType.DOUBLE_CHEST if (size == 54 or use_pagination) else MenuType.CHEST
            
            custom_name = display_name
            if item_stack:
                try:
                    meta = item_stack.item_meta
                    if meta and meta.display_name:
                        custom_name = meta.display_name
                except Exception as me:
                    pass

            menu = Menu(menu_type, custom_name)

            # 4. Populate GUI slots
            supports_vs = self.supports_virtual_stacks(db_key)
            if use_pagination:
                self.populate_menu_page(menu, 0, total_pages, contents, db_key)
            else:
                for slot_str, item_data in contents.items():
                    try:
                        slot_idx = int(slot_str)
                        if 0 <= slot_idx < size:
                            if supports_vs:
                                item = self.create_visual_item(item_data)
                            else:
                                item = deserialize_item(item_data)
                            if item:
                                menu.inventory.set_item(slot_idx, item)
                    except Exception as e:
                        self.logger.error(f"Failed to deserialize item at slot {slot_str}: {e}")

            # 5. Set Locks and Safety Flags
            self.active_item_sessions[backpack_id] = player_uuid
            self.session_opened_successfully[player_uuid] = True

            # 6. Event Handlers
            allow_nesting = self.config.rules.get("allow_backpack_nesting", False)

            def on_transaction(tr: MenuTransaction) -> MenuTransactionResult:
                clicked_id = get_backpack_id_from_item(tr.item_clicked)
                clicked_with_id = get_backpack_id_from_item(tr.item_clicked_with)
                
                if clicked_id == backpack_id or clicked_with_id == backpack_id:
                    tr.player.send_message(f"{ColorFormat.RED}You cannot move or modify the active backpack item while it is open!")
                    return tr.discard()

                if not allow_nesting:
                    if clicked_with_id is not None:
                        tr.player.send_message(f"{ColorFormat.RED}Backpack nesting is disabled on this server!")
                        return tr.discard()

                if use_pagination and tr.slot >= 45:
                    curr_page = self.active_pages.get(player_uuid, 0)
                    cache = self.contents_caches.get(player_uuid, {})

                    if tr.slot == 45 and curr_page > 0:
                        if player_uuid in self.pending_page_changes:
                            return tr.discard()
                        self.pending_page_changes.add(player_uuid)

                        if not self.supports_virtual_stacks(db_key):
                            self.save_current_page_to_cache(menu, curr_page, cache)
                        curr_page -= 1
                        self.active_pages[player_uuid] = curr_page
                        target_page = curr_page
                        
                        def run_prev_page():
                            self.populate_menu_page(menu, target_page, total_pages, cache, db_key)
                            self.pending_page_changes.discard(player_uuid)

                        self.plugin.server.scheduler.run_task(
                            self.plugin,
                            run_prev_page,
                            delay=1
                        )
                    elif tr.slot == 53 and curr_page < total_pages - 1:
                        if player_uuid in self.pending_page_changes:
                            return tr.discard()
                        self.pending_page_changes.add(player_uuid)

                        if not self.supports_virtual_stacks(db_key):
                            self.save_current_page_to_cache(menu, curr_page, cache)
                        curr_page += 1
                        self.active_pages[player_uuid] = curr_page
                        target_page = curr_page

                        def run_next_page():
                            self.populate_menu_page(menu, target_page, total_pages, cache, db_key)
                            self.pending_page_changes.discard(player_uuid)

                        self.plugin.server.scheduler.run_task(
                            self.plugin,
                            run_next_page,
                            delay=1
                        )

                    return tr.discard()

                if self.supports_virtual_stacks(db_key):
                    curr_page = self.active_pages.get(player_uuid, 0)
                    self.plugin.server.scheduler.run_task(
                        self.plugin,
                        lambda: self.reconcile_virtual_stacks(tr.player, menu, db_key, curr_page),
                        delay=1
                    )

                if self.config.rules.get("save_after_each_transaction", False):
                    self.plugin.server.scheduler.run_task(
                        self.plugin,
                        lambda: self.save_backpack_contents(db_key, bp_type, size, owner_uuid, owner_name, menu, use_pagination, player_uuid),
                        delay=1
                    )

                return tr.proceed()

            def on_close(closed_player: Player) -> None:
                closed_player_uuid = str(closed_player.unique_id)
                if self.session_opened_successfully.get(closed_player_uuid, False):
                    if self.supports_virtual_stacks(db_key):
                        self.reconcile_virtual_stacks(closed_player, menu, db_key)
                    self.save_backpack_contents(db_key, bp_type, size, owner_uuid, owner_name, menu, use_pagination, closed_player_uuid)
                    self.active_item_sessions.pop(backpack_id, None)
                    self.session_opened_successfully.pop(closed_player_uuid, None)
                    self.active_pages.pop(closed_player_uuid, None)
                    self.contents_caches.pop(closed_player_uuid, None)
                    self.pending_page_changes.discard(closed_player_uuid)
                    self.logger.info(f"Backpack for {db_key} closed and saved.")

            menu.set_listener(on_transaction)
            menu.set_close_listener(on_close)

            # 7. Open Menu
            menu.send_to(player)
        except Exception as e:
            self.logger.error(f"[Backpack ERROR] Exception in open_item_backpack: {e}\n{traceback.format_exc()}")
            player.send_message(f"{ColorFormat.RED}An internal error occurred: {e}")

    def save_backpack_contents(self, backpack_id: str, bp_type: str, size: int, owner_uuid: str, owner_name: str, menu: Menu, use_pagination: bool, player_uuid: str) -> None:
        """Combines current state and writes to SQLite."""
        if self.supports_virtual_stacks(backpack_id):
            contents = self.contents_caches.get(player_uuid, {})
        else:
            if use_pagination:
                curr_page = self.active_pages.get(player_uuid, 0)
                cache = self.contents_caches.get(player_uuid, {})
                # Save the currently viewed page items into the cache first
                self.save_current_page_to_cache(menu, curr_page, cache)
                contents = cache
            else:
                contents = {}
                for slot in range(size):
                    try:
                        item = menu.inventory.get_item(slot)
                        if item and str(item.type) != "minecraft:air":
                            serialized = serialize_item(item)
                            if serialized:
                                contents[str(slot)] = serialized
                    except Exception as e:
                        self.logger.error(f"Error serializing slot {slot}: {e}")

        # Write to SQLite
        try:
            self.db.save_item_backpack(backpack_id, bp_type, size, owner_uuid, owner_name, contents)
        except Exception as e:
            self.logger.error(f"Failed to write backpack {backpack_id} to DB: {e}")

    def clear_player_sessions(self, player_uuid: str) -> None:
        """Forcefully cleans up and saves sessions for a disconnecting player."""
        item_to_remove = [k for k, v in self.active_item_sessions.items() if v == player_uuid]
        for backpack_id in item_to_remove:
            self.active_item_sessions.pop(backpack_id, None)
            self.logger.info(f"Force-released item session lock {backpack_id} for disconnected player UUID {player_uuid}")

        self.session_opened_successfully.pop(player_uuid, None)
        self.active_pages.pop(player_uuid, None)
        self.contents_caches.pop(player_uuid, None)

    def open_block_storage(self, player: Player, location, tier_key: str) -> None:
        """Opens a virtual inventory menu for a block-based storage vault."""
        player_uuid = str(player.unique_id)
        player_name = player.name

        # Coordinate-based storage key format: block:dimension:x:y:z
        block_key = f"block:{location.dimension.name}:{int(location.x)}:{int(location.y)}:{int(location.z)}"

        try:
            # 1. Manage session locking (dupe/corruption prevention)
            # Check if this block location is already opened by any player
            has_active_session = False
            active_player_uuid = self.active_item_sessions.get(block_key)
            if active_player_uuid is not None:
                active_player = self.plugin.server.get_player(uuid.UUID(active_player_uuid))
                if active_player is not None:
                    # Verify if they actually have the UI menu open in endstone-inventoryui
                    from endstone_inventoryui.manager.player_manager import find_session as find_ui_session
                    try:
                        ui_session = find_ui_session(active_player)
                        if ui_session is not None:
                            has_active_session = True
                    except Exception as se:
                        pass

                if not has_active_session:
                    self.active_item_sessions.pop(block_key, None)
                    self.session_opened_successfully.pop(active_player_uuid, None)
                else:
                    if active_player_uuid != player_uuid:
                        player.send_message(f"{ColorFormat.RED}This vault block is already in use by another player!")
                        return
                    else:
                        player.send_message(f"{ColorFormat.RED}You already have this vault block open!")
                        return

            # Lock the session to the current player
            self.active_item_sessions[block_key] = player_uuid
            self.session_opened_successfully[player_uuid] = False

            # 2. Retrieve block tier details from config
            bp_def = self.config.block_storage.get(tier_key)
            if not bp_def or not bp_def.get("enabled", True):
                player.send_message(f"{ColorFormat.RED}This block storage tier ({tier_key}) is disabled.")
                self.active_item_sessions.pop(block_key, None)
                return

            size = bp_def.get("size", 27)
            display_name = bp_def.get("display_name", "Block Vault")

            # Load from DB
            data = self.db.get_item_backpack(block_key) # Reusing item_backpacks table
            contents = {}
            owner_uuid = player_uuid
            owner_name = player_name

            if data:
                contents = data.get("contents", {})
                owner_uuid = data.get("owner_uuid", player_uuid)
                owner_name = data.get("owner_name", player_name)
            else:
                # First open: Register
                self.db.save_item_backpack(block_key, tier_key, size, owner_uuid, owner_name, {})

            # 3. Pagination & Menu Settings
            use_pagination = size > 54
            total_pages = math.ceil(size / 45) if use_pagination else 1

            self.active_pages[player_uuid] = 0
            self.contents_caches[player_uuid] = contents

            # Menu UI initialization
            menu_type = MenuType.DOUBLE_CHEST if (size == 54 or use_pagination) else MenuType.CHEST
            menu = Menu(menu_type, display_name)

            supports_vs = self.supports_virtual_stacks(block_key)
            if use_pagination:
                self.populate_menu_page(menu, 0, total_pages, contents, block_key)
            else:
                for i in range(size):
                    db_slot_str = str(i)
                    if db_slot_str in contents:
                        try:
                            if supports_vs:
                                item = self.create_visual_item(contents[db_slot_str])
                            else:
                                item = deserialize_item(contents[db_slot_str])
                            if item:
                                menu.inventory.set_item(i, item)
                        except Exception as e:
                            self.logger.error(f"Failed to deserialize slot {db_slot_str}: {e}")

            # 4. Handle menu opening confirmation
            def on_open_task():
                self.session_opened_successfully[player_uuid] = True

            self.plugin.server.scheduler.run_task(self.plugin, on_open_task, delay=4)

            # 5. UI interaction event hooks
            def on_transaction(tr: MenuTransaction) -> MenuTransactionResult:
                # Safeguards
                allow_nesting = self.config.rules.get("allow_backpack_nesting", False)
                clicked_with_id = get_backpack_id_from_item(tr.item_clicked_with)

                if not allow_nesting and clicked_with_id is not None:
                    tr.player.send_message(f"{ColorFormat.RED}Backpack nesting is disabled on this server!")
                    return tr.discard()

                if self.supports_virtual_stacks(block_key):
                    # Intercept manual deposits (merges) and withdrawals to prevent client swaps and lore leakage!
                    cfg = getattr(self.config, "virtual_stacks", {})
                    max_amount = cfg.get("max_amount_per_slot", 900)
                    withdraw_stack = cfg.get("withdraw_stack_at_a_time", True)
                    default_withdraw = cfg.get("default_withdraw_amount", 64)
                    use_max_stack = cfg.get("use_item_max_stack_size_for_withdraw", True)
                    
                    storage_slots = 45 if use_pagination else size
                    
                    gui_item = tr.item_clicked if tr.slot < storage_slots else None
                    cursor_item = tr.item_clicked_with
                    
                    if tr.slot < storage_slots and gui_item is not None:
                        is_visual = False
                        if gui_item.item_meta and gui_item.item_meta.has_lore:
                            for line in gui_item.item_meta.lore:
                                if "Stored Amount:" in line:
                                    is_visual = True
                                    break
                        
                        if is_visual:
                            curr_page = self.active_pages.get(player_uuid, 0)
                            cache = self.contents_caches[player_uuid]
                            db_slot_str = str(curr_page * 45 + tr.slot)
                            cache_item = cache.get(db_slot_str)
                            
                            # A. Depositing / Merging item of same type
                            if cursor_item and str(cursor_item.type) == str(gui_item.type):
                                if cache_item:
                                    current_qty = cache_item.get("amount", 1)
                                    added_qty = cursor_item.amount
                                    new_qty = current_qty + added_qty
                                    
                                    if new_qty > max_amount:
                                        excess = new_qty - max_amount
                                        tr.item_clicked_with.amount = excess
                                        new_qty = max_amount
                                    else:
                                        tr.item_clicked_with.type = "minecraft:air"
                                        tr.item_clicked_with.amount = 0
                                    
                                    cache_item["amount"] = new_qty
                                    
                                    # Consolidate cache and redraw GUI slots to match consolidated state
                                    cache = self.consolidate_cache(cache, max_amount)
                                    self.contents_caches[player_uuid] = cache
                                    
                                    for idx in range(storage_slots):
                                        db_idx_str = str(curr_page * 45 + idx)
                                        c_item = cache.get(db_idx_str)
                                        v_item = self.create_visual_item(c_item) if c_item else None
                                        g_item = menu.inventory.get_item(idx)
                                        if not self.items_are_equal(g_item, v_item):
                                            menu.inventory.set_item(idx, v_item)
                                    
                                    # Save cache
                                    self.plugin.server.scheduler.run_task(
                                        self.plugin,
                                        lambda: self.db.save_item_backpack(block_key, tier_key, size, owner_uuid, owner_name, cache),
                                        delay=1
                                    )
                                    return tr.discard()
                            
                            # B. Withdrawing (clicking with empty cursor / air)
                            elif not cursor_item or str(cursor_item.type) == "minecraft:air":
                                if cache_item:
                                    stored_qty = cache_item.get("amount", 1)
                                    item_example = deserialize_item(cache_item)
                                    if item_example:
                                        max_stack = item_example.max_stack_size if use_max_stack else default_withdraw
                                        withdraw_qty = max_stack if withdraw_stack else 1
                                        withdraw_qty = min(stored_qty, withdraw_qty)
                                        
                                        # Give clean items directly
                                        give_stack = deserialize_item(cache_item)
                                        if give_stack:
                                            give_stack.amount = withdraw_qty
                                            leftovers = tr.player.inventory.add_item(give_stack)
                                            for leftover in leftovers.values():
                                                if leftover.amount > 0:
                                                    tr.player.dimension.drop_item(tr.player.location, leftover)
                                        
                                        new_qty = stored_qty - withdraw_qty
                                        if new_qty <= 0:
                                            cache.pop(db_slot_str, None)
                                        else:
                                            cache_item["amount"] = new_qty
                                            
                                        # Consolidate cache and redraw GUI slots to match consolidated state
                                        cache = self.consolidate_cache(cache, max_amount)
                                        self.contents_caches[player_uuid] = cache
                                        
                                        for idx in range(storage_slots):
                                            db_idx_str = str(curr_page * 45 + idx)
                                            c_item = cache.get(db_idx_str)
                                            v_item = self.create_visual_item(c_item) if c_item else None
                                            g_item = menu.inventory.get_item(idx)
                                            if not self.items_are_equal(g_item, v_item):
                                                menu.inventory.set_item(idx, v_item)
                                            
                                        # Save cache
                                        self.plugin.server.scheduler.run_task(
                                            self.plugin,
                                            lambda: self.db.save_item_backpack(block_key, tier_key, size, owner_uuid, owner_name, cache),
                                            delay=1
                                        )
                                        return tr.discard()

                if use_pagination and tr.slot >= 45:
                    curr_page = self.active_pages.get(player_uuid, 0)
                    cache = self.contents_caches.get(player_uuid, {})

                    if tr.slot == 45 and curr_page > 0:
                        if player_uuid in self.pending_page_changes:
                            return tr.discard()
                        self.pending_page_changes.add(player_uuid)

                        if not self.supports_virtual_stacks(block_key):
                            self.save_current_page_to_cache(menu, curr_page, cache)
                        curr_page -= 1
                        self.active_pages[player_uuid] = curr_page
                        target_page = curr_page

                        def run_prev_page():
                            self.populate_menu_page(menu, target_page, total_pages, cache, block_key)
                            self.pending_page_changes.discard(player_uuid)

                        self.plugin.server.scheduler.run_task(
                            self.plugin,
                            run_prev_page,
                            delay=1
                        )
                    elif tr.slot == 53 and curr_page < total_pages - 1:
                        if player_uuid in self.pending_page_changes:
                            return tr.discard()
                        self.pending_page_changes.add(player_uuid)

                        if not self.supports_virtual_stacks(block_key):
                            self.save_current_page_to_cache(menu, curr_page, cache)
                        curr_page += 1
                        self.active_pages[player_uuid] = curr_page
                        target_page = curr_page

                        def run_next_page():
                            self.populate_menu_page(menu, target_page, total_pages, cache, block_key)
                            self.pending_page_changes.discard(player_uuid)

                        self.plugin.server.scheduler.run_task(
                            self.plugin,
                            run_next_page,
                            delay=1
                        )

                    return tr.discard()

                if self.supports_virtual_stacks(block_key):
                    curr_page = self.active_pages.get(player_uuid, 0)
                    self.plugin.server.scheduler.run_task(
                        self.plugin,
                        lambda: self.reconcile_virtual_stacks(tr.player, menu, block_key, curr_page),
                        delay=1
                    )

                if self.config.rules.get("save_after_each_transaction", False):
                    self.plugin.server.scheduler.run_task(
                        self.plugin,
                        lambda: self.save_backpack_contents(block_key, tier_key, size, owner_uuid, owner_name, menu, use_pagination, player_uuid),
                        delay=1
                    )

                return tr.proceed()

            def on_close(closed_player: Player) -> None:
                closed_player_uuid = str(closed_player.unique_id)
                if self.session_opened_successfully.get(closed_player_uuid, False):
                    if self.supports_virtual_stacks(block_key):
                        self.reconcile_virtual_stacks(closed_player, menu, block_key)
                        self.clean_player_inventory(closed_player)
                    self.save_backpack_contents(block_key, tier_key, size, owner_uuid, owner_name, menu, use_pagination, closed_player_uuid)
                    self.active_item_sessions.pop(block_key, None)
                    self.session_opened_successfully.pop(closed_player_uuid, None)
                    self.active_pages.pop(closed_player_uuid, None)
                    self.contents_caches.pop(closed_player_uuid, None)
                    self.pending_page_changes.discard(closed_player_uuid)
                    self.logger.info(f"Vault {block_key} closed and saved.")

            menu.set_listener(on_transaction)
            menu.set_close_listener(on_close)

            # 6. Open Menu
            menu.send_to(player)
        except Exception as e:
            self.logger.error(f"[Block Storage ERROR] Exception in open_block_storage: {e}\n{traceback.format_exc()}")
            player.send_message(f"{ColorFormat.RED}An internal error occurred: {e}")
