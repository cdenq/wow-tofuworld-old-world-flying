# mod-fly-in-old-world (Tofu Worldview fork)

Flying in Eastern Kingdoms and Kalimdor for AzerothCore (3.3.5a, mod-playerbots fork), gated like Northrend: by default a character needs Cold Weather Flying (54197). Fork of [trackmastersteve/mod-fly-in-old-world](https://github.com/trackmastersteve/mod-fly-in-old-world), branch `tofu`. Installs as `modules/mod-fly-in-old-world` (loader `Addmod_fly_in_old_worldScripts`). Requires mod-playerbots in the same build.

## How it works

The core lets a flying mount or flight form work in an area only if the area has `AREA_FLAG_OUTLAND` (0x400) in AreaTable and `Player::canFlyInZone` agrees; `canFlyInZone` asks every `PlayerScript` through `OnPlayerCanFlyInZone` before its own Northrend check. The client checks the same AreaTable flag before it lets anyone take off.

1. Area data. `tools/gen_areatable.py` reads the server's stock `AreaTable.dbc` and sets 0x400 on every record with ContinentID 0 or 1 (972 records at build 12340: Eastern Kingdoms 499, Kalimdor 473). It writes:
   - `data/sql/db-world/tofu_fiow_01_areatable_flyable.sql`: full-record `areatable_dbc` rows (a database row replaces the whole DBC record with that ID), DELETE by ID list then INSERT, so it is re-runnable. The worldserver updater applies it as a module file.
   - with `--dbc`, the patched client `AreaTable.dbc`, which goes into the client data patch as `DBFilesClient\AreaTable.dbc` (Tofu Worldview: `build_patches.sh` step 1b puts it in `patch-z.mpq`).
   - Tofu Worldview addition, not part of flying: the areas in `SANCTUARY_AREAS` (GM Island, 876) also get `AREA_FLAG_SANCTUARY` (0x800), so players, their pets, and bots cannot attack each other there whatever their PvP flag; duels still work, and the client shows "(Sanctuary)" once the patched `AreaTable.dbc` is installed. It is here because this file owns the full `areatable_dbc` record of every old-world area; a second SQL file writing the same row would be overwritten whenever this one re-applies. Removing the module also removes the sanctuary.
2. The gate (`src/FlyInOldWorld.cpp`). For Eastern Kingdoms and Kalimdor only:
   - `FlyInOldWorld.Enable = 0`: nobody flies there. The area data alone would let anyone with flying riding skill fly, so the switch blocks rather than doing nothing.
   - A real player may fly if `FlyInOldWorld.RequiredSpell` is 0 or the player knows it in the active talent spec.
   - A mod-playerbots bot whose master is a real player may fly exactly when its master may (`FlyInOldWorld.BotsUseMasterPermission = 1`). Bots copy their master's mount, so your bots fly with you and a friend's bots stay on the ground when that friend cannot fly. Bots without a real master and selfbots use the real-player rule.
   - Outland, Northrend, and every other map are left to the core.

## What the fork changed from upstream

Upstream taught a custom spell 200001 from a "Tome of Old World Flight" (item 900002, sold by four vendors) and patched Spell.dbc and AreaTable.dbc with `patch_dbc.py`. That design is removed:

- The tome could not be used: its `item_template` row had no on-use spell, and `HandleUseItemOpcode` drops a use packet whose spell ID is unknown before any item script runs.
- Its "reading" visual, spell 7355, is Stuck (the `.unstuck` spell): cast triggered, it hearths the player.
- `addSpell(200001, 1, ...)` stored the spell for talent spec 1 only, and `HasSpell` checks the active spec, so dual-spec characters lost flying in their second spec.
- If the server lacked spell 200001, the tome was still destroyed and the success message still shown.
- `patch_dbc.py` cloned spell 68907 and blanked any field equal to 762, 225, 300, or 68, whatever the field meant.
- The conf held only the module template's unused `MyModule.Enable`.

## Install

1. Place the repo at `modules/mod-fly-in-old-world`, re-run CMake, and build.
2. Copy `conf/mod_fly_in_old_world.conf.dist` to the server's `configs/modules` as `mod_fly_in_old_world.conf`.
3. Start the worldserver: the updater applies `tofu_fiow_01_areatable_flyable.sql`.
4. Ship the patched `AreaTable.dbc` to every client (Tofu Worldview: `./publish.sh --retail`, which runs `build_patches.sh`). Without it the client refuses to take off in the old world even when the server allows it.

Checks:

- Startup log: `mod-fly-in-old-world: loaded (enabled 1, required spell 54197, bots use master permission 1).`
- `SELECT COUNT(*) FROM acore_world.areatable_dbc WHERE ContinentID IN (0, 1) AND (Flags & 1024) <> 0;` returns 972.
- In game with `.gm off`: a character with Cold Weather Flying takes off in Elwynn Forest and Durotar; one without it gets "You can't use that here"; with `FlyInOldWorld.Enable = 0` and `.reload config` nobody flies in the old world while Outland and Northrend still work.

## Regenerating and removing

- Regenerate only from the server's stock `AreaTable.dbc` (the script refuses an already patched copy): `python tools/gen_areatable.py --stock <server>/Data/dbc/AreaTable.dbc --sql data/sql/db-world/tofu_fiow_01_areatable_flyable.sql --revert revert/revert_tofu_fiow_01_areatable_flyable.sql`.
- Removal: take the module out of the build, run `revert/revert_tofu_fiow_01_areatable_flyable.sql` (it lives outside `data/sql`, so the updater never applies it), restart, and drop `AreaTable.dbc` from the client patch.
