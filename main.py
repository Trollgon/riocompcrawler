import config
import requests
import sqlite3

# https://raider.io/api#/

API_KEY = config.api_key
GUILD_NAME = "profanities"
GUILD_REALM = "kazzak"
GUILD_REGION = "eu"
TIER = "MN_1"

# prepare sqlite
database = "{}.db".format(TIER)
create_table_kills = """
    CREATE TABLE IF NOT EXISTS kills (
    id INTEGER PRIMARY KEY, 
    guild_name text NOT NULL, 
    boss text NOT NULL,
    region text NOT NULL, 
    realm text NOT NULL,
    avg_itemlevel float NOT NULL
);
"""
create_table_comps = """
    CREATE TABLE IF NOT EXISTS kill_to_spec (
    kill_id INTEGER, 
    class_name text NOT NULL,
    spec_name text NOT NULL,
    FOREIGN KEY (kill_id) 
    REFERENCES kills (id) 
        ON DELETE CASCADE 
        ON UPDATE CASCADE
);
"""

try:
    with sqlite3.connect(database) as conn:
        cursor = conn.cursor()
        cursor.execute(create_table_kills)
        cursor.execute(create_table_comps)
        conn.commit()

except sqlite3.OperationalError as e:
    print(e)

# get guild with boss ranks
g = requests.get(
    "https://raider.io/api/guilds/raid-rankings?raid=tier-mn-1&difficulty=mythic&region={}&realm={}&guild={}".format(
        GUILD_REGION, GUILD_REALM, GUILD_NAME))
boss_rankings = g.json()["bossRankings"]

for ranking in boss_rankings:
    current_boss = ranking["boss"]
    guild_rank = ranking["ranks"]["world"]

    print("Starting crawler for {} until WR {}".format(current_boss, guild_rank))

    # fixme: cant check prog pulls, only kills
    # TODO: Live Tracking - Raiding exists now??
    #  -> bugs out/not working properly?

    # get all guilds that prog in tier
    last_limit = guild_rank % 200
    page = 0

    while page < guild_rank / 200:
        print("Starting batch {} of {}.".format(page+1, round(page < guild_rank / 200)+1))
        g = requests.get(
            "https://raider.io/api/v1/raiding/raid-rankings?raid=tier-mn-1&difficulty=mythic&region=world&limit={}&page={}".format(200 if (page + 1) < guild_rank / 200 else last_limit, page))

        j = g.json()

        guilds = []

        for guild_api_response in j["raidRankings"]:
            guild_metadata = {
                "region": guild_api_response["guild"]["region"]["slug"],
                "guild_name": guild_api_response["guild"]["name"],
                "realm": guild_api_response["guild"]["realm"]["slug"]
            }

            guilds.append(guild_metadata)

        # make sure db connection is set up
        cursor = conn.cursor()

        # for all guilds
        for idx, guild in enumerate(guilds):
            region = guild["region"]
            guild_name = guild["guild_name"]
            realm = guild["realm"]

            # get roster for kill
            g = requests.get(
                "https://raider.io/api/v1/guilds/boss-kill?access_key={}&region={}&realm={}&guild={}&raid=tier-mn-1&boss={}&difficulty=mythic".format(
                    API_KEY, region, realm, guild_name, current_boss))

            j = g.json()

            avg_ilvl = j["kill"]["itemLevelEquippedAvg"]
            roster = j["roster"]

            # insert into DB
            # fixme: maybe optimize later to only make one insert?
            guild_insert_stmt = """
                INSERT INTO kills(guild_name, boss, region, realm, avg_itemlevel)
                VALUES(?,?,?,?,?)
            """
            cursor.execute(guild_insert_stmt, (guild_name, current_boss, region, realm, avg_ilvl))
            conn.commit()
            last_saved_kill_id = cursor.lastrowid

            player_insert_stmt = """
                            INSERT INTO kill_to_spec(kill_id, class_name, spec_name)
                            VALUES
                        """
            player_values = []

            for player in roster:
                player_insert_stmt += """(?,?,?),"""
                player_values += [last_saved_kill_id, player["character"]["class"]["name"], player["character"]["spec"]["name"]]

            player_insert_stmt = player_insert_stmt[:-1]
            cursor.execute(player_insert_stmt, player_values)
            conn.commit()


            print("{} out of {} guilds done".format(idx+1, len(guilds)))

        page += 1

print("done")
