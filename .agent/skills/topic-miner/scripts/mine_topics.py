#!/usr/bin/env python3
"""
mine_topics.py - Tactical History & Ancient Warfare Topic Miner

Selects, structures, and outputs niche tactical military anomalies into state/topic.json.
"""

import argparse
import json
import os
import random
import sys
from pathlib import Path

TOPIC_CATALOG = [
    {
        "id": "archimedes-claw",
        "title": "The Claw of Archimedes: Rome's Maritime Nightmare",
        "category": "siege_engine",
        "historical_era": "Second Punic War (214-212 BC)",
        "core_anomaly": "A fortified counterweight crane with an iron grapple that lifted Roman galleys vertically from the water and smashed them back down.",
        "hook_hookline": "In 213 BC, the Roman navy attacked Syracuse—only to be plucked out of the sea like toys by an invisible iron hand.",
        "key_facts": [
            "Conceived by Archimedes to defend Syracuse against Roman General Marcellus.",
            "Leveraged pulley mechanics and counterweight stones behind high coastal battlements.",
            "Caused psychological terror; Roman legionaries fled at the sight of any timber pole extending over the wall."
        ],
        "visual_motifs": [
            "Roman war galleys approaching stone coastal ramparts under dark stormy skies",
            "Enormous wooden boom dropping an iron talon grappling hook onto a Roman ship prow",
            "Warship tilted 90 degrees skyward, spilling armored legionaries into churning ocean waves",
            "Archimedes calculating with compass and parchment atop stone watchtower overlooking carnage"
        ]
    },
    {
        "id": "battle-of-carrhae-camel-train",
        "title": "Surena's Infinite Arrow Camel Train at Carrhae",
        "category": "tactical_anomaly",
        "historical_era": "Late Roman Republic (53 BC)",
        "core_anomaly": "Parthian General Surena solved the archer ammunition limit by stationing a reserve train of 1,000 baggage camels carrying millions of arrows.",
        "hook_hookline": "Crassus thought the Parthian horse archers would run out of arrows. He didn't know about the thousand camels behind the dunes.",
        "key_facts": [
            "Marcus Licinius Crassus formed a massive Roman square expecting archers to deplete quivers.",
            "General Surena set up an unbroken logistical conveyor belt using 1,000 Arabian baggage camels.",
            "Roman shields were pinned to legionaries' hands and boots to the ground under non-stop armor-piercing composite bow fire."
        ],
        "visual_motifs": [
            "Roman testudo formation baking under blinding desert sun in Mesopotamia",
            "Parthian horse archers circling at full gallop performing the Parthian shot",
            "Endless caravan of camels laden with wicker baskets overflowing with iron-tipped arrows",
            "Shattered Roman scuta shields bristling with dozens of arrows under blood-red sunset"
        ]
    },
    {
        "id": "byzantine-cheirosiphona",
        "title": "The Cheirosiphona: Medieval Byzantium's Handheld Flamethrower",
        "category": "bizarre_invention",
        "historical_era": "Byzantine Empire (10th Century AD)",
        "core_anomaly": "A portable brass hand-pumped siphon weapon that sprayed unquenchable Greek Fire directly into enemy battle ranks.",
        "hook_hookline": "A thousand years before modern flamethrowers, Byzantine shock troops burned enemy shield walls alive with brass hand pumps.",
        "key_facts": [
            "Documented in Emperor Leo VI's military treatise, the Tactica.",
            "Chambered pressurized petroleum, resin, and quicklime ignited by a front-mounted brazier nozzle.",
            "Water could not extinguish the chemical blaze, causing instant panic in tight infantries."
        ],
        "visual_motifs": [
            "Byzantine cataphract and shock troops clad in gilded iron scale armor",
            "Soldier bearing a polished bronze hand siphon spewing a roaring jet of green and orange chemical fire",
            "Enemy Viking and Arab boarding parties recoiling in horror as wooden ships catch fire on water",
            "Dense smoke and volumetric glowing embers illuminating the Golden Horn harbor"
        ]
    },
    {
        "id": "battle-of-pelusium-cat-shields",
        "title": "The Sacred Cat Shields of Pelusium",
        "category": "tactical_anomaly",
        "historical_era": "Achaemenid Persian Empire (525 BC)",
        "core_anomaly": "Cambyses II exploited Egyptian religious devotion to Bastet by painting cats on shields and driving sacred animals ahead of Persian vanguard.",
        "hook_hookline": "Persian invaders conquered Egypt using a forbidden sacred weapon.",
        "key_facts": [
            "Persian King Cambyses II faced Pharaoh Psamtik III at the fortified delta city of Pelusium.",
            "Persian soldiers held cats, dogs, and ibises in their arms or painted Bastet's visage on bronze shields.",
            "Egyptian archers refused to loose arrows for fear of wounding sacred animals, collapsing the garrison line."
        ],
        "visual_motifs": [
            "Persian Immortals advancing across Nile delta sands with painted feline icons on wicker shields",
            "Egyptian archers atop limestone ramparts lowering their composite bows in despair",
            "Temple of Bastet towering in background with mystical desert dust and sun rays",
            "Persian vanguard breaking through untouched gates in triumphant dusk lighting"
        ]
    },
    {
        "id": "flaming-war-pigs-megara",
        "title": "The Flaming War Pigs of Megara",
        "category": "bizarre_invention",
        "historical_era": "Hellenistic Warfare (266 BC)",
        "core_anomaly": "Megarian defenders doused swine in pitch, set them ablaze, and released them to panic Antigonus Gonatas' terrifying war elephant phalanx.",
        "hook_hookline": "When an army of giant war elephants besieged their city, Greek defenders defeated them with squealing, flaming pigs.",
        "key_facts": [
            "Antigonus II Gonatas besieged Megara with towering Indian war elephants clad in iron plates.",
            "Pigs coated in combustible crude tar were unleashed screeching directly into the elephant columns.",
            "The terrified pachyderms trampled their own Macedonian infantry in uncontrollable stampedes."
        ],
        "visual_motifs": [
            "Massive war elephants towering over Greek stone city gates, iron tusk spikes glinting",
            "Torches igniting pitch as Megarian hoplites open low sally ports",
            "Blazing stampede creating pandemonium among rearing elephants and fleeing armored lines",
            "Dramatic night battlefield illuminated by raging fires and billowing black pitch smoke"
        ]
    },
    {
        "id": "red-cliffs-fire-ships",
        "title": "Huang Gai's Deceptive Fire Ships at the Battle of Red Cliffs",
        "category": "tactical_anomaly",
        "historical_era": "Three Kingdoms China (208 AD)",
        "core_anomaly": "General Huang Gai feigned defection to Cao Cao, steering twenty warships packed with dry reeds, tallow, and oil into Cao Cao's chained armada before setting them ablaze in a sudden wind.",
        "hook_hookline": "In 208 AD, warlord Cao Cao chained eight hundred warships together to stop seasickness—turning his armada into history's greatest floating furnace.",
        "key_facts": [
            "Cao Cao chained his navy stem-to-stern across the Yangtze River to stabilize northern troops unaccustomed to waves.",
            "Southern warlord Zhou Yu and veteran general Huang Gai staged a fake defection letter to approach unchallenged.",
            "A sudden southeasterly wind whipped the ignited pitch ships directly into the chained armada, incinerating hundreds of thousands."
        ],
        "visual_motifs": [
            "Colossal chained fleet of Han dynasty warships spanning across misty Yangtze river",
            "Twenty dragon-prowed strike vessels sailing rapidly under billowing night wind",
            "Huang Gai ordering torches dropped onto straw-stuffed decks bursting into roaring chemical inferno",
            "Chained flotilla trapped in an inescapable wall of flame, burning flags tumbling into night water",
            "General Zhou Yu observing the glowing apocalyptic horizon from limestone cliffs"
        ]
    },
    {
        "id": "turtle-ships-yi-sun-sin",
        "title": "Admiral Yi's Spiked Ironclad Turtle Ships at Hansan Island",
        "category": "bizarre_invention",
        "historical_era": "Imjin War (1592 AD)",
        "core_anomaly": "Admiral Yi Sun-sin deployed armored Geobukseon vessels with iron-spiked roofs and sulfur smoke-spewing dragon prows to shatter the Japanese samurai boarding doctrine.",
        "hook_hookline": "When samurai boarding fleets invaded Korea, Admiral Yi unleashed armored dragon ships that blinded enemy gunners with sulfur clouds.",
        "key_facts": [
            "Japanese naval doctrine relied entirely on grappling hooks and lethal samurai sword boarding assaults.",
            "Yi covered his ships' curved decks with hexagonal iron plates bristling with concealed iron spikes covered in straw.",
            "A carved dragon head at the prow spewed suffocating toxic sulfur fumes while eleven heavy cannons fired point-blank."
        ],
        "visual_motifs": [
            "Heavy timber Geobukseon armor deck bristling with lethal iron spikes",
            "Carved dragon figurehead exhaling billowing dense yellow sulfur smoke across ocean waves",
            "Samurai warriors attempting boarding leaps and impaling their boots on concealed roof spikes",
            "Point-blank bronze cannon broadsides shattering wooden Japanese samurai warships",
            "Admiral Yi Sun-sin standing resolute at the helm amidst raging naval battle smoke"
        ]
    },
    {
        "id": "corvus-boarding-ramp",
        "title": "The Corvus: Rome's Spike-Bridge Naval Revolution",
        "category": "siege_engine",
        "historical_era": "First Punic War (260 BC)",
        "core_anomaly": "Rome converted maritime naval battles into land combat by inventing a thirty-six foot pivoting bridge with a colossal iron spike that locked Carthage's faster warships in place.",
        "hook_hookline": "Rome had no naval tradition—so Roman engineers invented a spiked crane bridge that turned sea battles into bloody land combat.",
        "key_facts": [
            "Carthaginian quinqueremes held total nautical superiority with veteran rowers and bronze rams.",
            "Consul Duilius mounted a rotating 36-foot wooden gangway with a heavy beak-like iron spike at the prow.",
            "When dropped onto Carthaginian decks, the iron beak punched through timber, letting Roman legionaries storm across."
        ],
        "visual_motifs": [
            "Colossal rotating wooden boarding bridge mounted on 24-foot mast with heavy iron beak spike",
            "Iron beak slamming violently through Carthaginian deck planks, locking ships in unbreakable grip",
            "Armored Roman legionaries charging two abreast with drawn gladii across the elevated gangway",
            "Carthaginian rowers trapped beneath shattered decks as Roman heavy infantry dominates hand-to-hand combat",
            "Consul Duilius directing the naval boarding assault under bright Mediterranean sunlight"
        ]
    }
]

