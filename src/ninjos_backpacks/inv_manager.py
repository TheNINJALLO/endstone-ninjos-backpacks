import json
from endstone import Player
from endstone.inventory import ItemStack
from endstone.form import ActionForm, ModalForm, TextInput, Dropdown
from endstone_inventoryui import Menu, MenuType, MenuTransaction, MenuTransactionResult
from ninjos_backpacks.serializer import serialize_item, deserialize_item

class InventoryManagerUI:
    def __init__(self, plugin):
        self.plugin = plugin
        self.db = plugin.db
        self.server = plugin.server
        self.logger = plugin.logger

    def open(self, player: Player):
        """Open the unified inventory manager menu"""
        if not self.db:
            player.send_message("§cDatabase not available.")
            return

        opls = self.server.online_players
        online_names = [pl.name for pl in opls]

        # 1. Container type selection dropdown
        container_dropdown = Dropdown(
            label="Container Type to inspect",
            options=["Inventory", "Ender Chest"]
        )

        # 2. Select online player dropdown (with offline fallback as default option)
        player_dropdown = Dropdown(
            label="Select Online Player (or select '-- Offline Player --' and type name below)",
            options=["-- Offline Player (Use Textbox) --"] + online_names
        )

        # 3. Text input for offline lookup
        name_input = TextInput(
            label="Offline Player Name (ignored if online player selected above)",
            placeholder="Type offline player name...",
            default_value=""
        )

        form = ModalForm(
            title="§l§6Inventory Manager",
            controls=[container_dropdown, player_dropdown, name_input]
        )

        def on_submit(pl, data):
            if data is None or data == "":
                return  # Form closed

            # Parse JSON response from modal form
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except Exception as e:
                    self.logger.error(f"Failed to parse form response: {e}")
                    return

            if not isinstance(data, list) or len(data) < 2:
                return

            container_type_idx = int(data[0])
            online_choice_idx = int(data[1])
            offline_name_input = data[2].strip() if len(data) > 2 else ""

            # Check container type
            container_type = "inv" if container_type_idx == 0 else "ender"

            # Determine target player
            if online_choice_idx == 0:
                # Offline Lookup
                if not offline_name_input:
                    pl.send_message("§cPlease enter an offline player name, or select an online player.")
                    return self.open(pl)

                try:
                    target_users = self.db.search_users_by_name(offline_name_input)
                    if not target_users:
                        pl.send_message(f"§cNo player found matching '§e{offline_name_input}§c' in database.")
                        pl.send_message("§7Note: Players must join at least once to be stored.")
                        return self.open(pl)

                    if len(target_users) > 1:
                        # Multiple matches - show disambiguation menu
                        disambiguate = ActionForm(
                            title="§lMultiple Matches Found",
                            content=f"§7Found {len(target_users)} players matching '§e{offline_name_input}§7'"
                        )
                        for user in target_users:
                            disambiguate.add_button(f"§7{user.name}")
                        disambiguate.add_button("« Search Again")

                        def on_disambiguate_select(viewer, idx):
                            if idx is None:
                                return self.open(viewer)
                            try:
                                idx = int(idx)
                            except (ValueError, TypeError):
                                return self.open(viewer)

                            if idx >= len(target_users):
                                return self.open(viewer)
                            user = target_users[idx]
                            if container_type == "inv":
                                return self._open_offline_inventory_ui(viewer, user)
                            else:
                                return self._open_offline_enderchest_ui(viewer, user)

                        disambiguate.on_submit = on_disambiguate_select
                        pl.send_form(disambiguate)
                        return
                    else:
                        # Single offline match
                        user = target_users[0]
                        if container_type == "inv":
                            return self._open_offline_inventory_ui(pl, user)
                        else:
                            return self._open_offline_enderchest_ui(pl, user)
                except Exception as e:
                    self.logger.error(f"Offline lookup error: {e}")
                    pl.send_message(f"§cLookup error: {e}")
                    return self.open(pl)
            else:
                # Online Player from dropdown
                target_name = online_names[online_choice_idx - 1]
                target_player = None
                for live in self.server.online_players:
                    if live.name == target_name:
                        target_player = live
                        break

                if not target_player:
                    pl.send_message("§cThe selected player went offline.")
                    return self.open(pl)

                if container_type == "inv":
                    return self._open_online_inventory_ui(pl, target_player)
                else:
                    return self._open_online_enderchest_ui(pl, target_player)

        form.on_submit = on_submit
        player.send_form(form)

    # ──────────────────────────────────────────────────────────────────────
    # ONLINE CONTAINERS HANDLING
    # ──────────────────────────────────────────────────────────────────────

    def _open_online_inventory_ui(self, viewer: Player, target: Player):
        """Open target player's inventory as interactive Menu using endstone-inventoryui"""
        tname = target.name
        menu = Menu(MenuType.DOUBLE_CHEST, f"{tname}'s Inventory")

        # 1. Populate main inventory slots (0 to 35)
        for i in range(36):
            item = target.inventory.get_item(i)
            if item and str(item.type) != "minecraft:air":
                menu.inventory.set_item(i, item)

        # 2. Add divider panes in slots 36-44 and 50-53
        divider = ItemStack("minecraft:gray_stained_glass_pane", 1)
        try:
            meta = divider.item_meta
            if meta:
                meta.display_name = "§r§8Divider"
                divider.set_item_meta(meta)
        except Exception:
            pass

        divider_slots = list(range(36, 45)) + list(range(50, 54))
        for slot in divider_slots:
            menu.inventory.set_item(slot, divider)

        # 3. Populate armor and offhand slots (45 to 49)
        helm = target.inventory.helmet
        if helm and str(helm.type) != "minecraft:air":
            menu.inventory.set_item(45, helm)
        chest = target.inventory.chestplate
        if chest and str(chest.type) != "minecraft:air":
            menu.inventory.set_item(46, chest)
        legs = target.inventory.leggings
        if legs and str(legs.type) != "minecraft:air":
            menu.inventory.set_item(47, legs)
        boots = target.inventory.boots
        if boots and str(boots.type) != "minecraft:air":
            menu.inventory.set_item(48, boots)
        offhand = target.inventory.item_in_off_hand
        if offhand and str(offhand.type) != "minecraft:air":
            menu.inventory.set_item(49, offhand)

        # 4. Listeners
        def on_transaction(tr: MenuTransaction) -> MenuTransactionResult:
            if tr.slot in divider_slots:
                return tr.discard()
            
            # Sync live target inventory in delayed task
            self.server.scheduler.run_task(
                self.plugin,
                lambda: self._sync_online_inventory(target, menu),
                delay=1
            )
            return tr.proceed()

        def on_close(closed_player: Player) -> None:
            self._sync_online_inventory(target, menu)
            closed_player.send_message(f"§aSaved and closed {tname}'s inventory.")

        menu.set_listener(on_transaction)
        menu.set_close_listener(on_close)
        menu.send_to(viewer)

    def _sync_online_inventory(self, target: Player, menu: Menu):
        try:
            # Main inventory slots 0-35
            for i in range(36):
                gui_item = menu.inventory.get_item(i)
                if gui_item is None or str(gui_item.type) == "minecraft:air":
                    target.inventory.set_item(i, None)
                else:
                    target.inventory.set_item(i, gui_item)

            # Armor and Offhand slots
            helm = menu.inventory.get_item(45)
            target.inventory.helmet = None if (helm is None or str(helm.type) == "minecraft:air") else helm
            chest = menu.inventory.get_item(46)
            target.inventory.chestplate = None if (chest is None or str(chest.type) == "minecraft:air") else chest
            legs = menu.inventory.get_item(47)
            target.inventory.leggings = None if (legs is None or str(legs.type) == "minecraft:air") else legs
            boots = menu.inventory.get_item(48)
            target.inventory.boots = None if (boots is None or str(boots.type) == "minecraft:air") else boots
            offhand = menu.inventory.get_item(49)
            target.inventory.item_in_off_hand = None if (offhand is None or str(offhand.type) == "minecraft:air") else offhand

            self.db.save_inventory(target)
        except Exception as e:
            self.logger.error(f"Error syncing online inventory for {target.name}: {e}")

    def _open_online_enderchest_ui(self, viewer: Player, target: Player):
        """Open target player's ender chest as interactive Menu using endstone-inventoryui"""
        tname = target.name
        menu = Menu(MenuType.CHEST, f"{tname}'s Ender Chest")

        for i in range(27):
            item = target.ender_chest.get_item(i)
            if item and str(item.type) != "minecraft:air":
                menu.inventory.set_item(i, item)

        def on_transaction(tr: MenuTransaction) -> MenuTransactionResult:
            self.server.scheduler.run_task(
                self.plugin,
                lambda: self._sync_online_enderchest(target, menu),
                delay=1
            )
            return tr.proceed()

        def on_close(closed_player: Player) -> None:
            self._sync_online_enderchest(target, menu)
            closed_player.send_message(f"§aSaved and closed {tname}'s ender chest.")

        menu.set_listener(on_transaction)
        menu.set_close_listener(on_close)
        menu.send_to(viewer)

    def _sync_online_enderchest(self, target: Player, menu: Menu):
        try:
            for i in range(27):
                gui_item = menu.inventory.get_item(i)
                if gui_item is None or str(gui_item.type) == "minecraft:air":
                    target.ender_chest.set_item(i, None)
                else:
                    target.ender_chest.set_item(i, gui_item)

            self.db.save_enderchest(target)
        except Exception as e:
            self.logger.error(f"Error syncing online ender chest for {target.name}: {e}")

    # ──────────────────────────────────────────────────────────────────────
    # OFFLINE CONTAINERS HANDLING
    # ──────────────────────────────────────────────────────────────────────

    def _open_offline_inventory_ui(self, viewer: Player, user):
        """Open offline player's inventory as interactive Menu using endstone-inventoryui"""
        menu = Menu(MenuType.DOUBLE_CHEST, f"{user.name}'s Inventory (Offline)")

        # 1. Populate divider panes in slots 36-44 and 50-53
        divider = ItemStack("minecraft:gray_stained_glass_pane", 1)
        try:
            meta = divider.item_meta
            if meta:
                meta.display_name = "§r§8Divider"
                divider.set_item_meta(meta)
        except Exception:
            pass

        divider_slots = list(range(36, 45)) + list(range(50, 54))
        for slot in divider_slots:
            menu.inventory.set_item(slot, divider)

        # 2. Load and deserialize items from the SQLite database
        try:
            db_items = self.db.get_inventory(user.xuid)
            for it_data in db_items:
                item = deserialize_item(it_data)
                if not item:
                    continue
                slot = it_data.get("slot", 0)
                if 0 <= slot < 36:
                    menu.inventory.set_item(slot, item)
                elif slot == -1:
                    menu.inventory.set_item(45, item)
                elif slot == -2:
                    menu.inventory.set_item(46, item)
                elif slot == -3:
                    menu.inventory.set_item(47, item)
                elif slot == -4:
                    menu.inventory.set_item(48, item)
                elif slot == -5:
                    menu.inventory.set_item(49, item)
        except Exception as e:
            self.logger.error(f"Error loading offline inventory for {user.name}: {e}")

        # 3. Listeners
        def on_transaction(tr: MenuTransaction) -> MenuTransactionResult:
            if tr.slot in divider_slots:
                return tr.discard()
            
            # Sync offline database changes in delayed task
            self.server.scheduler.run_task(
                self.plugin,
                lambda: self._sync_offline_inventory(user, menu),
                delay=1
            )
            return tr.proceed()

        def on_close(closed_player: Player) -> None:
            self._sync_offline_inventory(user, menu)
            closed_player.send_message(f"§aSaved and closed offline player {user.name}'s inventory.")

        menu.set_listener(on_transaction)
        menu.set_close_listener(on_close)
        menu.send_to(viewer)

    def _sync_offline_inventory(self, user, menu: Menu):
        try:
            items = []
            # Main inventory slots 0-35
            for i in range(36):
                gui_item = menu.inventory.get_item(i)
                if gui_item and str(gui_item.type) != "minecraft:air":
                    items.append(self.db._serialize_db_item(gui_item, i, "slot"))
            
            # Armor and offhand map
            armor_map = {
                45: (-1, "helmet"),
                46: (-2, "chestplate"),
                47: (-3, "leggings"),
                48: (-4, "boots"),
                49: (-5, "item_in_off_hand")
            }
            for gui_slot, (db_slot, slot_type) in armor_map.items():
                gui_item = menu.inventory.get_item(gui_slot)
                if gui_item and str(gui_item.type) != "minecraft:air":
                    items.append(self.db._serialize_db_item(gui_item, db_slot, slot_type))

            self.db.save_inventory_items(user.xuid, user.name, items)
        except Exception as e:
            self.logger.error(f"Error saving offline inventory for {user.name}: {e}")

    def _open_offline_enderchest_ui(self, viewer: Player, user):
        """Open offline player's ender chest as interactive Menu using endstone-inventoryui"""
        menu = Menu(MenuType.CHEST, f"{user.name}'s Ender Chest (Offline)")

        try:
            db_items = self.db.get_enderchest(user.xuid)
            for it_data in db_items:
                item = deserialize_item(it_data)
                if not item:
                    continue
                slot = it_data.get("slot", 0)
                if 0 <= slot < 27:
                    menu.inventory.set_item(slot, item)
        except Exception as e:
            self.logger.error(f"Error loading offline ender chest for {user.name}: {e}")

        def on_transaction(tr: MenuTransaction) -> MenuTransactionResult:
            self.server.scheduler.run_task(
                self.plugin,
                lambda: self._sync_offline_enderchest(user, menu),
                delay=1
            )
            return tr.proceed()

        def on_close(closed_player: Player) -> None:
            self._sync_offline_enderchest(user, menu)
            closed_player.send_message(f"§aSaved and closed offline player {user.name}'s ender chest.")

        menu.set_listener(on_transaction)
        menu.set_close_listener(on_close)
        menu.send_to(viewer)

    def _sync_offline_enderchest(self, user, menu: Menu):
        try:
            items = []
            for i in range(27):
                gui_item = menu.inventory.get_item(i)
                if gui_item and str(gui_item.type) != "minecraft:air":
                    items.append(self.db._serialize_db_item(gui_item, i, "slot"))

            self.db.save_enderchest_items(user.xuid, user.name, items)
        except Exception as e:
            self.logger.error(f"Error saving offline ender chest for {user.name}: {e}")
