/*
 * mod-fly-in-old-world (Tofu Worldview fork of trackmastersteve/mod-fly-in-old-world): flying in Eastern Kingdoms and Kalimdor, gated like Northrend.
 *
 * The core decides whether a flying mount or flight form works in an area in SpellInfo::CheckLocation: the area must have AREA_FLAG_OUTLAND (AreaTableEntry::IsFlyable) and Player::canFlyInZone must agree. canFlyInZone first asks every PlayerScript through OnPlayerCanFlyInZone, then applies the core's own Northrend rule (Cold Weather Flying, 54197).
 *
 * Stock AreaTable has no AREA_FLAG_OUTLAND on Eastern Kingdoms (map 0) or Kalimdor (map 1). The module's SQL (data/sql/db-world) adds it through areatable_dbc rows on the server, and the client needs the same flag from a patched AreaTable.dbc in patch-z.mpq (tools/gen_areatable.py writes both). With the flag in place, this hook is the only gate left for those two maps:
 *   - Enable = 0: nobody flies there (the hook blocks, since the area data alone would let anyone with flying riding skill fly).
 *   - A real player flies there if RequiredSpell is 0 or the player knows RequiredSpell (default 54197, Cold Weather Flying).
 *   - A mod-playerbots bot whose master is a real player flies there only if that master would be allowed (BotsUseMasterPermission = 1). A bot with no real master, a selfbot, or any bot with BotsUseMasterPermission = 0 uses the real-player rule.
 * Outland, Northrend, and every other map are left to the core.
 */

#include "Config.h"
#include "DBCStores.h"
#include "Log.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "SharedDefines.h"

#include "PlayerbotAI.h"
#include "Playerbots.h"

namespace
{
    struct FlyInOldWorldConfig
    {
        bool enabled = true;
        uint32 requiredSpell = 54197; // Cold Weather Flying
        bool botsUseMasterPermission = true;
        bool announce = true;
    };

    // Written on the world thread at startup and on ".reload config"; read by canFlyInZone on map threads. Plain values, as in the core's own config reads.
    FlyInOldWorldConfig config;

    bool IsOldWorld(uint32 mapId, uint32 zoneId)
    {
        uint32 const virtualMap = GetVirtualMapForMapAndZone(mapId, zoneId);
        return virtualMap == MAP_EASTERN_KINGDOMS || virtualMap == MAP_KALIMDOR;
    }

    // The rule for a character acting for itself: no spell needed, or the spell is known in the active talent spec.
    bool MeetsRequirement(Player* player)
    {
        return config.requiredSpell == 0 || player->HasSpell(config.requiredSpell);
    }

    bool MayFlyInOldWorld(Player* player)
    {
        if (!config.enabled)
            return false;

        if (config.botsUseMasterPermission && !IsRealPlayer(player) && !IsSelfBot(player))
        {
            PlayerbotAI* botAI = GET_PLAYERBOT_AI(player);
            Player* master = botAI ? botAI->GetMaster() : nullptr;
            // A bot follows its master's mount, so it inherits the master's permission. Only a real player counts as a master here; a bot whose master is missing, offline, or another bot uses its own rule.
            if (master && master != player && master->IsInWorld() && IsRealPlayer(master))
                return MeetsRequirement(master);
        }

        return MeetsRequirement(player);
    }
}

class FlyInOldWorldPlayerScript : public PlayerScript
{
public:
    FlyInOldWorldPlayerScript() : PlayerScript("FlyInOldWorldPlayerScript", { PLAYERHOOK_ON_CAN_PLAYER_FLY_IN_ZONE }) { }

    bool OnPlayerCanFlyInZone(Player* player, uint32 mapId, uint32 zoneId, SpellInfo const* /*bySpell*/) override
    {
        if (!player || !IsOldWorld(mapId, zoneId))
            return true; // not ours: the core's own rules decide

        return MayFlyInOldWorld(player);
    }
};

class FlyInOldWorldWorldScript : public WorldScript
{
public:
    FlyInOldWorldWorldScript() : WorldScript("FlyInOldWorldWorldScript", { WORLDHOOK_ON_AFTER_CONFIG_LOAD }) { }

    void OnAfterConfigLoad(bool reload) override
    {
        config.enabled = sConfigMgr->GetOption<bool>("FlyInOldWorld.Enable", true);
        config.requiredSpell = sConfigMgr->GetOption<uint32>("FlyInOldWorld.RequiredSpell", 54197);
        config.botsUseMasterPermission = sConfigMgr->GetOption<bool>("FlyInOldWorld.BotsUseMasterPermission", true);
        config.announce = sConfigMgr->GetOption<bool>("FlyInOldWorld.Announce", true);

        if (config.announce)
            LOG_INFO("module", "mod-fly-in-old-world: {} (enabled {}, required spell {}, bots use master permission {}).", reload ? "config reloaded" : "loaded", config.enabled ? 1 : 0, config.requiredSpell, config.botsUseMasterPermission ? 1 : 0);
    }
};

void AddFlyInOldWorld()
{
    new FlyInOldWorldPlayerScript();
    new FlyInOldWorldWorldScript();
}
