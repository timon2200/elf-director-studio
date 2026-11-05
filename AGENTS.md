# AGENTS.md — Vodič za AI Agente (`elf-director-studio`)

Ovaj dokument namijenjen je AI agentima (Antigravity, Claude Code, Cursor, Windsurf, Cline, Codex) kada korisnik zatraži postavljanje ili korištenje **ActionForge Elf Animation Director Studija v3.0** u Blenderu.

---

## 1. Automatska Instalacija na Korisnikovom Računalu (Korak po Korak za Agenta)

Kada ti korisnik pošalje link na ovaj repozitorij ili zatraži da mu složiš **Elf Studio** u Blenderu, izvrši sljedeće korake:

### Korak A: Kloniranje i Pokretanje Univerzalnog Instalatora
```bash
git clone https://github.com/timon2200/elf-director-studio.git
cd elf-director-studio
python3 install_elf_studio.py --download-scenes
```
Što `install_elf_studio.py` radi automatski:
1. Spaja `database/elf_assets_library.blend.part01` i `.part02` u `database/elf_assets_library.blend` (112 MB, 7 rigiranih vilenjaka + 34 animacije).
2. Zapisuje lokalne putanje do `database/` i `assets/` u `elf_director/_studio_paths.json` kako bi add-on radio iz bilo koje `.blend` datoteke na disku.
3. Kopira `elf_director` u `scripts/addons/elf_director` za sve pronađene verzije Blendera 4.x i 5.x (macOS, Windows, Linux).
4. Kroz pozadinski Blender uključuje add-on u korisničkim postavkama (`bpy.ops.preferences.addon_enable(module="elf_director")` + `bpy.ops.wm.save_userpref()`).
5. Generira `elf_director_quickstart.blend` te (uz `--download-scenes`) preuzima `elves_animation_director_studio.blend` i `minecart_pusher_demo.blend` s GitHub Releasea `v3.0.0`.

### Korak B: Ako Korisnik Ima Otvoren Živi Blender (Preko Blender MCP-a)
Ako imaš pristup alatu `execute_blender_code` (Blender MCP), **nemoj** čekati da korisnik ponovno pokrene Blender. Pošalji ovaj kod izravno u otvoreni Blender kako bi mu se odmah pojavila kartica **`Elf Director`** u N-panelu i učitala baza:

```python
import sys
# Zamijeni putanjom gdje si klonirao repozitorij:
STUDIO_PATH = "/apsolutna/putanja/do/elf-director-studio"
if STUDIO_PATH not in sys.path:
    sys.path.insert(0, STUDIO_PATH)

import bootstrap_director
ed = bootstrap_director.bootstrap_elf_director()
ed.integrate_into_scene(spawn_demo=True)
```

---

## 2. Agent-First Python SDK (`import elf_director as ed`)

Sve funkcije dostupne su izravno kroz modul `elf_director`:

### A) Učitavanje Baze i Pregled Scene
```python
import elf_director as ed

# Učitava 7 predložaka vilenjaka i 34 animacije u trenutnu scenu te registrira N-panel
ed.integrate_into_scene(spawn_demo=False)

# Popis vilenjaka, animacija i trenutnog stanja u sceni
elves = ed.list_available_elves()
anims = ed.list_available_animations()               # Sve 34 animacije
work_anims = ed.list_available_animations("WORK")    # Radne animacije (AF_22, AF_25..AF_33)
manifest = ed.get_scene_manifest()
```

### B) Postavljanje Vilenjaka (`ELF06`, `ELF10`, `ELF14`, `ELF16`, `ELF21`, `ELF23`, `ELF28`)
```python
urar = ed.spawn(
    elf_id="ELF10",
    location=(-2.0, 1.5, 0.0),
    rotation_z_deg=35.0,
    scale=1.0,
    animation="AF_01_Walk_Steady",
    frame_offset=12,
    show_hat=True,
    show_glasses=True,
)
```

### C) Promjena Animacije i Višeslojni NLA Sekvencer
```python
# Pojedinačna animacija
ed.set_animation(urar, "AF_27_Mine_Pickaxe", speed=1.0, frame_offset=0, loop=True)

# Niz animacija u NLA sekvenceru s glatkim prijelazima (Crossfade)
ed.chain_animations(urar, [
    {"action": "AF_01_Walk_Steady", "repeat": 2.0, "speed": 1.0, "blend": 0},
    {"action": "AF_27_Mine_Pickaxe", "repeat": 2.0, "speed": 1.0, "blend": 12},
    {"action": "AF_28_Wave_Hello", "repeat": 1.0, "speed": 1.0, "blend": 12},
])
```

