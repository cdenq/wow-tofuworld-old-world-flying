"""Generate mod-fly-in-old-world's area data from the server's stock AreaTable.dbc (3.3.5a, build 12340).

Every AreaTable record on Eastern Kingdoms (ContinentID 0) or Kalimdor (ContinentID 1) gets AREA_FLAG_OUTLAND (0x400), which is the only thing the core (AreaTableEntry::IsFlyable) and the client check to treat an area as flyable. Nothing else in a record changes.

Outputs (each optional):
  --sql     server side: full-record areatable_dbc rows for those areas (a row replaces the whole DBC record with that ID), as DELETE by ID list then INSERT, so the file gives the same result however often it runs
  --revert  DELETE of the same IDs (areatable_dbc is empty in stock AzerothCore, so this restores stock)
  --dbc     client side: the patched AreaTable.dbc for patch-z.mpq (DBFilesClient\\AreaTable.dbc)

Usage (Git Bash on the host, from the repo root):
  python tools/gen_areatable.py --stock "/c/Build/bin/RelWithDebInfo/Data/dbc/AreaTable.dbc" --sql data/sql/db-world/tofu_fiow_01_areatable_flyable.sql --revert revert/revert_tofu_fiow_01_areatable_flyable.sql
  python tools/gen_areatable.py --stock "/c/Build/bin/RelWithDebInfo/Data/dbc/AreaTable.dbc" --dbc work/AreaTable.dbc
Always start from the server's stock file, never from an already patched copy (the script refuses a file whose old-world records already carry the flag on every record).
"""
import argparse, hashlib, struct, sys

AREA_FLAG_OUTLAND = 0x400
FIELD_COUNT = 36
RECORD_SIZE = FIELD_COUNT * 4
OLD_WORLD = (0, 1)

# Column order of acore_world.areatable_dbc at core 32fd347 (one column per DBC field). Type: i int32, u uint32, f float, s string offset.
COLUMNS = [
    ('ID', 'i'), ('ContinentID', 'i'), ('ParentAreaID', 'i'), ('AreaBit', 'i'), ('Flags', 'i'),
    ('SoundProviderPref', 'i'), ('SoundProviderPrefUnderwater', 'i'), ('AmbienceID', 'i'), ('ZoneMusic', 'i'), ('IntroSound', 'i'), ('ExplorationLevel', 'i'),
] + [('AreaName_Lang_' + loc, 's') for loc in ('enUS', 'enGB', 'koKR', 'frFR', 'deDE', 'enCN', 'zhCN', 'enTW', 'zhTW', 'esES', 'esMX', 'ruRU', 'ptPT', 'ptBR', 'itIT', 'Unk')] + [
    ('AreaName_Lang_Mask', 'u'), ('FactionGroupMask', 'i'),
    ('LiquidTypeID_1', 'i'), ('LiquidTypeID_2', 'i'), ('LiquidTypeID_3', 'i'), ('LiquidTypeID_4', 'i'),
    ('MinElevation', 'f'), ('Ambient_Multiplier', 'f'), ('Lightid', 'i'),
]
assert len(COLUMNS) == FIELD_COUNT
FLAGS = 4
CONTINENT = 1


def read_dbc(path):
    raw = open(path, 'rb').read()
    magic, count, fields, size, str_size = struct.unpack_from('<4sIIII', raw, 0)
    if magic != b'WDBC' or fields != FIELD_COUNT or size != RECORD_SIZE:
        sys.exit('%s is not a 3.3.5a AreaTable.dbc (magic %r, %d fields, record size %d)' % (path, magic, fields, size))
    if len(raw) != 20 + count * size + str_size:
        sys.exit('%s has the wrong length for its header' % path)
    records = [bytearray(raw[20 + i * size:20 + (i + 1) * size]) for i in range(count)]
    strings = raw[20 + count * size:]
    return raw, records, strings


def string_at(strings, offset):
    end = strings.index(b'\0', offset)
    return strings[offset:end].decode('utf-8')


