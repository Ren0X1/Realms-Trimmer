# ✂️ Realms Trimmer

![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?style=flat-square&logo=python&logoColor=white) ![Tkinter](https://img.shields.io/badge/Tkinter-GUI-4B8BBE?style=flat-square) ![Windows](https://img.shields.io/badge/Windows-10%20%2F%2011-0078D4?style=flat-square&logo=windows&logoColor=white) ![Minecraft](https://img.shields.io/badge/Minecraft-Java%20Edition-62B47A?style=flat-square&logo=minecraft&logoColor=white) ![Realms](https://img.shields.io/badge/Realms-world%20upload-F5A623?style=flat-square) ![Dependencies](https://img.shields.io/badge/dependencies-none-success?style=flat-square) [![Tests](https://img.shields.io/github/actions/workflow/status/Ren0X1/Realms-Trimmer/tests.yml?branch=main&style=flat-square&label=tests&logo=githubactions&logoColor=white)](https://github.com/Ren0X1/Realms-Trimmer/actions/workflows/tests.yml)

> **Realms upload reaching 100%, then "verifying world"… and "timed out"?** Your world is probably full of chunks nobody has ever walked into. This makes a trimmed copy that Realms accepts. 🎮

Pre-generating a world (with **Chunky**, for example) fills it with thousands of chunks that no player has ever visited. The upload itself finishes, but Realms takes so long to verify all of them on its side that it gives up. **Realms Trimmer** keeps only the chunks you have actually played in, plus a safety margin, and writes the result to a **new folder**. Your original world is never touched. ⚡

---

## 🚀 Quick start

1. 🐍 Install [Python 3](https://www.python.org/downloads/) if you don't have it (no extra packages needed).
2. ❌ **Close Minecraft.**
3. 🖱️ Double-click `realms_trimmer.py`.
4. 📂 **Mundo (entrada)** → pick your world folder (inside `.minecraft/saves/`).
5. 📁 **Copia (salida)** → fills itself in as `<world> (Realms)`; change it if you like.
6. ✂️ Click **Analizar** to preview, or **Recortar** to create the trimmed copy.
7. ☁️ In Minecraft: **Realms → Configure → Worlds → Upload world** and pick the copy.

> 💡 Don't open the trimmed copy in singleplayer before uploading it, or the game will start generating chunks again.

---

## ⌨️ Command line

```bat
python realms_trimmer.py "C:\...\saves\My World"                          :: creates "My World (Realms)" next to it
python realms_trimmer.py "C:\...\saves\My World" "D:\out\My World Realms" :: custom output folder
python realms_trimmer.py "C:\...\saves\My World" --analizar               :: preview only, writes nothing
```

| Option | What it does |
|--------|--------------|
| `entrada` | World folder to read from |
| `salida` | Folder where the trimmed copy is created (optional) |
| `--margen N` | Chunks of margin kept around every visited chunk (default **3**). Lower = smaller world |
| `--nombre TEXT` | World name shown in the game's world list (default: output folder name) |
| `--analizar` | Only prints how much would be trimmed |

Running it with no arguments opens the window. 🪟

---

## 🔍 How it works

| Step | Action |
|------|--------|
| 🧭 **Finds the dimensions** | Reads both the new layout (`dimensions/minecraft/...`) and the classic one (`region/`, `DIM-1/`, `DIM1/`) |
| ⏱️ **Reads `InhabitedTime`** | Every chunk stores how long players have spent near it. `0` means nobody has ever been there |
| 🧱 **Builds the keep list** | Every visited chunk plus a square margin around it. Chunks that can't be read are kept, just in case |
| 📦 **Copies the world** | Full copy to the output folder (skips `session.lock`) |
| ✂️ **Rewrites the regions** | Rebuilds `region`, `entities` and `poi` `.mca` files with only the kept chunks; empty ones are deleted |
| 🏷️ **Renames the world** | Updates `LevelName` in `level.dat` so the copy is easy to tell apart |

The removed chunks regenerate on their own the first time someone walks there on the Realm. 🌱

---

## 📊 Real example

| | Before | After |
|---|---|---|
| 🧱 Chunks | 146,732 | 39,307 |
| 💾 Size | 1,115 MB | 319 MB |
| ☁️ Realms upload | ❌ timed out | ✅ works |

---

## 📦 Requirements

- 🐍 Python 3.8+ (Tkinter ships with the standard Windows installer)
- 🟩 A Minecraft **Java Edition** world
- ❌ Minecraft closed while trimming

---

## ⚠️ Notes

- 🧩 **Realms is vanilla.** Anything that depends on mods (homes, tpa, Carpet…) won't work there.
- 🌍 Trimmed areas regenerate with Realms' vanilla generator, so they can look different if the original world was generated with terrain mods.
- 🛡️ The original world is only read, never modified, and the output folder must not already exist.

---

> 🛠️ **Realms Trimmer v1.0** by [Ren0X1](https://github.com/Ren0X1) · free to use.
