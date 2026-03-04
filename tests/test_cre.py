
from core.formats.cre import CreFile, CreFileV12, SlotIndex, PstSlotIndex
from core.formats.tlk import TlkFile

cre = CreFile.from_file("GUARD2.cre")       # auto-dispatches on version
print(cre.header.max_hp)
print(cre.item_in_slot(SlotIndex.WEAPON2))

filename = "GUARD2"

tlk = TlkFile.from_file("dialog.tlk")
cre = CreFile.from_file(f"{filename}.cre")

name_ref = cre.header.name
name = tlk.get(name_ref)

for key, value in cre.header.__dict__.items():
    # if true:
    # # if key == "unidentified_name" or key == "identified_name" or key == "unidentified_desc" or key == "identified_desc":
    # #     print(f"{key}: {tlk.get(int(value))}")
    # else:
    print(f"{key}: {value}")

# Write back (round-trip)
cre.to_file(f"{filename}_copy.cre")

# JSON round-trip
import json
json.dump(cre.to_json(), open(f"{filename}.json", "w"), indent=2)