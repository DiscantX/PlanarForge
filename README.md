# Planar Forge — Unofficial Infinity Engine Development Suite

<img width="1366" height="768" alt="image" src="https://github.com/user-attachments/assets/cbb0f4fa-cc5b-44b5-91c6-c0e3e794ad88" />

A modern GUI for modding [Infinity Engine](https://en.wikipedia.org/wiki/Infinity_Engine) resources. The aim of this project is to provide an easy-to-use, fully featured suite of tools that allows the user to modify game resources for the Infinity Engine, which was used for games such as Baldur's Gate, Icewind Dale, Planescape Torment, as well as their sequels, expansions, and remastered versions (EE).

When it is complete, it should allow for easy creation of mods for the Infinity Engine games, or even full game conversion mods.

## Work in Progress

This project is under active development. It is not stable for use in its current state. Use at your own risk.

## Supported Games

Planar Forge currently supports the following Infinity Engine games:

* Baldur's Gate: Enhanced Edition
* Baldur's Gate II: Enhanced Edition
* Icewind Dale: Enhanced Edition

Support present but buggy due to version differences:

* Planescape Torment: Enhanced Edition
* Icewind Dale II

Support for the original (non-Enhanced Edition) Infinity Engine games and their expansions is planned, and may be working, but is either not yet implemented, or is not yet tested.

## (Partially) Implemented Features

* Easy to use, modern GUI. Takes inspiration from modern IDE and game engine editors.
* Read and write IE resource files:
  * From/to binary.
  * Resource file to JSON conversion.
  * Round-trip file read-write for both binary and JSON.
* Quick resource file search (using cached data).
* Implementation of the game interface for resource viewing & editing.
  * Read relevant UI elements from the original games, display them, allow editing of values, and then allow writing back to files.

## Planned Features

* Drag and drop interface
* Easy-to-use editors (areas, characters, items, spells, etc...)
* Graph-like dialogue editor
* Script editor (to what degree this will be integrated is undecided)
* Mod compatibility with other mods through [WeiDU](https://weidu.org/) integration
* End-to-end full conversion mod capability (all or nearly all resources created from scratch)

## License

For the moment, this body of work is not licensed for any other party to share or to modify, for non-commercial or for commercial use, except where otherwise required by law. A more permissive license will likely be adopted in the future, but for the time being remember this disclaimer:

### Disclaimer

The Infinity Engine is proprietary. The creator of this repository believes it to be owned wholly or in part by Beamdog Studios, and as such, any derivative works that are made as a result of the use of this tool cannot be used for commercial purposes.

Likewise, game assets such as image files or other resource files will not be publicly shared through this tool. Use of this tool requires an installation of a purchased copy of one of the Infinity Engine games.

## Acknowledgments

There has been a long history of modding the Infinity Engine. This project is built on the backs of (frost) giants.

Specific callouts include those responsible for the creation of the following tools and resources, which were instrumental in the creation of this one:

* [IESDP](https://gibberlings3.github.io/iesdp/): The ground truth for this entire project. It catalogues the entire known architecture for the engine, all of which was reverse engineered by a mass of rabid fans.
* [The Gibberlings 3](https://www.gibberlings3.net/): See above. The hub for IE modding.
* [Near Infinity](https://github.com/Argent77/NearInfinity): Comprehensive resource inspector. This tool was used to sanity-check file formats many times.
* [WeiDU](https://weidu.org/) Infinity Engine mod distribution tool.

## AI Use Disclaimer

Much, if not all, of the code used in this project was created through the use of AI, which was supervised and guided by a human. While this is not maybe the preferred path that this (human) author would have liked to have taken, it cut development time down substantially. The actual structure of the code base is under constant review by the human, as it seems to change rapidly.
