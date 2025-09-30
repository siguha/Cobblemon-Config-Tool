[![Download](https://img.shields.io/github/v/release/YOURNAME/Cobblemon-Academy-Config-Tool?label=Download)](https://github.com/siguha/Cobblemon-Config-Tool/releases/latest)


a Cobblemon Academy Config Tool
====================================

Frustrated with your "chest looted" stat saying 2000 while you have no Legendary to your name? Is the idea of navigating the configs too daunting a task
for you? Look no further. This simple Python script was made to help (myself first) but also conveniently, you! Simple to use, this tool will allow you
to customize the modpack's loot tables down to specific chests, designed to give you the control (and legendaries) you wish you had sooner.

Written by Reese, @sigRao for use in the Cobblemon Academy Discord Server.

====================================

What it does
------------
- Allows you to adjust global, tier-specific, or chest-specific chances for legendary items through Myths and Legends.
- Allows you to adjust individual chest loot tables to increase individual tier probability, or lower the chance you get junk in your ice room chest! 
- Seamlessly interacts with your config files to edit everything FOR you! Wow!
- Backs your config files up in case you pump a little too much too fast! Amazing!!

How To runtime_hooks
------------
### Option 1: Use the included Windows app
1. Download and unzip the release package.
2. Double-click `Loot Config Tool.exe`.
3. In the GUI, use the “Browse…” button to select your datapack root (the folder containing `data/academy/...`).
4. Switch between the **Academy Tiers** and **Chest Loot Tables** tabs to adjust what you want.
5. Click **Apply Changes** (tiers) or **Apply** (per chest) to save.

### Option 2: Run from source (for advanced users)
1. Install Python 3.9 or newer from https://www.python.org/downloads/.
2. Double-click `loot_config_tool_gui.py`, or run:
   ```bash
   python loot_config_tool_gui.py```

Tips
----
- Legendary ID defaults to `academy:myths_and_legends/legendaries`, this SHOULDN'T ever change but if it does, it's here. Otherwise don't touch it.
- The rate of change is incredibly drastic if you're mapping a global change to every value.
- For tier weights, click “Load Tiers from Chest Files” to see current values, change them, then Apply.

I'd overall be very mindful blindly assigning new values. For example, if you blindly global apply a 2x multiplier on all legendary chances,
your lower tier chests will seem more reasonable, but your higher tier less so in comparison as you'll virtually see legendaries in every chest.
In a modpack like this where level 100 gyms aren't arduous past a certain point, you'll lose a lot of the fun in legendary chasing.

Ultimately, the choice is yours and that's why I left the implementation in the production build of this script. Your experience is yours, do what you'd like, but do know that part of the (unfortunately little) longevitiy in this pack comes from the hunt.

Troubleshooting
---------------
- If you see “Failed to parse JSON” warnings: the tool scans every .json under your root. Some files
  may not be valid JSON (comments, trailing commas). That’s fine—those files are skipped.
- To reduce noise, keep paths under `data/<namespace>/loot_table/` (or `loot_tables`) and use the GUI tabs.
