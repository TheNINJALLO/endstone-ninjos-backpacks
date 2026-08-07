import math
import datetime
import traceback
from typing import List, Dict, Any, Optional

from endstone import Player, ColorFormat
from endstone.inventory import ItemStack

from ninjos_backpacks.serializer import deserialize_item, serialize_item, nbt_to_dict

class HopperScanner:
    def __init__(self, manager):
        self.manager = manager
        self.logger = manager.logger
        self.server = manager.plugin.server
        self.tick_counter = 0
        self.last_processed_idx = 0

    def is_player_nearby(self, dimension: str, x: int, y: int, z: int, max_dist: float) -> bool:
        for player in self.server.online_players:
            p_dim = player.location.dimension.name
            if p_dim == dimension:
                px, py, pz = player.location.x, player.location.y, player.location.z
                dist = math.sqrt((px - x)**2 + (py - y)**2 + (pz - z)**2)
                if dist <= max_dist:
                    return True
        return False

    def matches_filters(self, item: ItemStack, filters: dict, config) -> bool:
        if not filters:
            return False

        for slot_str, filter_data in filters.items():
            filter_item = deserialize_item(filter_data)
            if not filter_item:
                continue
            
            # 1. Type match
            if config.match_type:
                if str(filter_item.type) != str(item.type):
                    continue

            # 2. Display Name match
            if config.match_name:
                name1 = filter_item.item_meta.display_name if filter_item.item_meta else ""
                name2 = item.item_meta.display_name if item.item_meta else ""
                if name1 != name2:
                    continue

            # 3. Lore match
            if config.match_lore:
                lore1 = filter_item.item_meta.lore if (filter_item.item_meta and filter_item.item_meta.has_lore) else []
                lore2 = item.item_meta.lore if (item.item_meta and item.item_meta.has_lore) else []
                if lore1 != lore2:
                    continue

            # 4. Custom data / NBT match
            if config.match_custom_data:
                t1 = filter_item.nbt
                if t1 is not None:
                    t2 = item.nbt
                    if t2 is None:
                        continue
                    if nbt_to_dict(t1) != nbt_to_dict(t2):
                        continue

            return True

        return False

    def tick(self) -> None:
        try:
            self.tick_counter += 1
            
            # Fetch hoppers from DB
            hoppers = self.manager.db.list_hoppers()
            if not hoppers:
                return

            config = self.manager.cfg
            if not config.enabled:
                return

            # Skip if pausing when empty and no players online
            if config.pause_when_no_players_nearby:
                if len(self.server.online_players) == 0:
                    return

            max_to_process = config.max_hoppers_processed_per_tick
            total_hoppers = len(hoppers)
            
            # Stagger queue logic
            start_idx = self.last_processed_idx % total_hoppers
            end_idx = min(start_idx + max_to_process, total_hoppers)
            
            to_process = hoppers[start_idx:end_idx]
            
            processed_count = len(to_process)
            if processed_count < max_to_process and total_hoppers > processed_count:
                extra_needed = max_to_process - processed_count
                to_process.extend(hoppers[0:min(extra_needed, start_idx)])
                self.last_processed_idx = min(extra_needed, start_idx)
            else:
                self.last_processed_idx = end_idx % total_hoppers

            for hopper in to_process:
                stats = hopper.get("stats", {})
                last_scan_tick = stats.get("last_scan_tick", 0)
                is_full_cooldown = stats.get("storage_full", False)
                cooldown_ticks = config.storage_full_cooldown_ticks if is_full_cooldown else config.scan_interval_ticks
                
                if self.tick_counter < last_scan_tick:
                    last_scan_tick = 0
                
                if self.tick_counter - last_scan_tick < cooldown_ticks:
                    continue
                
                stats["last_scan_tick"] = self.tick_counter
                
                # Scan hopper
                self.scan_hopper(hopper, config)
                
                # Save updated stats
                self.manager.db.save_hopper(hopper["hopper_key"], hopper)

        except Exception as e:
            self.logger.error(f"[Hopper Scanner] Error inside scheduler tick: {e}\n{traceback.format_exc()}")

    def scan_hopper(self, hopper_data: dict, config) -> None:
        key = hopper_data["hopper_key"]
        enabled = hopper_data.get("enabled", True)
        link = hopper_data.get("linked_storage")
        storage_id = link.get("storage_id") if link else None
        
        # 1. Enabled status check
        if not enabled:
            return

        # 2. Manual link status check
        if not link:
            return

        if not storage_id:
            return

        parts = key.split(":")
        dim_name = parts[1]
        hx, hy, hz = int(parts[2]), int(parts[3]), int(parts[4])

        # 3. Skip check if pause empty is enabled and no nearby players
        if config.pause_when_no_players_nearby:
            if not self.is_player_nearby(dim_name, hx, hy, hz, config.player_nearby_range):
                return

        # 4. Check if linked storage exists
        adapter = self.manager.adapter
        if not adapter.is_valid_storage(storage_id):
            hopper_data["stats"]["last_status"] = "Invalid Link Target"
            return

        # 5. Check if storage is full
        if adapter.is_full(storage_id):
            hopper_data["stats"]["storage_full"] = True
            hopper_data["stats"]["last_status"] = "Storage Full"
            return
        else:
            hopper_data["stats"]["storage_full"] = False

        hr = hopper_data.get("horizontal_range", 8)
        vu = hopper_data.get("vertical_up", 4)
        vd = hopper_data.get("vertical_down", 4)

        checked_entities = 0
        items_moved = 0
        stacks_moved = 0
        
        filters = hopper_data.get("filters", {})
        start_time = datetime.datetime.now()

        # Iterate active dimension actors
        from endstone.actor import Item
        try:
            dim_obj = self.server.level.get_dimension(dim_name)
            all_actors = list(dim_obj.actors) if dim_obj else []
        except Exception:
            all_actors = list(self.server.level.actors)

        for actor in all_actors:
            if checked_entities >= config.max_entity_checks_per_hopper:
                break
            
            if not isinstance(actor, Item):
                continue

            if not actor.location or actor.location.dimension.name != dim_name:
                continue

            ax, ay, az = actor.location.x, actor.location.y, actor.location.z
            dx = abs(ax - hx)
            dz = abs(az - hz)
            dy = ay - hy

            # Check coordinate bounds
            if dx > hr or dz > hr or dy < -vd or dy > vu:
                continue

            checked_entities += 1

            item_stack = actor.item_stack
            if not item_stack or str(item_stack.type) == "minecraft:air" or item_stack.amount <= 0:
                continue

            # Apply filters
            mode = hopper_data.get("mode", "whitelist")
            should_collect = False
            if mode == "none":
                should_collect = True
            elif mode == "whitelist":
                should_collect = self.matches_filters(item_stack, filters, config)
            elif mode == "blacklist":
                should_collect = not self.matches_filters(item_stack, filters, config)

            if not should_collect:
                continue

            # Calculate allowed amount to move
            max_move = config.max_items_moved_per_scan - items_moved
            if max_move <= 0 or stacks_moved >= config.max_stacks_moved_per_scan:
                break

            to_move = min(item_stack.amount, max_move)
            if to_move <= 0:
                continue

            # Validate capacity
            space = adapter.get_available_space(storage_id, item_stack)
            if space <= 0:
                hopper_data["stats"]["storage_full"] = True
                break

            actual_move = min(to_move, space)
            if actual_move <= 0:
                continue

            # Rebuild ItemStack transfer details safely
            transfer_stack = ItemStack(str(item_stack.type), actual_move)
            if item_stack.nbt:
                transfer_stack.nbt = item_stack.nbt

            inserted = adapter.insert_item(storage_id, transfer_stack, actual_move)
            if inserted > 0:
                items_moved += inserted
                stacks_moved += 1
                
                new_amount = item_stack.amount - inserted
                if new_amount <= 0:
                    actor.remove()
                else:
                    item_stack.amount = new_amount
                    actor.item_stack = item_stack

        # Update stats
        if items_moved > 0:
            hopper_data["stats"]["items_moved_total"] = hopper_data["stats"].get("items_moved_total", 0) + items_moved
            hopper_data["stats"]["last_items_moved"] = items_moved
            hopper_data["stats"]["last_status"] = f"Moved {items_moved} items"
        else:
            hopper_data["stats"]["last_items_moved"] = 0
            if hopper_data["stats"].get("last_status") != "Storage Full":
                hopper_data["stats"]["last_status"] = "Idle"

        # Log slow scans
        if config.debug_timing:
            elapsed = (datetime.datetime.now() - start_time).total_seconds() * 1000.0
            if elapsed > 10.0:
                self.logger.warning(f"[Hopper Timer Warning] Slow scan detected at {key}: {elapsed:.1f}ms (Checked {checked_entities} actors).")
