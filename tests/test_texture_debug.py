#!/usr/bin/env python3
"""Debug the PVRTC decoder output."""

import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))

from game.installation import GameInstallation
from core.services.character_service import CharacterService
from PIL import Image

# Load INVENTOR
svc = CharacterService()
svc.select_game("BG2EE")
tex = svc.load_mos_by_resref("INVENTOR")

if tex:
    width, height, rgba_list = tex
    
    # Convert to PIL Image
    rgba_bytes = bytes(int(c * 255) for c in rgba_list)
    img = Image.frombytes('RGBA', (width, height), rgba_bytes)
    img.save("test_inventor.png")
    print(f"Saved test_inventor.png ({width}x{height})")
    
    # Check pixel values in first PVRZ block region (271,377) 224x32
    print("\n=== Block 0 region (271,377) 224x32 ===")
    for y in range(377, min(377+10, height)):
        for x in range(271, min(271+10, width)):
            idx = (y * width + x) * 4
            r, g, b, a = int(rgba_list[idx]*255), int(rgba_list[idx+1]*255), int(rgba_list[idx+2]*255), int(rgba_list[idx+3]*255)
            print(f"({x},{y}): RGBA({r},{g},{b},{a})", end="  ")
        print()
    
    # Check some random interior pixels
    print("\n=== Random interior pixels ===")
    for y in [50, 100, 200, 300]:
        for x in [100, 200, 300, 400]:
            idx = (y * width + x) * 4
            r, g, b, a = int(rgba_list[idx]*255), int(rgba_list[idx+1]*255), int(rgba_list[idx+2]*255), int(rgba_list[idx+3]*255)
            print(f"({x},{y}): RGBA({r},{g},{b},{a})")
else:
    print("Failed to load INVENTOR")