def sql_value(kind, rec, idx, strings):
    if kind == 's':
        text = string_at(strings, struct.unpack_from('<I', rec, idx * 4)[0])
        return "'" + text.replace('\\', '\\\\').replace("'", "''") + "'"
    if kind == 'f':
        return '%.9g' % struct.unpack_from('<f', rec, idx * 4)[0]
    if kind == 'u':
        return str(struct.unpack_from('<I', rec, idx * 4)[0])
    return str(struct.unpack_from('<i', rec, idx * 4)[0])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--stock', required=True, help="the server's stock AreaTable.dbc")
    ap.add_argument('--sql')
    ap.add_argument('--revert')
    ap.add_argument('--dbc')
    a = ap.parse_args()

    raw, records, strings = read_dbc(a.stock)
    stock_sha1 = hashlib.sha1(raw).hexdigest()

    targets = []  # (index, id, stock flags)
    for i, rec in enumerate(records):
        cont = struct.unpack_from('<i', rec, CONTINENT * 4)[0]
        if cont in OLD_WORLD:
            targets.append((i, struct.unpack_from('<i', rec, 0)[0], struct.unpack_from('<I', rec, FLAGS * 4)[0]))
    if not targets:
        sys.exit('no Eastern Kingdoms or Kalimdor records found')
    already = sum(1 for _, _, f in targets if f & AREA_FLAG_OUTLAND)
    if already == len(targets):
        sys.exit('every old-world record already has 0x400: this is a patched copy, start from the stock file')
    ids = sorted(t[1] for t in targets)
    per_map = {m: sum(1 for i, _, _ in targets if struct.unpack_from('<i', records[i], CONTINENT * 4)[0] == m) for m in OLD_WORLD}

    for i, _, flags in targets:
        struct.pack_into('<I', records[i], FLAGS * 4, flags | AREA_FLAG_OUTLAND)

    print('stock AreaTable.dbc: %d records, sha1 %s' % (len(records), stock_sha1))
    print('old-world records: %d (Eastern Kingdoms %d, Kalimdor %d); already flagged in stock: %d' % (len(targets), per_map[0], per_map[1], already))

    id_list = ','.join(str(x) for x in ids)
    check = 'SELECT COUNT(*) FROM acore_world.areatable_dbc WHERE ContinentID IN (0, 1) AND (Flags & 1024) <> 0; -- expected %d' % len(targets)

    if a.sql:
        cols = ', '.join('`%s`' % c for c, _ in COLUMNS)
        rows = []
        for i, _, _ in sorted(targets, key=lambda t: t[1]):
            rows.append('(' + ', '.join(sql_value(k, records[i], n, strings) for n, (_, k) in enumerate(COLUMNS)) + ')')
        with open(a.sql, 'w', encoding='utf-8', newline='\n') as f:
            f.write('-- mod-fly-in-old-world (Tofu Worldview fork): make every Eastern Kingdoms and Kalimdor area flyable on the server.\n')
            f.write('-- Changes: areatable_dbc gets the full stock record of each of the %d AreaTable.dbc records with ContinentID 0 or 1 (Eastern Kingdoms %d, Kalimdor %d), with Flags |= 0x400 (AREA_FLAG_OUTLAND, the flag AreaTableEntry::IsFlyable checks). Nothing else changes. Whether a character may actually fly there is decided by the module (FlyInOldWorld.* in mod_fly_in_old_world.conf).\n' % (len(targets), per_map[0], per_map[1]))
            f.write('-- Schema: acore_world. A DB row replaces the whole DBC record with the same ID, so each row carries the full record.\n')
            f.write('-- Generated by tools/gen_areatable.py from the server stock AreaTable.dbc, sha1 %s. Re-runnable: DELETE by ID list, then INSERT fixed values.\n' % stock_sha1)
            f.write('-- Needs: worldserver restart (DBC stores load at startup). Clients need the matching AreaTable.dbc in patch-z.mpq, or they refuse to take off.\n')
            f.write('-- Check: %s\n' % check)
            f.write('-- Revert: revert/revert_tofu_fiow_01_areatable_flyable.sql\n\n')
            f.write('DELETE FROM `areatable_dbc` WHERE `ID` IN (%s);\n\n' % id_list)
            f.write('INSERT INTO `areatable_dbc` (%s) VALUES\n' % cols)
            f.write(',\n'.join(rows) + ';\n')
        print('wrote %s (%d rows)' % (a.sql, len(rows)))

    if a.revert:
        with open(a.revert, 'w', encoding='utf-8', newline='\n') as f:
            f.write('-- Revert of mod-fly-in-old-world tofu_fiow_01_areatable_flyable.sql: removes its %d areatable_dbc rows, so Eastern Kingdoms and Kalimdor use the stock DBC records again (areatable_dbc is empty in stock).\n' % len(targets))
            f.write('-- Schema: acore_world. Run by hand after removing the module (this file lives outside data/sql, so the updater never applies it). Needs: worldserver restart.\n')
            f.write('-- Check: SELECT COUNT(*) FROM acore_world.areatable_dbc WHERE ID IN (%s); -- expected 0\n\n' % id_list)
            f.write('DELETE FROM `acore_world`.`areatable_dbc` WHERE `ID` IN (%s);\n' % id_list)
        print('wrote %s' % a.revert)

    if a.dbc:
        with open(a.dbc, 'wb') as f:
            f.write(raw[:20])
            for rec in records:
                f.write(rec)
            f.write(strings)
        print('wrote %s, sha1 %s' % (a.dbc, hashlib.sha1(open(a.dbc, 'rb').read()).hexdigest()))


if __name__ == '__main__':
    main()
