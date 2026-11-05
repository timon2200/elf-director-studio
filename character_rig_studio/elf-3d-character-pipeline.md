# Human-in-the-Loop (User ↔ Agent) 3-Part Modular 3D Character Pipeline (Body + Head/Beard + Rigged Hat)

Ovaj dokument definira službeni **naizmjenični (Back-and-Forth) Korisnik ↔ Agent workflow** za izradu, spajanje, riganje, ručni Weight Paint i animiranje 3D likova vilenjaka (`Overwatch_Vilenjaci_Katalog`) u projektu **Advent Lift 2026**, uključujući **zasebnu izradu, riganje i Weight Paint kape (`HAT`) te brade**.

Referentna implementacija i N-panel plugini nalaze se u:
- 3-Dijelna Python skripta i N-Panel (`Elf #10 Rig Studio (Urar + Kapa)`): [`tools/elf10_sculpt_rig_studio.py`](file:///Users/timonterzic/Documents/Projekti/Advent%20Lift%202026/tools/elf10_sculpt_rig_studio.py)
- 2-Dijelna Python skripta (`Elf #01 Kondukter`): [`tools/elf01_sculpt_rig_studio.py`](file:///Users/timonterzic/Documents/Projekti/Advent%20Lift%202026/tools/elf01_sculpt_rig_studio.py)
- Interaktivna Blender scena: [`assets/models/elf01_kondukter_rig_ready.blend`](file:///Users/timonterzic/Documents/Projekti/Advent%20Lift%202026/assets/models/elf01_kondukter_rig_ready.blend) / `assets/models/elf10_urar_rig_ready.blend`

---

## 1. Pregled Naizmjeničnog (Ping-Pong) Toka Rada: Korisnik ↔ Agent

Cijeli proces podijeljen je u **5 koraka (izmjena)** između Agenta i Korisnika u živom Blenderu (`localhost:9876` putem Blender MCP-a):

| Izmjena | Tko radi | Faza u `Elf Rig Studio` N-Panelu | Što se točno događa | Izlaz / Predaja (Handoff) |
| :--- | :--- | :--- | :--- | :--- |
| **1. Izmjena** | **AGENT** | Priprema 2D + 3D modela (3 dijela) i `.blend` scene | Generira **3 ortografska lista** (`HEAD AND HAIR` s bradom bez kape + `BODY` bez glave i bez brade u 45° A-pozi, 7.5H + `HAT` zasebna kapa sa zvončićem), izrezuje `1:1` poglede, uz odobrenje korisnika generira 3 `tripo-p2` GLB-a, čisti šavove, gradi 71-kostni `ARM_Elf_Hero` (s kostima kape `Hat.01..HatBell` i brade `Beard.01..02`) i ugrađuje `Elf Rig Studio` N-panel u živi Blender. | Agent predaje otvorenu `.blend` scenu Korisniku za **KORAK 1 i 2**. |
| **2. Izmjena** | **KORISNIK** | **KORAK 1 [VI]** i **KORAK 2 [VI]** | **Korak 1:** Namješta `HEAD AND HAIR` u ovratnik `BODY` modela i `HAT` na glavu (`G/R/S` + `Sculpt Grab: Glava / Tijelo / Kapa`) te klikne `Potvrdi Poravnanje Modela (Sync Kosti)`.<br>**Korak 2:** Klikne `Uredi Kosti (Edit Mode + X-Mirror)` i ručno namjesti kosti tijela, glave, brade i kape (`Samo Kapa i Brada`). | Korisnik klikne `Potvrdi Rig -> Početni Bind` ili u chatu javi Agentu: *"Namjestio sam rig"*. |
| **3. Izmjena** | **AGENT** | Izračun početnih oštrih težina (Initial Bind za sva 3 meša) | Preko Blender MCP-a (`execute_blender_code`) čita korisnikove pozicije kostiju iz živog Blendera, sprema ih u `BONE_TABLE` i računa početni **Crisp Axial Joint-Plane Bind (`1.8 cm` za tijelo/glavu, `2.2 cm` za lanac kape `Hat.01 -> Hat.02 -> Hat.03 -> HatBell`)** — 100% krute kosti duž segmenata, prijelaz samo u ravnini zgloba. | Agent osvježava živi Blender i predaje scenu Korisniku za **KORAK 3 (Weight Paint)**. |
| **4. Izmjena** | **KORISNIK** | **KORAK 3 [VI]: Ručni Weight Paint (Tijelo, Glava, Kapa)** | Pomoću 1-klik gumba kostiju (`Rame.L`, `Nadlaktica.L`, `Podlaktica.L`, `Bedro.L`..., te **`Obod Kape (Hat.01)`**, **`Tijelo Kape (Hat.02)`**, **`Vrh Kape (Hat.03)`**, **`Zvončić (HatBell)`**, **`Brada Gornja/Vrh`**), 1-klik četki (`Dodaj 100%`, `Zglob 50%`, `Briši 0%`, `Omekšaj Blur`), testne poze (`Savij Laktove/Koljena + Kapu/Bradu`) i `Zrcali .L -> .R` ručno dorađuje težine na sva 3 meša. | Korisnik klikne **`Potvrdi i Zaključaj Težine (Spremno za Agenta)`** (`elf01_lock_weights = True`) i javi Agentu: *"Gotov je weight paint"*. |
| **5. Izmjena** | **AGENT** | **KORAK 4 [AGENT]: Animacije i Export** | **STROGO ČUVA ZAKLJUČANE RUČNE TEŽINE** (nikada više ne poziva `bind_character_to_rig`!), prebacuje Mixamo/RPM animacije (`retarget_mixamo_fbx` uz sekundarnu fiziku njihanja vrha kape, zvončića i brade) i izvozi finalni `.glb` i `.blend`. | Gotov animirani 3D lik spreman za `master_file_2026_01.blend`. |

---

## 2. Zlatna Pravila za Sve Agente (Obavezno Čitanje)

1. **Živi Blender MCP (`execute_blender_code`) vs. Pozadinski CLI (`Blender -b`):**
   - Kada korisnik ima otvoren Blender, pokretanje `/Applications/Blender.app/Contents/MacOS/Blender -b` mijenja samo datoteku na disku, **NE i scenu koju korisnik gleda u RAM-u**!
   - Agent **MORA** sve izmjene skripti, čitanje kostiju i ažuriranje N-panela slati izravno u otvoreni Blender preko `call_mcp_tool(ServerName="blender", ToolName="execute_blender_code", ...)` uz poziv `area.tag_redraw()` i `bpy.ops.wm.save_mainfile()`.
2. **Zabrana Brisanja Korisnikovog Ručnog Weight Painta (`elf01_lock_weights`):**
   - Nakon što korisnik u **Koraku 3** ručno oboja težine na `BODY`, `HEAD AND HAIR` i `HAT` te uključi **`Zaključaj Ručne Težine`** (`context.scene.elf01_lock_weights = True` / `arm_obj["user_weights_locked"] = True`), **NIJEDAN agent ne smije ponovno pozvati `bind_character_to_rig()`**!
   - Funkcija `bind_character_to_rig(context, force=False)` ima ugrađenu blokadu i odbit će prebrisati `vertex_groups` dok je `elf01_lock_weights == True`.
3. **3-Dijelna Modularna Podjela (`HEAD AND HAIR` + `BODY` + `HAT`):**
   - **Dio 1 (`HEAD AND HAIR`):** Glava, kosa, uši, naočale/lupe, brkovi i cijela duga brada te čisti cilindrični stup vrata — **bez kape/šešira** (kako bi cijelo tjeme i kosa bili čisto izmodelirani).
   - **Dio 2 (`BODY`):** Cijelo tijelo bez glave (i bez brade na prsima, tako da su svi gumbi prsluka i ovratnik potpuno čisti) u **45° A-pozi**, proporcije **7.5 glava**, zatvoreni ravni ovratnik na vrhu vrata, dlanovi s razmaknutim prstima.
   - **Dio 3 (`HAT`):** Zasebna vilenjačka kapa/šešir (npr. baršunasta kapa s povijenim vrhom i mjedenim zvončićem na vrhu) bez glave i bez kose, sa šupljim donjim obodom koji sjeda na `HEAD AND HAIR`. Kapa dobiva vlastiti lanac kostiju (`Hat.01 -> Hat.02 -> Hat.03 -> HatBell` vezan na `Head`) u kolekciji `5_Kapa_Dodaci`, vlastiti `Armature` modifikator i punu podršku za ručni Weight Paint u Koraku 3!
4. **Izravni OpenAI API i Tripo 3D API v3 Pravila (Bez Magnific MCP-a):**
   - Za 2D ortografske listove (`gpt-image-2.5-sunburst`) koristi se isključivo izravni **OpenAI API ključ (`os.environ["OPENAI_API_KEY"]`)**, nikada preko Magnific MCP-a.
   - Za 3D generaciju (`P2-20260801` / `tripo-p2`) koristi se isključivo **izravni Tripo 3D API v3 (`https://openapi.tripo3d.ai/v3`, `os.environ["TRIPO_API_KEY"]`)** preko `/Users/timonterzic/.gemini/config/skills/tripo-3d-api/scripts/tripo_direct.py` ili `tripo-cli` (**nikada** preko Magnific MCP-a!).

---

## 3. Detaljan Opis Koraka i Tehnička Specifikacija

### Izmjena 1 [AGENT]: Priprema 2D/3D Modela (3 Dijela) i `.blend` Scene

1. **2D Ortografski Listovi (`1536×1024` -> `2048×1664`, `#808080` pozadina):**
   - Generiraj 3 lista s 3 pogleda (`FRONT`, `LEFT PROFILE`, `BACK`):
     - `VZ_elf_<ID>_part01_head_hair__gpt.png`
     - `VZ_elf_<ID>_part02_headless_body_outfit__gpt.png`
     - `VZ_elf_<ID>_part03_elf_hat__gpt.png`
   - Izreži svaki list u 4 uniformna kvadrata `1536×1536` (`front.png`, `left.png`, `back.png`, `right.png`).
2. **3D Generacija (Izravni Tripo 3D API v3 — `P2-20260801`):**
   - Pozovi izravni Tripo 3D API (`/v3/generation/multiview-to-model`, `model="P2-20260801"`, `quad=True`, `pbr=True`, `texture_quality="detailed"`, `120 kredita = $1.20` po dijelu) preko `tripo_direct.py` i generiraj 3 modela (`HEAD AND HAIR`, `BODY`, `HAT`).
3. **Čišćenje Geometrije i Postavljanje Pivota u Blenderu (`build_rig_ready_scene`):**
   - Sva 3 GLB-a uvezi u Blender, primijeni rotaciju `-90° Z` (`Front = -Y`, `Left = +X`, `Right = -X`, `Up = +Z`) i postavi potplate čizama `BODY` modela na `Z = 0.0`.
   - **Zavarivanje UV šavova (`remove_doubles`):** Na sva 3 modela u `Edit Mode` pokreni `bpy.ops.mesh.remove_doubles(threshold=0.0001)` kako se kod upotrebe `Sculpt Grab` četke poligoni ne bi razdvajali po UV šavovima.
   - **Pivot Glave i Kape:**
     - Pomakni vrhove `HEAD AND HAIR` meša tako da lokalni origin `(0, 0, 0)` leži u središtu baze vrata (`DEFAULT_HEAD_PIVOT`).
     - Pomakni vrhove `HAT` meša tako da lokalni origin `(0, 0, 0)` leži u središtu donjeg oboda kape (`DEFAULT_HAT_PIVOT`).
   - Kreiraj 71-kostnu armaturu `ARM_Elf_Hero` organiziranu u 5 kolekcija kostiju (`1_Torzo_Glavni`, `2_Ruke_Noge`, `3_Prsti`, `4_Glava_Lice_Usi`, `5_Kapa_Dodaci`) i ugradi skriptu s `use_module = True`.

---

### Izmjena 2 [KORISNIK u Blenderu]: KORAK 1 (Spajanje 3 Modela) i KORAK 2 (Poravnanje Kostiju)

Korisnik otvara bočni N-panel **`Elf #10 Rig Studio (Urar + Kapa)`** (tipka `N` u 3D Viewportu):

1. **KORAK 1 [VI]: Spoji i Poravnaj 3 Modela (`BODY` + `HEAD AND HAIR` + `HAT`):**
   - Klikne **`Odaberi HEAD AND HAIR (G / R / S)`** i namjesti glavu/vrat u ovratnik tijela.
   - Klikne **`Odaberi HAT — Kapu (G / R / S)`** i namjesti kapu na tjeme glave iznad naočala/lupa.
   - Po potrebi koristi **`Sculpt Grab: Glava`**, **`Sculpt Grab: Tijelo`** ili **`Sculpt Grab: Kapa`** (na asimetričnoj kapi `X-Mirror` se automatski gasi kako se povijeni vrh sa zvončićem ne bi deformirao).
   - Klikne **`Potvrdi Poravnanje Modela (Sync Kosti)`** — skripta automatski seli kosti glave, ušiju i brade prema transformaciji `HEAD AND HAIR`, a kosti `Hat.01 -> Hat.02 -> Hat.03 -> HatBell` prema transformaciji `HAT` objekta.
2. **KORAK 2 [VI]: Poravnaj Rig i Kosti:**
   - Klikne **`Uredi Kosti (Edit Mode + X-Mirror)`**.
   - Pomoću gumba **`Lijeva Šaka`**, **`Desna Šaka`**, **`Glava + Kapa`**, **`Samo Kapa i Brada`**, **`Cijelo Tijelo`**, **`Samo Prsti`** i **`X-Ray Model`** namješta zglobove kostiju unutar modela.
   - Na kraju Koraka 2 korisnik klikne **`Potvrdi Rig -> Početni Bind za Weight Paint`** ili napiše Agentu u chatu da je rig namješten.

---

### Izmjena 3 [AGENT preko Blender MCP-a]: Čitanje Riga i Početni Oštri Bind Zglobnih Ravnina

Kada korisnik javi da je namjestio rig:

1. Agent preko `execute_blender_code` čita sve uređene pozicije kostiju (`b.head_local`, `b.tail_local`, `b.roll`) iz živog `ARM_Elf_Hero` objekta i zapisuje ih u `BONE_TABLE` unutar [`tools/elf10_sculpt_rig_studio.py`](file:///Users/timonterzic/Documents/Projekti/Advent%20Lift%202026/tools/elf10_sculpt_rig_studio.py).
2. Agent izvršava **`bind_character_to_rig(bpy.context, force=True)`** koristeći **Cumulative Axial Joint-Plane Skinning (`blend_chain_planes`)** za sva 3 meša:
   - **`BODY`:** Lanac udova i kralježnice dijeli se poprečnim ravninama u zglobovima (`±1.8 cm`):
     $$F_i = \prod_{k=0}^{i} f_k, \qquad w_i = F_{i-1} - F_i$$
   - **`HEAD AND HAIR`:** Vrat (`Neck -> Head`), uši (`Ear.L/R`), naočale i dvostruke urarske lupe na čelu (`100% Head`) te lanac duge bijele brade (`Beard.01 -> Beard.02` uz blagi udio `Spine2` na samom donjem vrhu brade protiv probijanja kroz prsluk).
   - **`HAT` (`bind_hat_mesh_corridor`):** Lanac kape `Hat.01 (Obod) -> Hat.02 (Sredina) -> Hat.03 (Povijeni Vrh) -> HatBell (Zvončić)` dijeli se zglobnim ravninama (`±2.2 cm`). Donji baršunasti obod kape čvrsto prati glavu (`Hat.01` + `Head`), tijelo i povijeni rep kape glatko se savijaju kroz `Hat.02` i `Hat.03`, a mjedeni zvončić na vrhu ima `100% HatBell` težinu kako bi zadržao kruti kuglasti oblik dok se njiše.

---

### Izmjena 4 [KORISNIK u Blenderu]: KORAK 3 (Ručni Weight Paint za Tijelo, Glavu i Kapu + Zaključavanje)

Nakon što je početni oštri Bind izračunat, korisnik u **KORAKU 3** N-panela ima potpunu ručnu kontrolu nad sva 3 meša:

1. **A) Početna Širina Zglobova (opcionalno prije ručnog bojanja):**
   - Klizači u centimetrima (`Zglobovi Ruku cm`, `Zglobovi Nogu cm`, `Kralježnica cm`, **`Zglobovi Kape cm`**) i 1-klik preseti (`Oštri 1.0cm`, `Prirodni 1.8cm`, `Mekani 3.5cm`).
2. **B) Ručno Bojanje Težina (1-Klik Weight Paint Studio):**
   - **Automatsko prebacivanje meša (`BODY` / `HEAD AND HAIR` / `HAT`):**
     - Klik na kost tijela/udova automatski otvara Weight Paint na `BODY`.
     - Klik na `Vrat / Glava`, `Brada Gornja` ili `Brada Vrh` automatski otvara Weight Paint na `HEAD AND HAIR`.
     - Klik na **`Obod Kape (Hat.01)`**, **`Tijelo Kape (Hat.02)`**, **`Vrh Kape (Hat.03)`** ili **`Zvončić (HatBell)`** automatski prebacuje aktivni objekt na **`HAT`** u Weight Paint modu (s isključenim `X-Mirror` zbog asimetričnog repa kape).
   - **1-Klik Četke:** `Dodaj 100% (Kruto)`, `Zglob 50%`, `Briši 0%`, `Omekšaj (Blur)`.
   - **1-Klik Testna Poza:**
     - `Savij Laktove/Koljena + Kapu/Bradu (Test)` — savija ruke, nogu, vrh kape (`Hat.02`, `Hat.03`, `HatBell`) i bradu (`Beard.01`, `Beard.02`) kako bi korisnik u stvarnom vremenu provjerio deformaciju svih 3 dijelova.
3. **C) Završetak Weight Painta i Predaja Agentu:**
   - Kad je zadovoljan težinama, korisnik klikne **`Potvrdi i Zaključaj Težine (Spremno za Agenta)`** (`scene.elf01_lock_weights = True`) i javlja Agentu da preuzme Korak 4.

---

### Izmjena 5 [AGENT preko Blender MCP-a]: KORAK 4 (Animacije i Finalni Export bez diranja težina)

1. **Provjera Zaključanih Težina:**
   - Agent provjerava `bpy.context.scene.elf01_lock_weights == True` i **ne pokreće `bind_character_to_rig()`**. Sve korisnikove ručno obojane `vertex_groups` na `BODY`, `HEAD AND HAIR` i `HAT` ostaju 100% očuvane.
2. **Prebacivanje Mixamo / Mocap Animacija (`retarget_mixamo_fbx`):**
   - Koristi hijerarhijski swing-delta retargeter uz automatsku sekundarnu fiziku (follow-through njihanje) za kosti kape (`Hat.02`, `Hat.03`, `HatBell`) i brade (`Beard.01`, `Beard.02`).
3. **Finalni Izvoz:**
   - Izvozi kompletan animirani 3-dijelni lik (`BODY` + `HEAD AND HAIR` + `HAT` + `ARM_Elf_Hero`) u `.glb` i `.blend`.
