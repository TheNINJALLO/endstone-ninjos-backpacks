from pathlib import Path
from typing import Dict, Any, List

class Config:
    def __init__(self, plugin):
        self.plugin = plugin
        self.item_backpacks: Dict[str, Dict[str, Any]] = {}
        self.rules: Dict[str, Any] = {}
        self.navigation: Dict[str, str] = {}
        self.block_storage: Dict[str, Dict[str, Any]] = {}
        self.load()

    def load(self) -> None:
        """Load and parse configuration values from Endstone."""
        config = self.plugin.config

        # 1. Parse item backpacks definitions
        item_bp = config.get("item_backpacks", {})
        self.item_backpacks = {}
        for key, value in item_bp.items():
            if not isinstance(value, dict):
                continue
            self.item_backpacks[key] = {
                "enabled": value.get("enabled", True),
                "material": value.get("material", "minecraft:chest"),
                "display_name": value.get("display_name", f"§6{key.capitalize()} Backpack"),
                "size": value.get("size", 27),
                "lore": value.get("lore", ["§7A portable storage backpack.", "§8Backpack ID: {id}"])
            }

        # 2. Parse rules
        rules = config.get("rules", {})
        self.rules = {
            "require_owner_for_item_backpacks": rules.get("require_owner_for_item_backpacks", True),
            "allow_backpack_nesting": rules.get("allow_backpack_nesting", False),
            "save_after_each_transaction": rules.get("save_after_each_transaction", False)
        }

        # 3. Parse navigation item icons
        nav = config.get("navigation", {})
        self.navigation = {
            "previous_item": nav.get("previous_item", "minecraft:feather"),
            "next_item": nav.get("next_item", "minecraft:feather"),
            "page_item": nav.get("page_item", "minecraft:book")
        }

        # 4. Parse block storage definitions
        block_store = config.get("block_storage", {})
        if not block_store:
            block_store = {
                "vault_small": {
                    "enabled": True,
                    "block_type": "minecraft:crying_obsidian",
                    "display_name": "§dSmall Block Vault",
                    "size": 27
                },
                "vault_large": {
                    "enabled": True,
                    "block_type": "minecraft:lodestone",
                    "display_name": "§bLarge Block Vault",
                    "size": 54
                },
                "vault_gigantic": {
                    "enabled": True,
                    "block_type": "minecraft:respawn_anchor",
                    "display_name": "§cGigantic Block Vault",
                    "size": 90
                }
            }

        self.block_storage = {}
        for key, value in block_store.items():
            if not isinstance(value, dict):
                continue
            self.block_storage[key] = {
                "enabled": value.get("enabled", True),
                "block_type": value.get("block_type", "minecraft:crying_obsidian"),
                "display_name": value.get("display_name", f"§6{key.capitalize()} Vault"),
                "size": value.get("size", 27)
            }

        # 5. Parse virtual stacks config
        vs = config.get("virtual_stacks", {})
        self.virtual_stacks = {
            "enabled": vs.get("enabled", True),
            "apply_to_block_containers": vs.get("apply_to_block_containers", True),
            "apply_to_item_backpacks": vs.get("apply_to_item_backpacks", False),
            "max_amount_per_slot": vs.get("max_amount_per_slot", 900),
            "withdraw_stack_at_a_time": vs.get("withdraw_stack_at_a_time", True),
            "default_withdraw_amount": vs.get("default_withdraw_amount", 64),
            "use_item_max_stack_size_for_withdraw": vs.get("use_item_max_stack_size_for_withdraw", True),
            "show_virtual_amount_in_lore": vs.get("show_virtual_amount_in_lore", True),
            "display_stack_amount": vs.get("display_stack_amount", 1),
            "allow_virtual_stacking_of_unstackables": vs.get("allow_virtual_stacking_of_unstackables", False)
        }

        # 6. Parse MySQL config
        mysql = config.get("mysql", {})
        self.mysql = {
            "enabled": mysql.get("enabled", False),
            "host": mysql.get("host", "localhost"),
            "port": mysql.get("port", 3306),
            "user": mysql.get("user", "root"),
            "password": mysql.get("password", ""),
            "database": mysql.get("database", "player_data")
        }

    def save(self) -> None:
        """Write the current in-memory configurations back to config.toml on disk."""
        config_path = self.plugin.data_folder / "config.toml"
        
        lines = []
        for tier, settings in self.item_backpacks.items():
            lines.append(f"[item_backpacks.{tier}]")
            enabled_val = "true" if settings.get("enabled", True) else "false"
            lines.append(f"enabled = {enabled_val}")
            lines.append(f'material = "{settings.get("material")}"')
            lines.append(f'display_name = "{settings.get("display_name")}"')
            lines.append(f'size = {settings.get("size")}')
            
            # Format lore array
            lore_lines = [f'    "{line}"' for line in settings.get("lore", [])]
            lore_str = ",\n".join(lore_lines)
            lines.append(f"lore = [\n{lore_str}\n]")
            lines.append("")

        for tier, settings in self.block_storage.items():
            lines.append(f"[block_storage.{tier}]")
            enabled_val = "true" if settings.get("enabled", True) else "false"
            lines.append(f"enabled = {enabled_val}")
            lines.append(f'block_type = "{settings.get("block_type")}"')
            lines.append(f'display_name = "{settings.get("display_name")}"')
            lines.append(f'size = {settings.get("size")}')
            lines.append("")

        lines.append("[navigation]")
        for k, v in self.navigation.items():
            lines.append(f'{k} = "{v}"')
        lines.append("")

        lines.append("[rules]")
        for k, v in self.rules.items():
            if isinstance(v, bool):
                val_str = "true" if v else "false"
            else:
                val_str = str(v)
            lines.append(f"{k} = {val_str}")
        lines.append("")

        lines.append("[virtual_stacks]")
        for k, v in self.virtual_stacks.items():
            if isinstance(v, bool):
                val_str = "true" if v else "false"
            else:
                val_str = str(v)
            lines.append(f"{k} = {val_str}")
        lines.append("")

        if hasattr(self, "mysql"):
            lines.append("[mysql]")
            enabled_str = "true" if self.mysql.get("enabled", False) else "false"
            lines.append(f"enabled = {enabled_str}")
            lines.append(f'host = "{self.mysql.get("host", "localhost")}"')
            lines.append(f'port = {self.mysql.get("port", 3306)}')
            lines.append(f'user = "{self.mysql.get("user", "root")}"')
            lines.append(f'password = "{self.mysql.get("password", "")}"')
            lines.append(f'database = "{self.mysql.get("database", "player_data")}"')
            lines.append("")

        toml_content = "\n".join(lines)

        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(toml_content)
            self.plugin.logger.info("Configuration written successfully to config.toml")
        except Exception as e:
            self.plugin.logger.error(f"Failed to write config.toml: {e}")