### D) Hodanje po Krivuljama bez Klizanja Stopala (`Zero-Slip Curve Locomotion`)
```python
putanja = ed.create_walk_curve(
    name="Rudarska_Staza",
    points=[(-4.0, -2.0, 0.0), (0.0, 0.5, 0.0), (4.0, -1.5, 0.0)],
    cyclic=False,
)
ed.set_animation(urar, "AF_01_Walk_Steady")
ed.follow_curve(urar, putanja, start_pct=0.0, loop=True)

# Drugi vilenjak na istoj krivulji s pomakom od 35%
birokrat = ed.spawn(elf_id="ELF23", animation="AF_01_Walk_Steady", frame_offset=19)
ed.follow_curve(birokrat, putanja, start_pct=35.0, loop=True)
```

### E) Rudarske Košare na Užadi s Fizikom Njihala i Krampa (`elf_director.cliff_baskets`)
```python
from elf_director import cliff_baskets as cb

# Postavlja košaru s 4 Gizmo prstena užadi, koloturom vitla, vilenjakom i fizikom odguravanja od zida
station = cb.spawn_cliff_basket_station(
    name="Basket_Station_01",
    preset_id="BASKET_03_HALF_MINER",   # BASKET_01_OCT_EMPTY, BASKET_02_GONDOLA_EMPTY, BASKET_03_HALF_MINER, BASKET_04_FULL_CARGO
    location=(0.0, 0.0, 6.0),
    rope_length=8.0,
    elf_id="ELF06",
    cargo_id="CARGO_A_ICE",             # CARGO_A_ICE, CARGO_B_TOOLS, CARGO_C_BARREL, NONE
)
```

### F) Vilenjak koji Gura Rudarski Vagonet po 3D Pruzi (`elf_director.minecart_pusher`)
```python
from elf_director import minecart_pusher as mp

# Gradi zakrivljenu 3D uskotračnu prugu s pragovima i postavlja vilenjaka koji gura vagonet
res = mp.spawn_elf_pushing_minecart_on_rail_curve(
    elf_id="ELF14",
    variant="FULL",                     # "EMPTY" ili "FULL" (s košarom i plavim ledom)
    curve_points=[(-6.0, 0.0, 0.0), (-2.0, 1.5, 0.0), (3.0, 1.2, 0.0), (7.0, -1.0, 0.0)],
    start_pct=0.0,
)
```

### G) Podzemna Žičara s Gondolama i Dinamičkim Provjesom Sajle (`elf_director.ropeway_gondolas`)
```python
from elf_director import ropeway_gondolas as rw

# Gradi zatvorenu petlju žičare s interaktivnim Null točkama stupova, koloturama i gondolama
sys_obj = rw.spawn_ropeway_system(
    system_name="Glavna_Zicara",
    null_points=[(12.0, -8.0, 14.0), (4.0, -3.0, 11.5), (-6.0, 2.0, 9.0), (-15.0, 7.0, 7.0)],
    gondola_count=8,
    distribution_mode="MIXED_75_CARGO_25_ELF",
    support_mode="PYLON_TOWER",
)
```

### H) Obavezna Dijagnostička Provjera (`ed.verify_scene()`)
Prije završetka zadatka uvijek pokreni:
```python
report = ed.verify_scene()
print(report)
```

---

## 3. Modularni 4-Dijelni `Elf Rig Studio` (`character_rig_studio/`)

Ako korisnik želi rigirati vlastiti 3D lik podijeljen na `BODY`, `HEAD AND HAIR`, `HAT` i `GLASSES`:
- Pročitaj detaljnu specifikaciju u [`character_rig_studio/elf-3d-character-pipeline.md`](character_rig_studio/elf-3d-character-pipeline.md).
- Referentni N-panel plugin nalazi se u [`character_rig_studio/elf10_sculpt_rig_studio.py`](character_rig_studio/elf10_sculpt_rig_studio.py).
- **Zlatno pravilo:** Kada korisnik u Koraku 3 završi ručni Weight Paint i uključi `scene.elf01_lock_weights = True`, agent nikada ne smije ponovno pozvati `bind_character_to_rig()` kako ne bi prebrisao ručno obojane težine.
