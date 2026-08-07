import json
from typing import Dict, Any, Optional

from endstone import Player, ColorFormat
from endstone.inventory import ItemStack
from endstone_inventoryui import Menu, MenuType, MenuTransaction, MenuTransactionResult

from ninjos_backpacks.serializer import serialize_item, deserialize_item

class HopperUI:
    @classmethod
    def open_menu(cls, player: Player, hopper_key: str, manager) -> None:
        try:
            import time
            manager.last_open_times[str(player.unique_id)] = time.time()

            h_data = manager.db.get_hopper(hopper_key)
            if not h_data:
                player.send_message(f"{ColorFormat.RED}Hopper data could not be found.")
                return

            # Open standard 5-slot Hopper inventory shape
            menu = Menu(MenuType.HOPPER, "Advanced Hopper Filters")
            
            # 1. Populate filters in slots 0-3 (the first 4 slots)
            filters = h_data.get("filters", {})
            for i in range(4):
                slot_str = str(i)
                if slot_str in filters:
                    item = deserialize_item(filters[slot_str])
                    if item:
                        menu.inventory.set_item(i, item)

            # 2. Add Settings button in Slot 4 (the last slot)
            settings_item = ItemStack("minecraft:clock", 1)
            meta = settings_item.item_meta
            if meta:
                meta.display_name = "§b⚙ Settings & Configuration"
                meta.lore = [
                    "§7Click to open Settings Panel"
                ]
                settings_item.set_item_meta(meta)
            menu.inventory.set_item(4, settings_item)

            # 3. Transaction Hook
            def on_transaction(tr: MenuTransaction) -> MenuTransactionResult:
                if tr.slot == 4:
                    try:
                        from endstone_inventoryui.manager.player_manager import find_session as find_ui_session
                        ui_session = find_ui_session(player)
                        if ui_session and hasattr(ui_session, "close"):
                            ui_session.close()
                    except Exception:
                        pass

                    # Open chest settings menu after 2-tick delay
                    manager.plugin.server.scheduler.run_task(
                        manager.plugin,
                        lambda: cls.open_settings_menu(player, hopper_key, manager),
                        delay=2
                    )
                    return tr.discard()
                elif tr.slot > 4:
                    return tr.discard()
                return tr.proceed()

            # 4. Close Hook
            def on_close(closed_player: Player) -> None:
                import time
                manager.last_close_times[str(closed_player.unique_id)] = time.time()

                new_filters = {}
                for slot in range(4):
                    item = menu.inventory.get_item(slot)
                    if item and str(item.type) != "minecraft:air":
                        serialized = serialize_item(item)
                        if serialized:
                            new_filters[str(slot)] = serialized

                current_data = manager.db.get_hopper(hopper_key)
                if current_data:
                    current_data["filters"] = new_filters
                    manager.db.save_hopper(hopper_key, current_data)

            menu.set_listener(on_transaction)
            menu.set_close_listener(on_close)
            menu.send_to(player)

        except Exception as e:
            manager.logger.error(f"Error opening hopper configuration UI: {e}")
            player.send_message(f"{ColorFormat.RED}Error opening menu: {e}")

    @classmethod
    def open_settings_menu(cls, player: Player, hopper_key: str, manager) -> None:
        try:
            import time
            manager.last_open_times[str(player.unique_id)] = time.time()

            h_data = manager.db.get_hopper(hopper_key)
            if not h_data:
                player.send_message(f"{ColorFormat.RED}Hopper data could not be found.")
                return

            settings_menu = Menu(MenuType.CHEST, "Hopper Settings")
            cls.populate_settings_items(settings_menu, h_data, manager)

            def on_transaction(tr: MenuTransaction) -> MenuTransactionResult:
                slot = tr.slot
                cls.handle_settings_click(tr.player, hopper_key, slot, manager, settings_menu)
                return tr.discard()

            def on_settings_close(closed_player: Player) -> None:
                import time
                manager.last_close_times[str(player.unique_id)] = time.time()

            settings_menu.set_listener(on_transaction)
            settings_menu.set_close_listener(on_settings_close)
            settings_menu.send_to(player)

        except Exception as e:
            manager.logger.error(f"Error opening hopper advanced settings: {e}")
            player.send_message(f"{ColorFormat.RED}Error opening advanced settings: {e}")

    @classmethod
    def populate_settings_items(cls, settings_menu: Menu, h_data: dict, manager) -> None:
        # Helper function to configure control items
        def set_button(slot: int, material: str, name: str, lore: list):
            btn = ItemStack(material, 1)
            meta = btn.item_meta
            if meta:
                meta.display_name = name
                meta.lore = lore
                btn.set_item_meta(meta)
            settings_menu.inventory.set_item(slot, btn)

        # Clear existing buttons
        for i in range(27):
            settings_menu.inventory.set_item(i, None)

        # 1. Enabled Toggle
        is_enabled = h_data.get("enabled", True)
        set_button(
            0,
            "minecraft:lime_dye" if is_enabled else "minecraft:gray_dye",
            "§aHopper Status: §aEnabled" if is_enabled else "§cHopper Status: §cDisabled",
            [
                "§7Click to toggle Enabled/Disabled status"
            ]
        )

        # 2. Filter Mode
        mode = h_data.get("mode", "whitelist")
        mode_desc = {
            "whitelist": "§bWhitelist (Matching items only)",
            "blacklist": "§eBlacklist (All items except matching)",
            "none": "§dNone (Collects all items)"
        }.get(mode, mode)
        set_button(
            1,
            "minecraft:paper",
            "§6Filter Mode",
            [
                f"§7Currently: {mode_desc}",
                "",
                "§eClick to Cycle Modes"
            ]
        )

        # 3. Horizontal Range
        horiz_range = h_data.get("horizontal_range", 8)
        set_button(
            2,
            "minecraft:compass",
            "§dHorizontal Range",
            [
                f"§7Currently: §f{horiz_range} blocks",
                "",
                "§eClick to Cycle Range options"
            ]
        )

        # 4. Vertical Up
        vert_up = h_data.get("vertical_up", 4)
        set_button(
            3,
            "minecraft:feather",
            "§bVertical Up Range",
            [
                f"§7Currently: §f{vert_up} blocks",
                "",
                "§eClick to Cycle Range options"
            ]
        )

        # 5. Vertical Down
        vert_down = h_data.get("vertical_down", 4)
        set_button(
            4,
            "minecraft:feather",
            "§cVertical Down Range",
            [
                f"§7Currently: §f{vert_down} blocks",
                "",
                "§eClick to Cycle Range options"
            ]
        )

        # 6. Linking Status
        linked = h_data.get("linked_storage")
        if linked:
            link_status = "§aLinked"
            link_lore = [
                f"§7Target: §f{linked.get('x')}, {linked.get('y')}, {linked.get('z')}",
                f"§7Dimension: §f{linked.get('dimension')}",
                f"§7Status: §aValid"
            ]
            link_material = "minecraft:ender_chest"
        else:
            link_status = "§cUnlinked"
            link_lore = [
                "§7Hopper does not have a linked destination.",
                "§7Run §e/hopper link §7in game chat to connect it."
            ]
            link_material = "minecraft:chest"
        
        set_button(5, link_material, f"§bDestination Status: {link_status}", link_lore)

        # 7. Stats
        stats = h_data.get("stats", {})
        moved = stats.get("items_moved_total", 0)
        set_button(
            6,
            "minecraft:redstone",
            "§eHopper Stats",
            [
                f"§7Items Moved: §f{moved:,}",
                f"§7Last Status: §f{stats.get('last_status', 'None')}"
            ]
        )

        # 8. Back Button
        set_button(8, "minecraft:arrow", "§e◀ Back", ["§7Return to filters configuration menu"])

        # 9. Fill remaining slots with iron bars spacer
        for i in range(27):
            if settings_menu.inventory.get_item(i) is None:
                spacer = ItemStack("minecraft:iron_bars", 1)
                meta = spacer.item_meta
                if meta:
                    meta.display_name = " "
                    spacer.set_item_meta(meta)
                settings_menu.inventory.set_item(i, spacer)

    @classmethod
    def handle_settings_click(cls, player: Player, hopper_key: str, slot: int, manager, settings_menu: Menu) -> None:
        h_data = manager.db.get_hopper(hopper_key)
        if not h_data:
            return

        changed = False
        
        if slot == 0:
            h_data["enabled"] = not h_data["enabled"]
            changed = True
        elif slot == 1:
            modes = ["whitelist", "blacklist", "none"]
            curr = h_data.get("mode", "whitelist")
            try:
                next_idx = (modes.index(curr) + 1) % len(modes)
            except ValueError:
                next_idx = 0
            h_data["mode"] = modes[next_idx]
            changed = True
        elif slot == 2:
            horiz_allowed = manager.cfg.allowed_horizontal
            curr = h_data.get("horizontal_range", 8)
            try:
                next_idx = (horiz_allowed.index(curr) + 1) % len(horiz_allowed)
            except ValueError:
                next_idx = 0
            h_data["horizontal_range"] = horiz_allowed[next_idx]
            changed = True
        elif slot == 3:
            vert_allowed = manager.cfg.allowed_vertical
            curr = h_data.get("vertical_up", 4)
            try:
                next_idx = (vert_allowed.index(curr) + 1) % len(vert_allowed)
            except ValueError:
                next_idx = 0
            h_data["vertical_up"] = vert_allowed[next_idx]
            changed = True
        elif slot == 4:
            vert_allowed = manager.cfg.allowed_vertical
            curr = h_data.get("vertical_down", 4)
            try:
                next_idx = (vert_allowed.index(curr) + 1) % len(vert_allowed)
            except ValueError:
                next_idx = 0
            h_data["vertical_down"] = vert_allowed[next_idx]
            changed = True
        elif slot == 8:
            try:
                from endstone_inventoryui.manager.player_manager import find_session as find_ui_session
                ui_session = find_ui_session(player)
                if ui_session and hasattr(ui_session, "close"):
                    ui_session.close()
            except Exception:
                pass

            # Reopen filters menu after 2-tick delay
            manager.plugin.server.scheduler.run_task(
                manager.plugin,
                lambda: cls.open_menu(player, hopper_key, manager),
                delay=2
            )
            return

        if changed:
            manager.db.save_hopper(hopper_key, h_data)
            # Repopulate settings items inside the existing menu instantly!
            cls.populate_settings_items(settings_menu, h_data, manager)
