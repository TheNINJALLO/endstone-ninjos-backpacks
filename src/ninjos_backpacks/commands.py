import json
import re
from typing import List, Optional, Any

from endstone import Player, ColorFormat
from endstone.command import Command, CommandSender
from endstone.inventory import ItemStack
from endstone.form import ActionForm, ModalForm, TextInput, Dropdown

from ninjos_backpacks.serializer import get_backpack_id_from_item

class CommandHandler:
    def __init__(self, plugin):
        self.plugin = plugin
        self.db = plugin.db
        self.config = plugin.cfg
        self.manager = plugin.manager
        self.logger = plugin.logger

    def execute(self, sender: CommandSender, command: Command, args: List[str]) -> bool:
        """Process the main /backpack commands and delegate to subcommands."""
        if not args:
            self.send_help(sender)
            return True

        subcommand = args[0].lower()

        if subcommand == "assign":
            return self.handle_assign(sender, args)
        elif subcommand == "open":
            return self.handle_open(sender, args)
        elif subcommand == "delete":
            return self.handle_delete(sender, args)
        elif subcommand == "info":
            return self.handle_info(sender, args)
        elif subcommand == "reload":
            return self.handle_reload(sender, args)
        elif subcommand == "list":
            return self.handle_list(sender, args)
        elif subcommand == "cleanup":
            return self.handle_cleanup(sender, args)
        elif subcommand == "config":
            return self.handle_config(sender, args)
        else:
            sender.send_message(f"{ColorFormat.RED}Unknown subcommand. Use /backpack for help.")
            return True

    def send_help(self, sender: CommandSender) -> None:
        """Send help lines to command executor."""
        sender.send_message(f"{ColorFormat.GOLD}=== NinjOSBackpacks Help ===")
        sender.send_message(f"{ColorFormat.YELLOW}/backpack assign {ColorFormat.GRAY}- Open GUI form to assign/give backpack (Admins)")
        sender.send_message(f"{ColorFormat.YELLOW}/backpack assign <player> <tier> [extra_lore] {ColorFormat.GRAY}- Give backpack to player")
        sender.send_message(f"{ColorFormat.YELLOW}/backpack config {ColorFormat.GRAY}- Open configuration GUI (Admins)")
        sender.send_message(f"{ColorFormat.YELLOW}/backpack open <player_name> [tier] {ColorFormat.GRAY}- Admin command to open a player's backpack")
        sender.send_message(f"{ColorFormat.YELLOW}/backpack delete <player_name> [tier] {ColorFormat.GRAY}- Admin command to delete a player's backpack")
        sender.send_message(f"{ColorFormat.YELLOW}/backpack info {ColorFormat.GRAY}- Show info for backpack currently held in hand")
        sender.send_message(f"{ColorFormat.YELLOW}/backpack reload {ColorFormat.GRAY}- Reload configuration file")
        sender.send_message(f"{ColorFormat.YELLOW}/backpack list {ColorFormat.GRAY}- Admin command to list known backpacks")
        sender.send_message(f"{ColorFormat.YELLOW}/backpack cleanup {ColorFormat.GRAY}- Clean up empty backpack records older than 30 days")

    def handle_assign(self, sender: CommandSender, args: List[str]) -> bool:
        """Command handler for /backpack assign"""
        if not sender.has_permission("ninjosbackpacks.command.give"):
            sender.send_message(f"{ColorFormat.RED}You do not have permission to use this command.")
            return True

        if len(args) < 3:
            if isinstance(sender, Player):
                self.open_give_form(sender)
            else:
                sender.send_message(f"{ColorFormat.RED}Usage: /backpack assign <player> <tier> [extra_lore]")
            return True

        player_name = args[1]
        tier = args[2].lower()
        extra_lore = " ".join(args[3:]) if len(args) > 3 else None

        target_player = self.plugin.server.get_player(player_name)
        if not target_player:
            sender.send_message(f"{ColorFormat.RED}Player '{player_name}' not found.")
            return True

        self.give_backpack(sender, target_player, tier, None, extra_lore)
        return True

    def open_give_form(self, sender: Player) -> None:
        """Opens ModalForm UI prompting the admin for custom backpack/vault values."""
        form = ModalForm(title="Give Backpack/Vault Form")
        
        form.add_control(TextInput(
            label="Target Player Name",
            placeholder="Enter target player name..."
        ))
        
        # Get list of enabled tiers from config (both items and block storages)
        tiers = [k for k, v in self.config.item_backpacks.items() if v.get("enabled", True)]
        tiers += [k for k, v in self.config.block_storage.items() if v.get("enabled", True)]
        if not tiers:
            sender.send_message(f"{ColorFormat.RED}No backpack or block storage tiers are currently enabled.")
            return
            
        form.add_control(Dropdown(
            label="Backpack/Vault Tier",
            options=tiers,
            default_index=0
        ))
        
        form.add_control(TextInput(
            label="Custom Display Name (optional)",
            placeholder="Leave blank for default tier name..."
        ))
        
        form.add_control(TextInput(
            label="Custom Specific Lore (optional)",
            placeholder="Enter custom lore line specific to this player..."
        ))
        
        def on_submit(p: Player, data: str):
            try:
                response = json.loads(data)
                target_name = response[0].strip()
                tier_idx = response[1]
                custom_name = response[2].strip() or None
                extra_lore = response[3].strip() or None
                
                if not target_name:
                    p.send_message(f"{ColorFormat.RED}Please enter a target player name!")
                    return
                    
                target_player = self.plugin.server.get_player(target_name)
                if not target_player:
                    p.send_message(f"{ColorFormat.RED}Player '{target_name}' is offline or does not exist.")
                    return
                    
                selected_tier = tiers[tier_idx]
                self.give_backpack(p, target_player, selected_tier, custom_name, extra_lore)
            except Exception as e:
                self.logger.error(f"Error submitting give form: {e}")
                p.send_message(f"{ColorFormat.RED}Error processing form submission: {e}")
                
        form.on_submit = on_submit
        sender.send_form(form)

    def give_backpack(self, sender: CommandSender, target_player: Player, tier: str, custom_name: Optional[str], extra_lore: Optional[str]) -> None:
        """Prepares and gives a backpack or block vault item stack to a player."""
        # Check item-based backpacks first
        bp_def = self.config.item_backpacks.get(tier)
        is_block = False
        if not bp_def:
            # Check block-based storages
            bp_def = self.config.block_storage.get(tier)
            if bp_def:
                is_block = True

        if not bp_def or not bp_def.get("enabled", True):
            sender.send_message(f"{ColorFormat.RED}Backpack or block storage tier '{tier}' is disabled or not configured.")
            return

        # Custom name override
        if not custom_name:
            custom_name = bp_def.get("display_name")

        if is_block:
            material = bp_def.get("block_type", "minecraft:crying_obsidian")
            raw_lore = bp_def.get("lore", ["§7Place this block on the ground to use it as a storage vault."])
        else:
            material = bp_def.get("material", "minecraft:chest")
            raw_lore = bp_def.get("lore", [])
        
        # Unique ID is the target player's name
        bp_id = target_player.name

        try:
            item = ItemStack(material, 1)
            meta = item.item_meta
            if meta:
                meta.display_name = custom_name
                # Format lore template
                formatted_lore = [line.replace("{id}", bp_id) for line in raw_lore]
                
                # Append custom extra lore specific to target player if provided
                if extra_lore:
                    formatted_lore.append(f"§d{extra_lore}")
                    
                meta.lore = formatted_lore
                item.set_item_meta(meta)

            # Give to target player
            leftovers = target_player.inventory.add_item(item)
            if leftovers:
                for leftover_item in leftovers.values():
                    if leftover_item and leftover_item.amount > 0:
                        target_player.dimension.drop_item(target_player.location, leftover_item)

            sender.send_message(f"{ColorFormat.GREEN}Successfully gave '{custom_name}' {ColorFormat.GREEN}to {target_player.name}.")
            target_player.send_message(f"{ColorFormat.GREEN}You have received a '{custom_name}'{ColorFormat.GREEN}!")
            self.logger.info(f"Backpack/Vault item for {bp_id} (Tier: {tier}) given to {target_player.name} by {sender.name}")
        except Exception as e:
            sender.send_message(f"{ColorFormat.RED}Failed to create or give backpack/vault item: {e}")
            self.logger.error(f"Error giving backpack/vault item: {e}")

    def handle_open(self, sender: CommandSender, args: List[str]) -> bool:
        """Command handler for /backpack open <player_name>"""
        if not sender.has_permission("ninjosbackpacks.command.open"):
            sender.send_message(f"{ColorFormat.RED}You do not have permission to use this command.")
            return True

        if not isinstance(sender, Player):
            sender.send_message(f"{ColorFormat.RED}This command can only be used by players in-game.")
            return True

        if len(args) < 2:
            sender.send_message(f"{ColorFormat.RED}Usage: /backpack open <player_name> [tier]")
            return True

        target_name = args[1].strip()
        bp_type = "small"
        if len(args) >= 3:
            bp_type = args[2].strip().lower()

        db_key = f"{target_name}_{bp_type}"

        # Query database to find if the backpack exists
        data = self.db.get_item_backpack(db_key)
        if not data:
            sender.send_message(f"{ColorFormat.RED}No {bp_type} backpack found in database for player: {target_name}")
            return True

        # Open it
        self.manager.open_item_backpack(sender, target_name, bp_type, None)
        return True

    def handle_delete(self, sender: CommandSender, args: List[str]) -> bool:
        """Command handler for /backpack delete <player_name> [tier]"""
        if not sender.has_permission("ninjosbackpacks.command.delete"):
            sender.send_message(f"{ColorFormat.RED}You do not have permission to use this command.")
            return True

        if len(args) < 2:
            sender.send_message(f"{ColorFormat.RED}Usage: /backpack delete <player_name> [tier]")
            return True

        target_name = args[1].strip()
        bp_type = "small"
        if len(args) >= 3:
            bp_type = args[2].strip().lower()

        db_key = f"{target_name}_{bp_type}"

        # Check if active session is running for this player
        if target_name in self.manager.active_item_sessions:
            sender.send_message(f"{ColorFormat.RED}Cannot delete backpack for {target_name} because they currently have an active session open!")
            return True

        success = self.db.delete_item_backpack(db_key)
        if success:
            sender.send_message(f"{ColorFormat.GREEN}Successfully deleted {bp_type} backpack for player {target_name}.")
            self.logger.info(f"Backpack {db_key} deleted from database by {sender.name}")
        else:
            # Fallback: check if the old key format exists and delete it
            old_success = self.db.delete_item_backpack(target_name)
            if old_success:
                sender.send_message(f"{ColorFormat.GREEN}Successfully deleted old format backpack for player {target_name}.")
                self.logger.info(f"Old format backpack for {target_name} deleted from database by {sender.name}")
            else:
                sender.send_message(f"{ColorFormat.RED}No {bp_type} backpack found in database for player: {target_name}")

        return True

    def handle_info(self, sender: CommandSender, args: List[str]) -> bool:
        """Command handler for /backpack info"""
        if not sender.has_permission("ninjosbackpacks.command.info"):
            sender.send_message(f"{ColorFormat.RED}You do not have permission to use this command.")
            return True

        if not isinstance(sender, Player):
            sender.send_message(f"{ColorFormat.RED}This command can only be used by players in-game.")
            return True

        # Check item in hand
        held_slot = sender.inventory.held_item_slot
        held_item = sender.inventory.get_item(held_slot)
        backpack_id = get_backpack_id_from_item(held_item)

        if backpack_id:
            data = self.db.get_item_backpack(backpack_id)
            sender.send_message(f"{ColorFormat.GOLD}=== Backpack Item Info ===")
            sender.send_message(f"{ColorFormat.YELLOW}ID (Owner): {ColorFormat.WHITE}{backpack_id}")
            if data:
                sender.send_message(f"{ColorFormat.YELLOW}Tier: {ColorFormat.WHITE}{data.get('type')}")
                sender.send_message(f"{ColorFormat.YELLOW}Size: {ColorFormat.WHITE}{data.get('size')} slots")
                sender.send_message(f"{ColorFormat.YELLOW}Owner UUID: {ColorFormat.WHITE}{data.get('owner_uuid')}")
                sender.send_message(f"{ColorFormat.YELLOW}Owner Name: {ColorFormat.WHITE}{data.get('owner_name')}")
                sender.send_message(f"{ColorFormat.YELLOW}Created At: {ColorFormat.WHITE}{data.get('created_at')}")
                sender.send_message(f"{ColorFormat.YELLOW}Updated At: {ColorFormat.WHITE}{data.get('updated_at')}")
                items_cnt = sum(1 for v in data.get("contents", {}).values() if v and v.get("type") is not None)
                sender.send_message(f"{ColorFormat.YELLOW}Items Stored: {ColorFormat.WHITE}{items_cnt}")
            else:
                sender.send_message(f"{ColorFormat.YELLOW}Status: {ColorFormat.RED}Not yet initialized in database (empty)")
            return True

        sender.send_message(f"{ColorFormat.RED}You must hold a valid backpack item to check its info.")
        return True

    def handle_reload(self, sender: CommandSender, args: List[str]) -> bool:
        """Command handler for /backpack reload"""
        if not sender.has_permission("ninjosbackpacks.command.reload"):
            sender.send_message(f"{ColorFormat.RED}You do not have permission to use this command.")
            return True

        try:
            self.plugin.reload_config()
            self.config.load()
            sender.send_message(f"{ColorFormat.GREEN}NinjOSBackpacks configuration successfully reloaded.")
            self.logger.info(f"Configuration reloaded by {sender.name}")
        except Exception as e:
            sender.send_message(f"{ColorFormat.RED}Failed to reload config: {e}")
            self.logger.error(f"Error reloading configuration: {e}")

        return True

    def handle_list(self, sender: CommandSender, args: List[str]) -> bool:
        """Command handler for /backpack list"""
        if not sender.has_permission("ninjosbackpacks.command.list"):
            sender.send_message(f"{ColorFormat.RED}You do not have permission to use this command.")
            return True

        items = self.db.list_item_backpacks()

        sender.send_message(f"{ColorFormat.GOLD}=== Registered Backpacks List ===")
        sender.send_message(f"{ColorFormat.YELLOW}Backpacks in Database ({len(items)}):")
        for idx, item in enumerate(items[:15]):  # Limit to 15 entries to avoid spam
            sender.send_message(f"  {ColorFormat.GRAY}- Owner/ID: {ColorFormat.WHITE}{item['backpack_id']} {ColorFormat.GRAY}(Owner UUID: {item['owner_uuid']}, Tier: {item['type']}, Size: {item['size']} slots)")
        if len(items) > 15:
            sender.send_message(f"    {ColorFormat.ITALIC}and {len(items) - 15} more item backpacks...")

        return True

    def handle_cleanup(self, sender: CommandSender, args: List[str]) -> bool:
        """Command handler for /backpack cleanup"""
        if not sender.has_permission("ninjosbackpacks.command.list"):
            sender.send_message(f"{ColorFormat.RED}You do not have permission to use this command.")
            return True

        deleted = self.db.cleanup_orphaned_backpacks()
        sender.send_message(f"{ColorFormat.GREEN}Cleanup completed! Deleted {deleted} empty/orphaned item backpacks older than 30 days.")
        self.logger.info(f"Database cleanup ran by {sender.name}. Removed {deleted} empty records.")
        return True

    # ==========================================
    # IN-GAME CONFIGURATION FORMS (ADMIN MENU)
    # ==========================================

    def handle_config(self, sender: CommandSender, args: List[str]) -> bool:
        """Command handler for /backpack config"""
        if not sender.has_permission("ninjosbackpacks.command.reload"):
            sender.send_message(f"{ColorFormat.RED}You do not have permission to use this command.")
            return True

        if not isinstance(sender, Player):
            sender.send_message(f"{ColorFormat.RED}This command can only be used by players in-game.")
            return True

        self.open_config_menu(sender)
        return True

    def open_config_menu(self, player: Player):
        """Displays main configuration hub menu."""
        form = ActionForm(title="§1NinjOSBackpacks Config Menu")
        
        form.add_button("§2Edit Backpack Tiers\n§8Change material, size, name", "textures/ui/hammer_icon",
                        lambda p: self.open_tiers_menu(p))
        form.add_button("§6Edit Global Rules\n§8Change ownership, nesting, saves", "textures/ui/settings_glyph_color_2x",
                        lambda p: self.open_rules_menu(p))
        form.add_button("§cReload config.toml\n§8Discard changes and reload", "textures/ui/refresh_light",
                        lambda p: self.reload_from_file_menu(p))
        
        player.send_form(form)

    def open_tiers_menu(self, player: Player):
        """Displays lists of currently defined tiers."""
        form = ActionForm(title="§1Backpack/Vault Tiers List")
        
        # Add a button for each configured item backpack tier
        for tier_key, tier_data in self.config.item_backpacks.items():
            material = tier_data.get("material")
            size = tier_data.get("size")
            display_name = tier_data.get("display_name")
            enabled_str = "§aEnabled" if tier_data.get("enabled", True) else "§cDisabled"
            
            button_text = f"{display_name} §r(Key: {tier_key})\n§8[Item Backpack] Material: {material} | Size: {size} | {enabled_str}"
            form.add_button(button_text, "textures/ui/World", 
                            lambda p, tk=tier_key: self.open_tier_edit_form(p, tk, False))
            
        # Add a button for each configured block storage vault tier
        for tier_key, tier_data in self.config.block_storage.items():
            block_type = tier_data.get("block_type")
            size = tier_data.get("size")
            display_name = tier_data.get("display_name")
            enabled_str = "§aEnabled" if tier_data.get("enabled", True) else "§cDisabled"
            
            button_text = f"{display_name} §r(Key: {tier_key})\n§8[Block Vault] Block: {block_type} | Size: {size} | {enabled_str}"
            form.add_button(button_text, "textures/ui/icon_recipe_item", 
                            lambda p, tk=tier_key: self.open_tier_edit_form(p, tk, True))

        form.add_button("§a+ Add New Tier\n§8Create a new custom tier definition", "textures/ui/trade_icon",
                        lambda p: self.open_add_tier_form(p))
        
        form.add_button("§7◀ Back to Main Config\n§8Go back", "textures/ui/left_arrow",
                        lambda p: self.open_config_menu(p))
                        
        player.send_form(form)

    def open_tier_edit_form(self, player: Player, tier_key: str, is_block: bool):
        """Form to edit specific configurations for a single tier."""
        if is_block:
            tier_data = self.config.block_storage.get(tier_key)
        else:
            tier_data = self.config.item_backpacks.get(tier_key)

        if not tier_data:
            player.send_message(f"{ColorFormat.RED}Error: Tier '{tier_key}' not found.")
            return

        form = ModalForm(title=f"Edit Tier: {tier_key}")
        
        form.add_control(TextInput(
            label="Display Name",
            placeholder="e.g. §6Small Backpack",
            default_value=tier_data.get("display_name", "")
        ))
        
        if is_block:
            form.add_control(TextInput(
                label="Block Type ID",
                placeholder="e.g. minecraft:crying_obsidian",
                default_value=tier_data.get("block_type", "")
            ))
        else:
            form.add_control(TextInput(
                label="Item Material ID",
                placeholder="e.g. minecraft:chest",
                default_value=tier_data.get("material", "")
            ))
        
        form.add_control(TextInput(
            label="Storage Size (slots)",
            placeholder="e.g. 27, 54, 90",
            default_value=str(tier_data.get("size", 27))
        ))
        
        if is_block:
            # Block storage does not use lore template, but we can display a reminder
            form.add_control(TextInput(
                label="Lore Reminder (Not stored for block storage)",
                placeholder="Lore is not used for block vaults.",
                default_value="Vault blocks do not require lore templates."
            ))
        else:
            lore_lines = tier_data.get("lore", [])
            lore_str = "\n".join(lore_lines)
            form.add_control(TextInput(
                label="Lore (Use newlines for multiple lines)",
                placeholder="Enter lore template lines...",
                default_value=lore_str
            ))
        
        enabled_val = 0 if tier_data.get("enabled", True) else 1
        form.add_control(Dropdown(
            label="Enabled",
            options=["Yes", "No"],
            default_index=enabled_val
        ))

        form.add_control(Dropdown(
            label="Delete Tier?",
            options=["Keep Tier", "Delete Tier (Danger!)"],
            default_index=0
        ))

        def on_submit(p: Player, data: str):
            try:
                response = json.loads(data)
                display_name = response[0].strip()
                material = response[1].strip()
                size_str = response[2].strip()
                lore_input = response[3].strip()
                enabled_idx = response[4]
                delete_idx = response[5]

                # Deletion handling
                if delete_idx == 1:
                    if is_block:
                        self.config.block_storage.pop(tier_key, None)
                    else:
                        self.config.item_backpacks.pop(tier_key, None)
                    
                    self.config.save()
                    self.plugin.reload_config()
                    self.config.load()
                    p.send_message(f"{ColorFormat.GREEN}✓ Tier '{tier_key}' successfully deleted!")
                    self.open_tiers_menu(p)
                    return

                if not display_name or not material or not size_str:
                    p.send_message(f"{ColorFormat.RED}Failed: Display Name, Material/Block Type, and Size cannot be empty!")
                    self.open_tier_edit_form(p, tier_key, is_block)
                    return

                try:
                    size = int(size_str)
                    if size <= 0:
                        raise ValueError()
                except ValueError:
                    p.send_message(f"{ColorFormat.RED}Failed: Size must be a positive integer.")
                    self.open_tier_edit_form(p, tier_key, is_block)
                    return

                # Update configurations
                if is_block:
                    self.config.block_storage[tier_key] = {
                        "enabled": (enabled_idx == 0),
                        "block_type": material,
                        "display_name": display_name,
                        "size": size
                    }
                else:
                    lore = [line.strip() for line in lore_input.split("\n") if line.strip()]
                    self.config.item_backpacks[tier_key] = {
                        "enabled": (enabled_idx == 0),
                        "material": material,
                        "display_name": display_name,
                        "size": size,
                        "lore": lore
                    }

                # Save to config.toml and reload
                self.config.save()
                self.plugin.reload_config()
                self.config.load()

                p.send_message(f"{ColorFormat.GREEN}✓ Tier '{tier_key}' successfully updated and saved!")
                self.open_tiers_menu(p)
            except Exception as e:
                self.logger.error(f"Error submitting tier edit form: {e}")
                p.send_message(f"{ColorFormat.RED}Error updating tier: {e}")

        form.on_submit = on_submit
        form.on_close = lambda p: self.open_tiers_menu(p)
        player.send_form(form)

    def open_add_tier_form(self, player: Player):
        """Form to add a completely new backpack or vault tier in-game."""
        form = ModalForm(title="Add Custom Backpack/Vault Tier")
        
        form.add_control(Dropdown(
            label="Storage Type",
            options=["Item-based Backpack", "Block-based Storage Vault"],
            default_index=0
        ))

        form.add_control(TextInput(
            label="Tier Key (Lowercase identifier, e.g. 'heavy')",
            placeholder="Enter tier key..."
        ))
        
        form.add_control(TextInput(
            label="Display Name",
            placeholder="e.g. §5Heavy Backpack"
        ))
        
        form.add_control(TextInput(
            label="Material ID / Block Type ID",
            placeholder="e.g. minecraft:shulker_box or minecraft:bedrock"
        ))
        
        form.add_control(TextInput(
            label="Storage Size (slots)",
            placeholder="e.g. 27, 54, 90"
        ))
        
        form.add_control(TextInput(
            label="Lore (For item-based only, use newlines)",
            placeholder="§7A portable heavy container.\n§8Backpack ID: {id}",
            default_value="§7A custom backpack container.\n§8Backpack ID: {id}"
        ))

        def on_submit(p: Player, data: str):
            try:
                response = json.loads(data)
                storage_type_idx = response[0]
                tier_key = response[1].strip().lower()
                display_name = response[2].strip()
                material = response[3].strip()
                size_str = response[4].strip()
                lore_input = response[5].strip()

                if not tier_key or not display_name or not material or not size_str:
                    p.send_message(f"{ColorFormat.RED}Failed: All fields are required to create a new tier!")
                    self.open_add_tier_form(p)
                    return

                if not re.match(r"^[a-z0-9_]+$", tier_key):
                    p.send_message(f"{ColorFormat.RED}Failed: Tier key must contain only lowercase letters, numbers, and underscores.")
                    self.open_add_tier_form(p)
                    return

                if tier_key in self.config.item_backpacks or tier_key in self.config.block_storage:
                    p.send_message(f"{ColorFormat.RED}Failed: Tier '{tier_key}' already exists!")
                    self.open_add_tier_form(p)
                    return

                try:
                    size = int(size_str)
                    if size <= 0:
                        raise ValueError()
                except ValueError:
                    p.send_message(f"{ColorFormat.RED}Failed: Size must be a positive integer.")
                    self.open_add_tier_form(p)
                    return

                # Add and save
                if storage_type_idx == 0:  # Item-based Backpack
                    lore = [line.strip() for line in lore_input.split("\n") if line.strip()]
                    self.config.item_backpacks[tier_key] = {
                        "enabled": True,
                        "material": material,
                        "display_name": display_name,
                        "size": size,
                        "lore": lore
                    }
                else:  # Block-based Storage Vault
                    self.config.block_storage[tier_key] = {
                        "enabled": True,
                        "block_type": material,
                        "display_name": display_name,
                        "size": size
                    }

                self.config.save()
                self.plugin.reload_config()
                self.config.load()

                p.send_message(f"{ColorFormat.GREEN}✓ Custom tier '{tier_key}' successfully created and saved!")
                self.open_tiers_menu(p)
            except Exception as e:
                self.logger.error(f"Error submitting add tier form: {e}")
                p.send_message(f"{ColorFormat.RED}Error adding tier: {e}")

        form.on_submit = on_submit
        form.on_close = lambda p: self.open_tiers_menu(p)
        player.send_form(form)

    def open_rules_menu(self, player: Player):
        """Form to configure rules setting."""
        form = ModalForm(title="Edit Global Rules")
        
        req_owner = 0 if self.config.rules.get("require_owner_for_item_backpacks", True) else 1
        form.add_control(Dropdown(
            label="Require Owner for Item Backpacks",
            options=["Yes", "No"],
            default_index=req_owner
        ))
        
        allow_nesting = 0 if self.config.rules.get("allow_backpack_nesting", False) else 1
        form.add_control(Dropdown(
            label="Allow Backpack Nesting",
            options=["Yes", "No"],
            default_index=allow_nesting
        ))
        
        save_after = 0 if self.config.rules.get("save_after_each_transaction", False) else 1
        form.add_control(Dropdown(
            label="Save After Each Transaction (High Security)",
            options=["Yes", "No"],
            default_index=save_after
        ))

        def on_submit(p: Player, data: str):
            try:
                response = json.loads(data)
                req_owner_idx = response[0]
                allow_nesting_idx = response[1]
                save_after_idx = response[2]

                self.config.rules["require_owner_for_item_backpacks"] = (req_owner_idx == 0)
                self.config.rules["allow_backpack_nesting"] = (allow_nesting_idx == 0)
                self.config.rules["save_after_each_transaction"] = (save_after_idx == 0)

                self.config.save()
                self.plugin.reload_config()
                self.config.load()

                p.send_message(f"{ColorFormat.GREEN}✓ Global rules successfully saved and reloaded!")
                self.open_config_menu(p)
            except Exception as e:
                self.logger.error(f"Error submitting global rules form: {e}")
                p.send_message(f"{ColorFormat.RED}Error updating rules: {e}")

        form.on_submit = on_submit
        form.on_close = lambda p: self.open_config_menu(p)
        player.send_form(form)

    def reload_from_file_menu(self, player: Player):
        """Discards in-memory edits and syncs back from files."""
        try:
            self.plugin.reload_config()
            self.config.load()
            player.send_message(f"{ColorFormat.GREEN}✓ Configuration reloaded successfully from config.toml!")
        except Exception as e:
            player.send_message(f"{ColorFormat.RED}Failed to reload config: {e}")
        self.open_config_menu(player)
