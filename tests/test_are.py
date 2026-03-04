from core.formats.are import AreFile

area = AreFile.from_file("AR0602.are")
print(area.header.wed_resref)       # companion WED file
print(len(area.actors))             # number of actors placed in the area
for entrance in area.entrances:
    print(entrance.name, entrance.x, entrance.y)
