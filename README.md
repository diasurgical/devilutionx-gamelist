[![Linux](https://github.com/diasurgical/devilutionx-gamelist/actions/workflows/linux.yml/badge.svg)](https://github.com/diasurgical/devilutionx-gamelist/actions/workflows/linux.yml)
[![Windows](https://github.com/diasurgical/devilutionx-gamelist/actions/workflows/windows.yml/badge.svg)](https://github.com/diasurgical/devilutionx-gamelist/actions/workflows/windows.yml)
[![MyPy Check](https://github.com/diasurgical/devilutionx-gamelist/actions/workflows/mypy.yml/badge.svg)](https://github.com/diasurgical/devilutionx-gamelist/actions/workflows/mypy.yml)

# devilutionx-gamelist
Small program for printing out a json list of current games

## How to build
```sh
cmake -S. -Bbuild -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
```

Premade binaries are available from the [linux](https://github.com/diasurgical/devilutionx-gamelist/actions/workflows/linux.yml?query=branch%3Amain) and [windows](https://github.com/diasurgical/devilutionx-gamelist/actions/workflows/windows.yml?query=branch%3Amain) workflows.

# discord_bot.py
Companion utility that watches for the output of devilutionx-gamelist and advertises the games in a discord channel

## How to build/run
```sh
# optionally create/activate a venv-like isolated environment
pip install -r requirements.txt # or install dependencies at a user level if not using a venv, or via your system package manager
python discord_bot.py
# OR
pip install -e . # could also use pipx or similar tools
discord_bot
```

Source and wheel distributions are available from the [python](https://github.com/diasurgical/devilutionx-gamelist/actions/workflows/python.yml?query=branch%3Amain) workflow.
