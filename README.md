<!-- endstone-professional-header:start -->
<p align="center">
  <img src="docs/assets/banner.svg" width="100%" alt="Endstone Ninjo's Backpacks &mdash; High-fidelity SQLite/MySQL-backed backpacks plugin utilizing endstone-inventoryui">
</p>

<p align="center">
  <a href="https://github.com/TheNINJALLO/endstone-ninjos-backpacks/actions/workflows/wheel-release.yml"><img alt="Build" src="https://img.shields.io/github/actions/workflow/status/TheNINJALLO/endstone-ninjos-backpacks/wheel-release.yml?branch=main&amp;style=for-the-badge&amp;logo=githubactions&amp;logoColor=white&amp;label=Build"></a>
  <a href="https://github.com/TheNINJALLO/endstone-ninjos-backpacks/releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/TheNINJALLO/endstone-ninjos-backpacks?display_name=tag&amp;style=for-the-badge&amp;label=Release"></a>
</p>

<p align="center">
  <img alt="Endstone 0.11.9" src="https://img.shields.io/badge/Endstone-0.11.9-52b7a8?style=flat-square">
  <img alt="API 0.11" src="https://img.shields.io/badge/API-0.11-63b8ff?style=flat-square">
  <img alt="BDS 1.26.44" src="https://img.shields.io/badge/BDS-1.26.44-8b7dff?style=flat-square">
  <img alt="Python >=3.11" src="https://img.shields.io/badge/Python-%3E=3.11-3776AB?style=flat-square&amp;logo=python&amp;logoColor=white">
</p>

<p align="center">
  <strong>High-fidelity SQLite/MySQL-backed backpacks plugin utilizing endstone-inventoryui.</strong>
</p>

<p align="center">
  <a href="#what-it-does">What it does</a> &bull;
  <a href="#how-to-use">How to use</a> &bull;
  <a href="#commands-and-permissions">Commands</a> &bull;
  <a href="#install">Install</a> &bull;
  <a href="https://github.com/TheNINJALLO/endstone-ninjos-backpacks/releases">Releases</a>
</p>

## Overview

High-fidelity SQLite/MySQL-backed backpacks plugin utilizing endstone-inventoryui. This release is aligned with Endstone 0.11.9 and Minecraft Bedrock Dedicated Server 1.26.44, and is distributed as a Python wheel for direct installation in an Endstone server.

## What it does

- Provides persistent, tiered player backpacks backed by SQLite or MySQL.
- Preserves item data through high-fidelity serialization and InventoryUI menus.
- Adds linked advanced hoppers plus staff inventory and ender-chest management.

## How to use

1. Install `endstone-inventoryui`; install `blockdata-api` too when its integration is wanted.
2. Start once, review the generated backpack tiers, item mappings, and optional MySQL settings, then restart.
3. Players open their storage with `/backpack`; staff assign tiers and administer stored backpacks through its subcommands.
4. Use `/hopper link` while targeting the intended containers, and reserve `/manageinv` for staff.

## Commands and permissions

| Command / usage | What it does | Access |
|---|---|---|
| `/backpack`<br>`/backpack assign [player: player] [tier: str] [extra_lore: message]`<br>`/backpack config`<br>`/backpack open [player_name: str] [tier: str]`<br>`/backpack delete [player_name: str] [tier: str]`<br>`/backpack info`<br>`/backpack reload`<br>`/backpack list`<br>`/backpack cleanup` | Main command for NinjOSBackpacks | `ninjosbackpacks.command` |
| `/hopper`<br>`/hopper info`<br>`/hopper link`<br>`/hopper unlink`<br>`/hopper reload`<br>`/hopper list`<br>`/hopper debug [state: str]` | Control Advanced Hoppers | `ninjoshopper.use` |
| `/manageinv` | Open inventory management interface | `ninjosbackpacks.admin.inv` |

## Compatibility

| Component | Supported version |
|---|---|
| Endstone | `0.11.9` |
| Endstone API | `0.11` |
| Bedrock Dedicated Server | `1.26.44` |
| Python | `>=3.11` |
| Plugin release | `v1.0.90` |

## Install

Download both required wheels over HTTPS:

- [InventoryUI `v2.0.6`](https://github.com/TheNINJALLO/endstone-inventoryui/releases/download/v2.0.6/endstone_inventoryui-2.0.6-py3-none-any.whl)
- [Ninjo's Backpacks `v1.0.90`](https://github.com/TheNINJALLO/endstone-ninjos-backpacks/releases/download/v1.0.90/endstone_ninjos_backpacks-1.0.90-py3-none-any.whl)

Copy the downloaded wheel into the server's `plugins/` directory, remove any older wheel for the same plugin, and restart Endstone.

> [!IMPORTANT]
> Remove older InventoryUI and Backpacks wheels before installing these releases. Use Endstone `0.11.9` with BDS `1.26.44`, and back up worlds and plugin data before upgrading a production server.

## Configuration and secrets

Runtime databases, logs, local `.env` files, server directories, and root `config.toml` files are excluded from source releases. When an example configuration is provided, copy it locally and keep live tokens, passwords, webhook URLs, and server identifiers out of Git.

## Release automation

Every `v*` tag runs [the wheel release workflow](.github/workflows/wheel-release.yml), builds the package in a clean GitHub runner, stores the wheel as a workflow artifact, and attaches it to the matching GitHub release.
<!-- endstone-professional-header:end -->
