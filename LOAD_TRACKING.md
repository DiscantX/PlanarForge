"""
LOAD TRACKING IMPLEMENTATION SUMMARY
=====================================

Overview
--------
When switching games (BGEE → BG2EE) or loading characters, PlanarForge now displays
real-time status messages in the toolbar showing what operation is currently running.
This provides visibility into what's happening during long-running operations and helps
identify where time is being spent.

The implementation uses background threading to allow the UI to remain responsive and
update status messages in real-time.

Components
==========

1. ui/core/progress_handler.py (NEW - Reusable for all editors)
   - EditorProgressHandler: Simple callback interface for status updates
   - Used by editors to wire service operations to toolbar display
   - Methods:
     * on_progress(message) - Called during operation (intermediate steps)
     * on_complete(message) - Called when operation finishes
     * on_error(message) - Called on error

2. ui/core/editor_toolbar.py (UPDATED)
   - Simplified to only manage game selection, buttons, and status text
   - Status text displayed in blue (150, 200, 255) at right end of toolbar
   - Methods:
     * set_status(message) - Update toolbar status display
     * get_status() - Get current status

3. core/services/character_service.py (UPDATED)
   - Added progress callback support for tracking operations
   - set_progress_callback(callback) - Register progress reporter
   - Progress points in load_character_with_payload():
     * "Loading {resref}..."
     * "Parsing {resref}..."
     * "Loading inventory for {resref}..."
     * "Serializing {resref}..."

4. ui/editors/character_editor.py (UPDATED)
   - Uses EditorProgressHandler to wire service callbacks to toolbar
   - Handler created in __init__:
     ```python
     self._progress_handler = EditorProgressHandler(self._set_status)
     self.service.set_progress_callback(self._progress_handler.on_progress)
     ```
   - Services call handler.on_progress() during operations
   - Messages appear immediately in blue text

5. ui/util/async_loader.py (NEW - Optional for CPU-bound operations)
   - AsyncLoader: Runs long operations in background thread
   - Allows spinner/animations to work during blocking operations
   - Thread-safe result retrieval


Using Progress Tracking in New Editors
======================================

To add progress tracking to a new editor (e.g., ItemEditorPanel):

1. Import EditorProgressHandler:
   ```python
   from ui.core import EditorProgressHandler
   ```

2. Create handler in __init__:
   ```python
   self._progress_handler = EditorProgressHandler(self._set_status)
   ```

3. Wire to your service:
   ```python
   service.set_progress_callback(self._progress_handler.on_progress)
   ```

4. Add progress points in your service (same as CharacterService):
   ```python
   def load_item(self, itm_resref: str):
       self._report_progress(f"Loading {itm_resref}...")
       # ... do work ...
       self._report_progress(f"Parsing {itm_resref}...")
       # ... more work ...
   ```

5. The status text automatically updates in the toolbar.

That's it! No spinner management, no threading code needed in the editor.


How the System Works
====================

**Synchronous (Blocking) Operation:**
- Editor calls service.load_character()
- Service calls _report_progress() at key points
- Progress messages appear immediately in toolbar
- UI updates are "live" but may feel blocky during heavy operations

**Background Threading (Optional - for UI responsiveness):**
- Use AsyncLoader to offload long operations to background thread
- Example:
  ```python
  def _load_character_async(self, resref):
      loader = AsyncLoader(
          operation=self.service.load_character_with_payload,
          on_progress=self._progress_handler.on_progress,
          on_complete=self._on_character_loaded,
          on_error=self._on_load_error,
      )
      loader.start(resref)
  ```
- Main thread can render spinner, animations, or respond to input
- Operation runs in background, callbacks fired when events occur

**Message Flow:**
1. Service._report_progress(msg) called
2. Calls registered callback (progress_handler.on_progress)
3. Handler calls toolbar.set_status(msg)
4. DearPyGui updates text immediately
5. UI thread continues rendering

Performance Notes
=================

All progress tracking is synchronous and happens on the calling thread (service).
Progress callbacks are fast (just a text update), so overhead is minimal.

**Current Implementation:**
- Messages update ~immediately as service operations complete
- Operations still block the UI when called synchronously
- Good for: Visibility of what's happening, identifying slow operations

**Future Optimization Path:**
- Wrap slow operations (load_character, load_index) with AsyncLoader
- Run in background threads with real-time progress updates
- UI stays responsive, user can cancel if needed

**Bottlenecks to Profile:**
Based on tracking, investigate these areas if still slow:
1. "Loading {resref}..." - CHITIN.KEY archive read time
2. "Parsing {resref}..." - CreFile.from_bytes() binary parsing
3. "Loading inventory..." - Item icon lookups (itm_catalog)
4. "Rendering..." - UI element creation and layouting
5. MOS/PVRZ texture loading (if backgrounds take long)


Example: Adding Tracking to a New Service Method
=================================================

```python
def load_spell_description(self, spl_resref: str) -> SpellVM:
    self._report_progress(f"Finding {spl_resref}...")
    entry = self._key.find(spl_resref, ResType.SPL)
    
    self._report_progress(f"Reading from archive...")
    raw = self._key.read_resource(entry, game_root=self._selected_game)
    
    self._report_progress(f"Parsing {spl_resref}...")
    spl = SplFile.from_bytes(raw)
    
    self._report_progress(f"Resolving strings...")
    vm = SpellVM.from_spl(spl, self._manager)
    
    return vm

# Editor wires this automatically:
# handler.on_progress() → toolbar.set_status()
# User sees: "Finding FIREBALL..." → "Reading from archive..." → etc.
```
"""
