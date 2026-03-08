"""
LOAD TRACKING IMPLEMENTATION SUMMARY
=====================================

Overview
--------
This document outlines the load tracking and visual progress indicator system
added to PlanarForge to help identify performance bottlenecks when switching
games and loading characters.

Components Added
================

1. ui/core/load_tracker.py (NEW MODULE)
   - LoadTracker: Simple timing/progress tracking class
   - Tracks elapsed time from start
   - Records step timings for each operation
   - Methods:
     * step(message) - Record a progress point with elapsed time
     * mark(message) - Alias for step()
     * elapsed() - Get total elapsed time
     * get_step_times() - Get dictionary of all recorded steps


2. ui/core/editor_toolbar.py (UPDATED)
   - Added animated spinner visual indicator
   - Spinner frames: ["|", "/", "-", "\\"] rotating continuously
   - New methods:
     * set_loading(is_loading, message="") - Show/hide spinner
     * update_spinner(message="") - Animate spinner frame
   - Display format: "[spinner_frame] [message]" in blue text (150, 200, 255)
   - Spinner updates on each call to update_spinner()


3. core/services/character_service.py (UPDATED)
   - Added progress callback support
   - New method: set_progress_callback(callback)
   - Callback is called with status messages during character loading
   - Progress tracking points in load_character_with_payload():
     * "Loading {resref}..."
     * "Parsing {resref}..."
     * "Loading inventory for {resref}..."
     * "Serializing {resref}..."


4. ui/editors/character_editor.py (UPDATED)
   - Integrated load tracking into character loading flow
   - Progress callback wired to toolbar spinner animation
   - Spinner starts on game selection and character load
   - Two main tracked flows:

     a) Game Selection (_activate_game):
        - Spinner: "Initializing..."
        - Spinner: "Loading CRE index..."
        - Displays total CRE count when done

     b) Character Load (load_character):
        - Spinner: "Loading {cre_resref}..."
        - Service provides status updates (parsing, inventory, etc)
        - Spinner: "Rendering inventory..."
        - Displays final status with character name


Usage / How to Analyze Performance
===================================

The visual spinner provides real-time feedback of what's happening:
- Spinner indicates UI is NOT frozen
- Messages tell you exactly which step is running
- You can now see where time is being spent

To Measure Performance:
1. Watch the status messages as you switch games/load characters
2. Note which step takes longest before next update
3. The steps are:
   - Loading CRE index (initial game selection)
   - Loading CRE file from archives
   - Parsing CRE binary format
   - Loading inventory (item icon lookups)
   - Serializing to JSON/viewmodel
   - Rendering game screen UI

Next Steps for Optimization
============================

Based on the tracking, focus on:

1. Inventory Loading - If "Loading inventory..." takes long:
   - Profile itm_catalog.load_item_name_and_icon_by_resref()
   - Consider parallel loading of item icons
   - Cache loaded item data between characters

2. Game Screen Rendering - If "Rendering inventory..." takes long:
   - Profile InfinityScreenPanel._rebuild()
   - Check if it's dpg.add_image() calls that are slow
   - Consider batch/deferred rendering

3. CRE Parsing - If "Parsing {resref}..." takes long:
   - CreFile.from_bytes() may be the bottleneck
   - Check for expensive calculations
   - Profile binary unpacking

To Add More Tracking:

1. Service-level progress:
   ```python
   service.set_progress_callback(lambda msg: print(f"Progress: {msg}"))
   ```

2. Custom tracking in editor:
   ```python
   self._toolbar.set_loading(True, "Custom message")
   # ... do work ...
   self._toolbar.update_spinner("New message")
   # ... more work ...
   self._toolbar.set_loading(False, "Done!")
   ```

3. To add tracking to skin_assets or screen_panel:
   - Add progress_callback parameter to __init__
   - Call callback at key points
   - Wire callback from character_editor like we did for service


Performance Hints
=================

The slowness on first load is typical because:
1. CRE files must be unpacked from CHITIN.KEY archives
2. Item data must be loaded from ITM catalog
3. Game screen layout must be loaded from CHU data
4. Icon textures must be loaded from BAM files

Subsequent loads are fast because of caching:
- CRE index is cached
- Item catalog is cached
- CHU layouts are cached in InfinitySkinAssets._chu_layout_cache
- Textures are cached

The spinner and messages now make this behavior visible to the user.
"""
