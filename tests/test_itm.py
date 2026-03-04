from core.formats.itm import ItmFile, ItemType
from core.formats.tlk import TlkFile

filename = "HELM21"

tlk = TlkFile.from_file("dialog.tlk")
itm = ItmFile.from_file(f"{filename}.itm")

name_ref = itm.header.identified_name
name = tlk.get(name_ref)
item_type_value = itm.header.item_type
item_base_value = itm.header.base_value

# print(name_ref, name)
# print(item_type_value, ItemType(item_type_value).name)
# print(itm.header.base_value)

for key, value in itm.header.__dict__.items():
    if key == "unidentified_name" or key == "identified_name" or key == "unidentified_desc" or key == "identified_desc":
        print(f"{key}: {tlk.get(int(value))}")
    else:
        print(f"{key}: {value}")

# Write back (round-trip)
itm.to_file(f"{filename}_copy.itm")

# JSON round-trip
import json
json.dump(itm.to_json(), open(f"{filename}.json", "w"), indent=2)