ALIAS_MAP = {
    "carrhae-testudo": "battle-of-carrhae-camel-train",
    "the-archimedes-claw-at-syracuse": "archimedes-claw",
    "the-fire-ships-of-red-cliffs": "red-cliffs-fire-ships",
    "the-roman-scutum-testudo-at-carrhae": "battle-of-carrhae-camel-train"
}


def mine_topic(category: str = "all", custom_topic_id: str = None) -> dict:
    """Select or filter a topic from the catalog."""
    if custom_topic_id:
        target_id = ALIAS_MAP.get(custom_topic_id.lower().replace(" ", "-"), custom_topic_id)
        for t in TOPIC_CATALOG:
            if t["id"] == target_id:
                return t
        print(f"[WARN] Topic id '{custom_topic_id}' not found. Selecting from catalog.", file=sys.stderr)

    candidates = TOPIC_CATALOG
    if category != "all":
        filtered = [t for t in TOPIC_CATALOG if t["category"] == category]
        if filtered:
            candidates = filtered
        else:
            print(f"[WARN] No topic matched category '{category}', falling back to full catalog.", file=sys.stderr)

    return random.choice(candidates)


def main():
    parser = argparse.ArgumentParser(
        description="Mine and structure tactical military history topics for short-form video generation."
    )
    parser.add_argument(
        "--category",
        choices=["all", "siege_engine", "tactical_anomaly", "bizarre_invention"],
        default="all",
        help="Filter topic by tactical category."
    )
    parser.add_argument(
        "--topic-id",
        type=str,
        default=None,
        help="Explicitly pick a topic by ID (e.g., 'archimedes-claw', 'battle-of-carrhae-camel-train')."
    )
    parser.add_argument(
        "--output",
        type=str,
        default="state/topic.json",
        help="Destination path for the structured topic JSON."
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available topics and exit."
    )

    args = parser.parse_args()

    if args.list:
        print("\nAvailable Tactical History Topics:")
        for t in TOPIC_CATALOG:
            print(f" - [{t['id']}] ({t['category']}) {t['title']}")
        return

    topic_data = mine_topic(category=args.category, custom_topic_id=args.topic_id)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(topic_data, f, indent=2, ensure_ascii=False)

    print(f"[SUCCESS] Mined topic: '{topic_data['title']}' ({topic_data['id']})")
    print(f"[SUCCESS] Topic state saved to: {out_path.resolve()}")


if __name__ == "__main__":
    main()
