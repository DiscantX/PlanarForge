from pathlib import Path
import json
from core.formats.itm import ItmFile, ItemType
from core.formats.cre import CreFile, CreFileV12, SlotIndex, PstSlotIndex
from core.formats.tlk import TlkFile
from game.installation import InstallationFinder, GameInstallation
from core.formats.key_biff import KeyFile, ResType

finder = InstallationFinder()

file_objects = {
    "itm": ItmFile,
    "cre": CreFile
}

directory_path = "reference/test/"
tlk = TlkFile.from_file(f"{directory_path}/dialog.tlk")

def print_header(resource, filetype):
    for key, value in resource.header.__dict__.items():
        if (key == "unidentified_name" or key == "identified_name" or key == "unidentified_desc" or key == "identified_desc"
        or key == "name" or key == "tooltip"):
            print(f"{key}: {tlk.get(int(value))}")
        else:
            print(f"{key}: {value}")       
      

def roundtrip(resource, filetype, filename):
    # Write back (round-trip)
    resource.to_file(f"{directory_path}{filetype}/{filename}_roundtrip.{filetype}")

    # JSON round-trip
    json.dump(resource.to_json(), open(f"{directory_path}{filetype}/{filename}.json", "w"), indent=2)

def read_resources():
   subdirectories = [x for x in Path(directory_path).iterdir() if x.is_dir()]
   for dir in subdirectories:
       extension = dir.name
       print()
       print(extension)
       pattern = f"*.{extension}"
       # Get the list of matching files
       files = [p for p in Path(dir).glob(pattern) if p.is_file() and "_roundtrip" not in p.name]
       for file in files:
           print("="*80)
           print(f"\t{file}")
           print("="*80)
           file_obj = file_objects[extension]
           resource = file_obj.from_file(file)
           print_header(resource, extension)
           roundtrip(resource, extension, file.name)


def main():
    chitin_path = finder.find_chitin("BG2EE")
    print(chitin_path)
    print(finder.find("BG2EE"))
    chitin = KeyFile.open(chitin_path)
    entry = chitin.find("AR0602", ResType.ARE)
    if entry:
         raw = chitin.read_resource(entry, game_root=finder.find("BG2EE")) 
         print(raw)   
    
    # read_resources()
    
if __name__ == "__main__":
    main()