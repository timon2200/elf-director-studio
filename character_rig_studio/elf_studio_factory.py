#!/usr/bin/env python3
"""
Advent Lift 2026 — Universal Elf Studio Factory & Multi-Agent Production Manager
=================================================================================
Upravlja cijelim katalogom vilenjaka (28 postojećih + 6 novih prijedloga = 34 lika),
prati stanje kroz 5 izmjena (Korisnik <-> Agent), izrezuje ortografske poglede (1536x1536)
i automatski generira prilagođene `tools/elf<XX>_sculpt_rig_studio.py` N-panel skripte
prema 4-dijelnoj arhitekturi (`BODY` + `HEAD AND HAIR` + `HAT` + `GLASSES`).

Upotreba:
  python3 tools/elf_studio_factory.py --status
  python3 tools/elf_studio_factory.py --print-wave 1
  python3 tools/elf_studio_factory.py --generate-studio 04
  python3 tools/elf_studio_factory.py --slice-sheet <putanja_do_lista.png> --prefix S1_04_head_hair --out-dir <mapa>
"""

import os
import re
import sys
import json
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional

PROJECT_ROOT = Path("/Users/timonterzic/Documents/Projekti/Advent Lift 2026")
KATALOG_DIR = PROJECT_ROOT / "Reference sheets" / "01_Likovi" / "Overwatch_Vilenjaci_Katalog"
GLB_ROOT = PROJECT_ROOT / "assets" / "models" / "glb"
MODELS_ROOT = PROJECT_ROOT / "assets" / "models"
TOOLS_ROOT = PROJECT_ROOT / "tools"
MASTER_STUDIO_TEMPLATE = TOOLS_ROOT / "elf10_sculpt_rig_studio.py"

# ==============================================================================
# MASTER KATALOG: 28 POSTOJEĆIH + 6 NOVIH PREDLOŽENIH VILENJAKA (UKUPNO 34)
# Podijeljeni u 4 Proizvodna Vala (Tier 1 - Tier 4)
# ==============================================================================
ELF_PRODUCTION_ROSTER: List[Dict[str, Any]] = [
    # --- GOTOVI / U RADU (VAL 0 — Pilot Referentni Modeli) ---
    {
        "num": 1,
        "id": "S0_01_kondukter_pecat_M_stariji",
        "slug": "kondukter",
        "stage_dir": "00_Ukrcaj_Sermage",
        "hr_name": "Stariji Kondukter s Cvikalicom za Karte",
        "wave": 0,
        "tier": "Pilot (Gotov 2-Part / Rig-Ready)",
        "sex": "M",
        "age": 60,
        "costume_archetype": "Costume_2_LongToggleCoat_Capelet",
        "hat_archetype": "Hat_A_PointedGreenRedZigzag",
        "parts": ["BODY", "HEAD AND HAIR"],
        "has_beard": False,
        "has_glasses": True,
        "blend_file": "elf01_kondukter_rig_ready.blend",
        "studio_script": "elf01_sculpt_rig_studio.py",
        "glb_folder": "elf_01_kondukter_modular",
    },
    {
        "num": 10,
        "id": "S3_10_urar_vijecnice_M_stari",
        "slug": "urar",
        "stage_dir": "03_Reveal_Grad_i_Korzo",
        "hr_name": "Stari Urar Tornja Varaždinske Vijećnice",
        "wave": 0,
        "tier": "Pilot (Gotov 4-Part Master Standard)",
        "sex": "M",
        "age": 72,
        "costume_archetype": "Costume_5_LongToggleCoat_Waistcoat",
        "hat_archetype": "Hat_A_PointedGreenRedZigzag",
        "parts": ["BODY", "HEAD AND HAIR", "HAT", "GLASSES"],
        "has_beard": True,
        "has_glasses": True,
        "blend_file": "elf10_urar_rig_ready.blend",
        "studio_script": "elf10_sculpt_rig_studio.py",
        "glb_folder": "elf_10_urar_modular",
    },
    {
        "num": 24,
        "id": "S5A_24_hvatacica_pisama_F_mlada",
        "slug": "hvatacica_pisama",
        "stage_dir": "05A_Posta_i_Knjiznica",
        "hr_name": "Hvatačica Letećih Pisama i Operaterka Pneumatike",
        "wave": 0,
        "tier": "Pilot (Gotov 2-Part)",
        "sex": "F",
        "age": 23,
        "costume_archetype": "Costume_7_CrimsonScallopedVest_F",
        "hat_archetype": "Hat_C_CrimsonVelvetCap",
        "parts": ["BODY", "HEAD AND HAIR", "HAT"],
        "has_beard": False,
        "has_glasses": True,
        "blend_file": "elf24_hvatacica_pisama_rig_ready.blend",
        "studio_script": "elf24_sculpt_rig_studio.py",
        "glb_folder": "elf_24_v2_75h_modular",
    },

    # --- VAL 1 (TIER 1): HERO LIKOVI U PRVOM PLANU (8 ključnih protagonista po scenama) ---
    {
        "num": 4,
        "id": "S1_04_inzenjer_poluge_M_srednji",
        "slug": "inzenjer_poluge",
        "stage_dir": "01_Podzemna_Stanica",
        "hr_name": "Glavni Inženjer Kočione Poluge",
        "wave": 1,
        "tier": "Val 1 — Hero Prvi Plan (Scena 1: Kočiona stanica)",
        "sex": "M",
        "age": 48,
        "costume_archetype": "Costume_1_GreenOveralls_Turtleneck_M",
        "hat_archetype": "Hat_A_PointedGreenRedZigzag",
        "parts": ["BODY", "HEAD AND HAIR", "HAT", "GLASSES"],
        "has_beard": False,
        "has_glasses": True,
        "blend_file": "elf04_inzenjer_poluge_rig_ready.blend",
        "studio_script": "elf04_sculpt_rig_studio.py",
        "glb_folder": "elf_04_inzenjer_poluge_modular",
    },
    {
        "num": 6,
        "id": "S2_06_strojovodja_lokomotive_M_iskusni",
        "slug": "strojovodja",
        "stage_dir": "02_Tunel_i_Vlakic",
        "hr_name": "Strojovođa Podzemnog Teretnog Vlakića",
        "wave": 1,
        "tier": "Val 1 — Hero Prvi Plan (Scena 2: Paralelni vlakić u tunelu)",
        "sex": "M",
        "age": 54,
        "costume_archetype": "Costume_2_LongToggleCoat_M",
        "hat_archetype": "Hat_B_CrimsonSantaHat",
        "parts": ["BODY", "HEAD AND HAIR", "HAT", "GLASSES"],
        "has_beard": False,
        "has_glasses": True,
        "blend_file": "elf06_strojovodja_rig_ready.blend",
        "studio_script": "elf06_sculpt_rig_studio.py",
        "glb_folder": "elf_06_strojovodja_modular",
    },
    {
        "num": 13,
        "id": "S3_13_cuvar_vijadukta_M_visoki",
        "slug": "cuvar_vijadukta",
        "stage_dir": "03_Reveal_Grad_i_Korzo",
        "hr_name": "Stražar i Trubač na Vijaduktu",
        "wave": 1,
        "tier": "Val 1 — Hero Prvi Plan (Scena 3: Izlazak na vijadukt s trubom)",
        "sex": "M",
        "age": 40,
        "costume_archetype": "Costume_4_SplitTailTunic_Capelet_M",
        "hat_archetype": "Hat_A_PointedGreenRedZigzag",
        "parts": ["BODY", "HEAD AND HAIR", "HAT"],
        "has_beard": False,
        "has_glasses": False,
        "blend_file": "elf13_cuvar_vijadukta_rig_ready.blend",
        "studio_script": "elf13_sculpt_rig_studio.py",
        "glb_folder": "elf_13_cuvar_vijadukta_modular",
    },
    {
        "num": 14,
        "id": "S4_14_stolar_majstor_M_srednji",
        "slug": "stolar_majstor",
        "stage_dir": "04_Tvornica_Igracaka",
        "hr_name": "Majstor Stolar i Tokar Igračaka",
        "wave": 1,
        "tier": "Val 1 — Hero Prvi Plan (Scena 4: Tvornica Stanica 1)",
        "sex": "M",
        "age": 50,
        "costume_archetype": "Costume_1_GreenOveralls_Turtleneck_M",
        "hat_archetype": "Hat_A_PointedGreenRedZigzag",
        "parts": ["BODY", "HEAD AND HAIR", "HAT"],
        "has_beard": True,
        "has_glasses": False,
        "blend_file": "elf14_stolar_majstor_rig_ready.blend",
        "studio_script": "elf14_sculpt_rig_studio.py",
        "glb_folder": "elf_14_stolar_majstor_modular",
    },
    {
        "num": 16,
        "id": "S4_16_bojadisarica_konjica_F_mlada",
        "slug": "bojadisarica",
        "stage_dir": "04_Tvornica_Igracaka",
        "hr_name": "Bojadišarica Drvenih Konjića i Orašara",
        "wave": 1,
        "tier": "Val 1 — Hero Prvi Plan (Scena 4: Tvornica Stanica 2)",
        "sex": "F",
        "age": 27,
        "costume_archetype": "Costume_6_GreenPinaforeDress_F",
        "hat_archetype": "Hat_B_CrimsonSantaHat",
        "parts": ["BODY", "HEAD AND HAIR", "HAT"],
        "has_beard": False,
        "has_glasses": False,
        "blend_file": "elf16_bojadisarica_rig_ready.blend",
        "studio_script": "elf16_sculpt_rig_studio.py",
        "glb_folder": "elf_16_bojadisarica_modular",
    },
    {
        "num": 21,
        "id": "S4_21_glavni_pekar_medenjaka_M_krupni",
        "slug": "pekar_medenjaka",
        "stage_dir": "04_Tvornica_Igracaka",
        "hr_name": "Glavni Pekar Medenjaka (Peć Broj 3)",
        "wave": 1,
        "tier": "Val 1 — Hero Prvi Plan (Scena 4: Peć br. 3 & Radio oglas)",
        "sex": "M",
        "age": 58,
        "costume_archetype": "Costume_Baker_PlumpApron_M",
        "hat_archetype": "Hat_B_CrimsonSantaHat",
        "parts": ["BODY", "HEAD AND HAIR", "HAT"],
        "has_beard": True,
        "has_glasses": False,
        "blend_file": "elf21_pekar_medenjaka_rig_ready.blend",
        "studio_script": "elf21_sculpt_rig_studio.py",
        "glb_folder": "elf_21_pekar_medenjaka_modular",
    },
    {
        "num": 23,
        "id": "S5A_23_stari_birokrat_salter_M_stari",
        "slug": "stari_birokrat",
        "stage_dir": "05A_Posta_i_Knjiznica",
        "hr_name": "Stari Birokrat sa Šaltera (Glavni Pečatar)",
        "wave": 1,
        "tier": "Val 1 — Hero Prvi Plan (Scena 5A: Poštanski šalter)",
        "sex": "M",
        "age": 70,
        "costume_archetype": "Costume_3_CrimsonJesterCollar_M",
        "hat_archetype": "Hat_A_PointedGreenRedZigzag",
        "parts": ["BODY", "HEAD AND HAIR", "HAT", "GLASSES"],
        "has_beard": True,
        "has_glasses": True,
        "blend_file": "elf23_stari_birokrat_rig_ready.blend",
        "studio_script": "elf23_sculpt_rig_studio.py",
        "glb_folder": "elf_23_stari_birokrat_modular",
    },
    {
        "num": 28,
        "id": "S5B_28_osobni_pomocnik_djeda_M_mladi",
        "slug": "pomocnik_djeda",
        "stage_dir": "05B_Hangar_i_Djed_Mraz",
        "hr_name": "Mladi Osobni Pomoćnik uz Fotelju Djeda Mraza",
        "wave": 1,
        "tier": "Val 1 — Hero Prvi Plan (Scena 5B: Finale uz Djedovu fotelju)",
        "sex": "M",
        "age": 21,
        "costume_archetype": "Costume_3_CrimsonJesterCollar_M",
        "hat_archetype": "Hat_B_CrimsonSantaHat",
        "parts": ["BODY", "HEAD AND HAIR", "HAT"],
        "has_beard": False,
        "has_glasses": False,
        "blend_file": "elf28_pomocnik_djeda_rig_ready.blend",
        "studio_script": "elf28_sculpt_rig_studio.py",
        "glb_folder": "elf_28_pomocnik_djeda_modular",
    },

    # --- VAL 2 (TIER 2): SREDNJI PLAN I SPECIFIČNE RADNE STANICE (10 vilenjaka) ---
    {
        "num": 2,
        "id": "S0_02_zvono_vratarka_F_mlada",
        "slug": "zvono_vratarka",
        "stage_dir": "00_Ukrcaj_Sermage",
        "hr_name": "Mlada Vratarka sa Zvonom za Polazak",
        "wave": 2,
        "tier": "Val 2 — Srednji Plan (Faza 0: Ukrcaj Sermage)",
        "sex": "F",
        "age": 20,
        "costume_archetype": "Costume_7_CrimsonScallopedVest_F",
        "hat_archetype": "Hat_B_CrimsonSantaHat",
        "parts": ["BODY", "HEAD AND HAIR", "HAT"],
        "has_beard": False,
        "has_glasses": False,
        "blend_file": "elf02_zvono_vratarka_rig_ready.blend",
        "studio_script": "elf02_sculpt_rig_studio.py",
        "glb_folder": "elf_02_zvono_vratarka_modular",
    },
    {
        "num": 5,
        "id": "S1_05_inspektorica_manometara_F_srednja",
        "slug": "inspektorica_manometara",
        "stage_dir": "01_Podzemna_Stanica",
        "hr_name": "Inspektorica Tlačnih Manometara i Fenjera",
        "wave": 2,
        "tier": "Val 2 — Srednji Plan (Scena 1: Podzemna stanica)",
        "sex": "F",
        "age": 35,
        "costume_archetype": "Costume_4_GreenJacket_Capelet_F",
        "hat_archetype": "Hat_C_CrimsonVelvetCap",
        "parts": ["BODY", "HEAD AND HAIR", "HAT", "GLASSES"],
        "has_beard": False,
        "has_glasses": True,
        "blend_file": "elf05_inspektorica_rig_ready.blend",
        "studio_script": "elf05_sculpt_rig_studio.py",
        "glb_folder": "elf_05_inspektorica_modular",
    },
    {
        "num": 7,
        "id": "S2_07_skretnicarka_tunela_F_mlada",
        "slug": "skretnicarka",
        "stage_dir": "02_Tunel_i_Vlakic",
        "hr_name": "Skretničarka sa Signalnim Zastavicama",
        "wave": 2,
        "tier": "Val 2 — Srednji Plan (Scena 2: Y-skretnica u tunelu)",
        "sex": "F",
        "age": 26,
        "costume_archetype": "Costume_3_CrimsonJesterCollar_F",
        "hat_archetype": "Hat_A_PointedGreenRedZigzag",
        "parts": ["BODY", "HEAD AND HAIR", "HAT"],
        "has_beard": False,
        "has_glasses": False,
        "blend_file": "elf07_skretnicarka_rig_ready.blend",
        "studio_script": "elf07_sculpt_rig_studio.py",
        "glb_folder": "elf_07_skretnicarka_modular",
    },
    {
        "num": 8,
        "id": "S2_08_spiker_radio_megazvon_M_sarmantni",
        "slug": "spiker_megazvon",
        "stage_dir": "02_Tunel_i_Vlakic",
        "hr_name": "Spiker „Radio Megazvona”",
        "wave": 2,
        "tier": "Val 2 — Srednji Plan (Scena 2: Glasovni studio u niši)",
        "sex": "M",
        "age": 38,
        "costume_archetype": "Costume_7_CrimsonScallopedVest_M",
        "hat_archetype": "Hat_A_PointedGreenRedZigzag",
        "parts": ["BODY", "HEAD AND HAIR", "HAT"],
        "has_beard": True,
        "has_glasses": False,
        "blend_file": "elf08_spiker_megazvon_rig_ready.blend",
        "studio_script": "elf08_sculpt_rig_studio.py",
        "glb_folder": "elf_08_spiker_megazvon_modular",
    },
    {
        "num": 11,
        "id": "S3_11_ukrasavacica_bora_korzo_F_mlada",
        "slug": "ukrasavacica_bora",
        "stage_dir": "03_Reveal_Grad_i_Korzo",
        "hr_name": "Ukrašavačica Velikog Bora na Korzu",
        "wave": 2,
        "tier": "Val 2 — Srednji Plan (Scena 3: Bor na Korzu)",
        "sex": "F",
        "age": 24,
        "costume_archetype": "Costume_6_GreenPinaforeDress_F",
        "hat_archetype": "Hat_B_CrimsonSantaHat",
        "parts": ["BODY", "HEAD AND HAIR", "HAT"],
        "has_beard": False,
        "has_glasses": False,
        "blend_file": "elf11_ukrasavacica_bora_rig_ready.blend",
        "studio_script": "elf11_sculpt_rig_studio.py",
        "glb_folder": "elf_11_ukrasavacica_bora_modular",
    },
    {
        "num": 18,
        "id": "S4_18_monter_mehanizama_M_mladi",
        "slug": "monter_mehanizama",
        "stage_dir": "04_Tvornica_Igracaka",
        "hr_name": "Monter Mehanizama na Navijanje",
        "wave": 2,
        "tier": "Val 2 — Srednji Plan (Scena 4: Tvornica Stanica 3 & Strojarnica)",
        "sex": "M",
        "age": 30,
        "costume_archetype": "Costume_4_GreenJacket_Capelet_M",
        "hat_archetype": "Hat_C_CrimsonVelvetCap",
        "parts": ["BODY", "HEAD AND HAIR", "HAT", "GLASSES"],
        "has_beard": False,
        "has_glasses": True,
        "blend_file": "elf18_monter_mehanizama_rig_ready.blend",
        "studio_script": "elf18_sculpt_rig_studio.py",
        "glb_folder": "elf_18_monter_mehanizama_modular",
    },
    {
        "num": 20,
        "id": "S4_20_pakirerica_masni_F_vesela",
        "slug": "pakirerica_masni",
        "stage_dir": "04_Tvornica_Igracaka",
        "hr_name": "Pakirerica Darova i Majstorica Mašni",
        "wave": 2,
        "tier": "Val 2 — Srednji Plan (Scena 4: Tvornica Stanica 4 Pakirnica)",
        "sex": "F",
        "age": 22,
        "costume_archetype": "Costume_3_CrimsonJesterCollar_F",
        "hat_archetype": "Hat_B_CrimsonSantaHat",
        "parts": ["BODY", "HEAD AND HAIR", "HAT"],
        "has_beard": False,
        "has_glasses": False,
        "blend_file": "elf20_pakirerica_masni_rig_ready.blend",
        "studio_script": "elf20_sculpt_rig_studio.py",
        "glb_folder": "elf_20_pakirerica_masni_modular",
    },
    {
        "num": 25,
        "id": "S5A_25_knjiznicarka_arhive_F_visoka",
        "slug": "knjiznicarka_arhive",
        "stage_dir": "05A_Posta_i_Knjiznica",
        "hr_name": "Glavna Knjižničarka „Arhive Dobrih”",
        "wave": 2,
        "tier": "Val 2 — Srednji Plan (Scena 5A: Knjižnica na ljestvama)",
        "sex": "F",
        "age": 52,
        "costume_archetype": "Costume_5_LongToggleCoat_F",
        "hat_archetype": "Hat_A_PointedGreenRedZigzag",
        "parts": ["BODY", "HEAD AND HAIR", "HAT", "GLASSES"],
        "has_beard": False,
        "has_glasses": True,
        "blend_file": "elf25_knjiznicarka_rig_ready.blend",
        "studio_script": "elf25_sculpt_rig_studio.py",
        "glb_folder": "elf_25_knjiznicarka_modular",
    },
    {
        "num": 26,
        "id": "S5B_26_konjusar_sobova_M_snazni",
        "slug": "konjusar_sobova",
        "stage_dir": "05B_Hangar_i_Djed_Mraz",
        "hr_name": "Glavni Konjušar i Timaritelj Sobova",
        "wave": 2,
        "tier": "Val 2 — Srednji Plan (Scena 5B: Hangar sa sobovima)",
        "sex": "M",
        "age": 45,
        "costume_archetype": "Costume_2_LongToggleCoat_Capelet",
        "hat_archetype": "Hat_A_PointedGreenRedZigzag",
        "parts": ["BODY", "HEAD AND HAIR", "HAT"],
        "has_beard": True,
        "has_glasses": False,
        "blend_file": "elf26_konjusar_sobova_rig_ready.blend",
        "studio_script": "elf26_sculpt_rig_studio.py",
        "glb_folder": "elf_26_konjusar_sobova_modular",
    },
    {
        "num": 27,
        "id": "S5B_27_majstorica_sanjki_F_srednja",
        "slug": "majstorica_sanjki",
        "stage_dir": "05B_Hangar_i_Djed_Mraz",
        "hr_name": "Majstorica za Mjedene Salinje i Kompas Sanjki",
        "wave": 2,
        "tier": "Val 2 — Srednji Plan (Scena 5B: Hangar uz Djedove sanjke)",
        "sex": "F",
        "age": 34,
        "costume_archetype": "Costume_1_GreenOveralls_Turtleneck_F",
        "hat_archetype": "Hat_A_PointedGreenRedZigzag",
        "parts": ["BODY", "HEAD AND HAIR", "HAT", "GLASSES"],
        "has_beard": False,
        "has_glasses": True,
        "blend_file": "elf27_majstorica_sanjki_rig_ready.blend",
        "studio_script": "elf27_sculpt_rig_studio.py",
        "glb_folder": "elf_27_majstorica_sanjki_modular",
    },

    # --- VAL 3 (TIER 3): KITBASH / DIJELJENA TIJELA ZA POPUNJAVANJE PROSTORA (7 vilenjaka) ---
    {
        "num": 3,
        "id": "S0_03_garderobijer_prtljaga_M_krupni",
        "slug": "garderobijer",
        "stage_dir": "00_Ukrcaj_Sermage",
        "hr_name": "Krupni Garderobijer i Nosač",
        "wave": 3,
        "tier": "Val 3 — Kitbash (Nova glava + dijeljeno krupno tijelo #21)",
        "sex": "M",
        "age": 42,
        "costume_archetype": "Costume_4_SplitTailTunic_Plump_M",
        "hat_archetype": "Hat_A_PointedGreenRedZigzag",
        "parts": ["BODY", "HEAD AND HAIR", "HAT"],
        "has_beard": True,
        "has_glasses": False,
        "blend_file": "elf03_garderobijer_rig_ready.blend",
        "studio_script": "elf03_sculpt_rig_studio.py",
        "glb_folder": "elf_03_garderobijer_modular",
    },
    {
        "num": 9,
        "id": "S2_09_kocnicar_vagona_M_mladi",
        "slug": "kocnicar_vagona",
        "stage_dir": "02_Tunel_i_Vlakic",
        "hr_name": "Mladi Kočničar na Vagonu s Igračkama",
        "wave": 3,
        "tier": "Val 3 — Kitbash (Nova glava + dijeljeno tijelo kombinezona #04/#14)",
        "sex": "M",
        "age": 19,
        "costume_archetype": "Costume_1_GreenOveralls_Turtleneck_M",
        "hat_archetype": "Hat_B_CrimsonSantaHat",
        "parts": ["BODY", "HEAD AND HAIR", "HAT"],
        "has_beard": False,
        "has_glasses": False,
        "blend_file": "elf09_kocnicar_vagona_rig_ready.blend",
        "studio_script": "elf09_sculpt_rig_studio.py",
        "glb_folder": "elf_09_kocnicar_vagona_modular",
    },
    {
        "num": 12,
        "id": "S3_12_nosacica_poklona_korzo_F_starija",
        "slug": "nosacica_poklona",
        "stage_dir": "03_Reveal_Grad_i_Korzo",
        "hr_name": "Starija Vilenjakinja s Korza (Mještanka)",
        "wave": 3,
        "tier": "Val 3 — Srednji Plan / Kitbash (Scena 3: Korzo)",
        "sex": "F",
        "age": 56,
        "costume_archetype": "Costume_3_CrimsonJesterCollar_Matron_F",
        "hat_archetype": "Hat_A_PointedGreenRedZigzag",
        "parts": ["BODY", "HEAD AND HAIR", "HAT", "GLASSES"],
        "has_beard": False,
        "has_glasses": True,
        "blend_file": "elf12_nosacica_poklona_rig_ready.blend",
        "studio_script": "elf12_sculpt_rig_studio.py",
        "glb_folder": "elf_12_nosacica_poklona_modular",
    },
    {
        "num": 15,
        "id": "S4_15_segrt_stolar_M_mladi",
        "slug": "segrt_stolar",
        "stage_dir": "04_Tvornica_Igracaka",
        "hr_name": "Mladi Šegrt Stolar (Brušenje Drveta)",
        "wave": 3,
        "tier": "Val 3 — Kitbash (Nova glava + dijeljeno tijelo #28/#13)",
        "sex": "M",
        "age": 17,
        "costume_archetype": "Costume_4_SplitTailTunic_Apron_M",
        "hat_archetype": "Hat_B_CrimsonSantaHat",
        "parts": ["BODY", "HEAD AND HAIR", "HAT"],
        "has_beard": False,
        "has_glasses": False,
        "blend_file": "elf15_segrt_stolar_rig_ready.blend",
        "studio_script": "elf15_sculpt_rig_studio.py",
        "glb_folder": "elf_15_segrt_stolar_modular",
    },
    {
        "num": 17,
        "id": "S4_17_krojacica_plisanaca_F_starija",
        "slug": "krojacica_plisanaca",
        "stage_dir": "04_Tvornica_Igracaka",
        "hr_name": "Starija Krojačica Plišanih Igračaka i Lutaka",
        "wave": 3,
        "tier": "Val 3 — Kitbash (Nova glava + dijeljeno tijelo #12/#24)",
        "sex": "F",
        "age": 62,
        "costume_archetype": "Costume_7_CrimsonScallopedVest_F",
        "hat_archetype": "Hat_C_CrimsonVelvetCap",
        "parts": ["BODY", "HEAD AND HAIR", "HAT", "GLASSES"],
        "has_beard": False,
        "has_glasses": True,
        "blend_file": "elf17_krojacica_rig_ready.blend",
        "studio_script": "elf17_sculpt_rig_studio.py",
        "glb_folder": "elf_17_krojacica_modular",
    },
    {
        "num": 19,
        "id": "S4_19_kontrolorka_kvalitete_F_stroga",
        "slug": "kontrolorka_kvalitete",
        "stage_dir": "04_Tvornica_Igracaka",
        "hr_name": "Glavna Kontrolorka Kvalitete Igračaka",
        "wave": 3,
        "tier": "Val 3 — Kitbash (Nova glava + dijeljeno visoko tijelo #25)",
        "sex": "F",
        "age": 46,
        "costume_archetype": "Costume_2_LongToggleCoat_F",
        "hat_archetype": "Hat_A_PointedGreenRedZigzag",
        "parts": ["BODY", "HEAD AND HAIR", "HAT", "GLASSES"],
        "has_beard": False,
        "has_glasses": True,
        "blend_file": "elf19_kontrolorka_rig_ready.blend",
        "studio_script": "elf19_sculpt_rig_studio.py",
        "glb_folder": "elf_19_kontrolorka_modular",
    },
    {
        "num": 22,
        "id": "S4_22_slasticarka_glazure_F_mlada",
        "slug": "slasticarka_glazure",
        "stage_dir": "04_Tvornica_Igracaka",
        "hr_name": "Mlada Slastičarka i Licitarka (Ukrašavanje Medenjaka)",
        "wave": 3,
        "tier": "Val 3 — Kitbash (Nova glava + dijeljeno tijelo pregače #16/#11)",
        "sex": "F",
        "age": 19,
        "costume_archetype": "Costume_6_GreenPinaforeDress_F",
        "hat_archetype": "Hat_A_PointedGreenRedZigzag",
        "parts": ["BODY", "HEAD AND HAIR", "HAT"],
        "has_beard": False,
        "has_glasses": False,
        "blend_file": "elf22_slasticarka_rig_ready.blend",
        "studio_script": "elf22_sculpt_rig_studio.py",
        "glb_folder": "elf_22_slasticarka_modular",
    },

    # --- VAL 4 (TIER 4): 6 NOVIH PREDLOŽENIH ULOGA ZA STROJARNICU, KORZO ZBOR I HANGAR ---
    {
        "num": 29,
        "id": "S3_29_dirigent_zbora_korzo_M_stariji",
        "slug": "dirigent_zbora",
        "stage_dir": "03_Reveal_Grad_i_Korzo",
        "hr_name": "Dirigent Vilenjačkog Zbora na Korzu (Kanal 3 Kulminacija)",
        "wave": 4,
        "tier": "Val 4 — Novi Prijedlog (Scena 3: Dirigent Božićne pjesme na Korzu)",
        "sex": "M",
        "age": 64,
        "costume_archetype": "Costume_2_LongToggleCoat_Capelet",
        "hat_archetype": "Hat_A_PointedGreenRedZigzag",
        "parts": ["BODY", "HEAD AND HAIR", "HAT", "GLASSES"],
        "has_beard": False,
        "has_glasses": True,
        "blend_file": "elf29_dirigent_zbora_rig_ready.blend",
        "studio_script": "elf29_sculpt_rig_studio.py",
        "glb_folder": "elf_29_dirigent_zbora_modular",
    },
    {
        "num": 30,
        "id": "S1_30_uljar_zupcanika_strojarnica_M_srednji",
        "slug": "uljar_strojarnica",
        "stage_dir": "01_Podzemna_Stanica",
        "hr_name": "Majstor Podmazivač Velikih Zupčanika (Strojarnica / Swiss Watch)",
        "wave": 4,
        "tier": "Val 4 — Novi Prijedlog (Strojarnica s mjedenim zupčanicima)",
        "sex": "M",
        "age": 44,
        "costume_archetype": "Costume_1_GreenOveralls_Turtleneck_M",
        "hat_archetype": "Hat_C_CrimsonVelvetCap",
        "parts": ["BODY", "HEAD AND HAIR", "HAT", "GLASSES"],
        "has_beard": True,
        "has_glasses": True,
        "blend_file": "elf30_uljar_strojarnica_rig_ready.blend",
        "studio_script": "elf30_sculpt_rig_studio.py",
        "glb_folder": "elf_30_uljar_strojarnica_modular",
    },
    {
        "num": 31,
        "id": "S3_31_vilenjak_Verglas_glazbenik_M_mladi",
        "slug": "verglas_glazbenik",
        "stage_dir": "03_Reveal_Grad_i_Korzo",
        "hr_name": "Svirač Mehaničkog Vergleca na Korzu",
        "wave": 4,
        "tier": "Val 4 — Novi Prijedlog (Scena 3: Mehanički verglec na trgu)",
        "sex": "M",
        "age": 29,
        "costume_archetype": "Costume_7_CrimsonScallopedVest_M",
        "hat_archetype": "Hat_A_PointedGreenRedZigzag",
        "parts": ["BODY", "HEAD AND HAIR", "HAT"],
        "has_beard": False,
        "has_glasses": False,
        "blend_file": "elf31_verglas_glazbenik_rig_ready.blend",
        "studio_script": "elf31_sculpt_rig_studio.py",
        "glb_folder": "elf_31_verglas_glazbenik_modular",
    },
    {
        "num": 32,
        "id": "S4_32_kovac_mjedenih_zvona_M_snazni",
        "slug": "kovac_zvona",
        "stage_dir": "04_Tvornica_Igracaka",
        "hr_name": "Ljevač i Ugađač Mjedenih Praporaca (Tvornica)",
        "wave": 4,
        "tier": "Val 4 — Novi Prijedlog (Scena 4: Ljevaonica praporaca)",
        "sex": "M",
        "age": 51,
        "costume_archetype": "Costume_4_SplitTailTunic_Apron_M",
        "hat_archetype": "Hat_C_CrimsonVelvetCap",
        "parts": ["BODY", "HEAD AND HAIR", "HAT", "GLASSES"],
        "has_beard": True,
        "has_glasses": True,
        "blend_file": "elf32_kovac_zvona_rig_ready.blend",
        "studio_script": "elf32_sculpt_rig_studio.py",
        "glb_folder": "elf_32_kovac_zvona_modular",
    },
    {
        "num": 33,
        "id": "S5A_33_cistac_pneumatskih_cijevi_M_mladi",
        "slug": "cistac_cijevi",
        "stage_dir": "05A_Posta_i_Knjiznica",
        "hr_name": "Akrobatski Serviser Pneumatskih Cijevi za Pisma",
        "wave": 4,
        "tier": "Val 4 — Novi Prijedlog (Scena 5A: Odglavljivanje pisama u cijevima)",
        "sex": "M",
        "age": 22,
        "costume_archetype": "Costume_1_GreenOveralls_Turtleneck_M",
        "hat_archetype": "Hat_B_CrimsonSantaHat",
        "parts": ["BODY", "HEAD AND HAIR", "HAT", "GLASSES"],
        "has_beard": False,
        "has_glasses": True,
        "blend_file": "elf33_cistac_cijevi_rig_ready.blend",
        "studio_script": "elf33_sculpt_rig_studio.py",
        "glb_folder": "elf_33_cistac_cijevi_modular",
    },
    {
        "num": 34,
        "id": "S5B_34_dispecerica_leta_aurorom_F_starija",
        "slug": "dispecerica_leta",
        "stage_dir": "05B_Hangar_i_Djed_Mraz",
        "hr_name": "Glavna Navigatorica Aurore i Lansirne Rampe Sanjki",
        "wave": 4,
        "tier": "Val 4 — Novi Prijedlog (Scena 5B: Kontrola polijetanja u Hangaru)",
        "sex": "F",
        "age": 55,
        "costume_archetype": "Costume_2_LongToggleCoat_F",
        "hat_archetype": "Hat_A_PointedGreenRedZigzag",
        "parts": ["BODY", "HEAD AND HAIR", "HAT", "GLASSES"],
        "has_beard": False,
        "has_glasses": True,
        "blend_file": "elf34_dispecerica_leta_rig_ready.blend",
        "studio_script": "elf34_sculpt_rig_studio.py",
        "glb_folder": "elf_34_dispecerica_leta_modular",
    },
]


def inspect_elf_status(entry: Dict[str, Any]) -> Dict[str, Any]:
    stage_path = KATALOG_DIR / entry["stage_dir"]
    full_2d = stage_path / f"VZ_elf_{entry['id']}__overwatch_gpt_2_5.png"
    mod_dir = stage_path / f"{entry['num']:02d}_Modular_75H"
    glb_dir = GLB_ROOT / entry["glb_folder"]
    blend_path = MODELS_ROOT / entry["blend_file"]
    studio_path = TOOLS_ROOT / entry["studio_script"]

    glb_files = list(glb_dir.glob("*.glb")) if glb_dir.exists() else []
    mod_pngs = list(mod_dir.glob("*.png")) if mod_dir.exists() else []

    return {
        "num": entry["num"],
        "id": entry["id"],
        "hr_name": entry["hr_name"],
        "wave": entry["wave"],
        "has_2d_full": full_2d.exists(),
        "mod_2d_count": len(mod_pngs),
        "glb_count": len(glb_files),
        "has_studio_py": studio_path.exists(),
        "has_blend": blend_path.exists(),
    }


def print_status_table() -> None:
    print("=" * 118)
    print(f"{'#':<3} | {'Val':<5} | {'ID':<38} | {'2D Full':<7} | {'2D Mod':<6} | {'3D GLB':<6} | {'Studio.py':<9} | {'.blend':<6} | {'Naziv'}")
    print("-" * 118)
    for entry in sorted(ELF_PRODUCTION_ROSTER, key=lambda x: (x["wave"], x["num"])):
        st = inspect_elf_status(entry)
        w_str = f"W{st['wave']}" if st["wave"] > 0 else "DONE"
        f2d = "DA" if st["has_2d_full"] else "NE"
        m2d = f"{st['mod_2d_count']} list" if st["mod_2d_count"] > 0 else "-"
        glb = f"{st['glb_count']} glb" if st["glb_count"] > 0 else "-"
        spy = "DA" if st["has_studio_py"] else "-"
        bld = "DA" if st["has_blend"] else "-"
        print(
            f"{st['num']:02d}  | {w_str:<5} | {st['id']:<38} | {f2d:<7} | {m2d:<6} | {glb:<6} | {spy:<9} | {bld:<6} | {st['hr_name']}"
        )
    print("=" * 118)


def slice_3view_sheet(sheet_path: Path, prefix: str, out_dir: Path, size: int = 1536, bg_rgb=(128, 128, 128)) -> List[Path]:
    """
    Izrezuje horizontalni 3-pogledni list (FRONT, LEFT PROFILE, BACK) u 4 uniformna 1:1 kvadrata
    (front.png, left.png, back.png, right.png) s centriranjem na #808080 pozadini.
    """
    from PIL import Image

    im = Image.open(sheet_path).convert("RGB")
    w, h = im.size
    third = w // 3
    crops = {
        "front": im.crop((0, 0, third, h)),
        "left": im.crop((third, 0, 2 * third, h)),
        "back": im.crop((2 * third, 0, w, h)),
    }
    crops["right"] = crops["left"].transpose(Image.FLIP_LEFT_RIGHT)

    out_dir.mkdir(parents=True, exist_ok=True)
    saved: List[Path] = []
    for view_name, view_im in crops.items():
        vw, vh = view_im.size
        scale = min((size * 0.92) / vw, (size * 0.92) / vh)
        nw, nh = int(round(vw * scale)), int(round(vh * scale))
        resized = view_im.resize((nw, nh), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (size, size), bg_rgb)
        canvas.paste(resized, ((size - nw) // 2, (size - nh) // 2))
        out_path = out_dir / f"{prefix}_{view_name}.png"
        canvas.save(out_path, "PNG")
        saved.append(out_path)
    return saved


def generate_studio_script_for_elf(elf_num: int) -> Path:
    """
    Generira prilagođenu `tools/elf<XX>_sculpt_rig_studio.py` skriptu iz master predloška
    `tools/elf10_sculpt_rig_studio.py` za odabranog vilenjaka.
    """
    matches = [e for e in ELF_PRODUCTION_ROSTER if e["num"] == elf_num]
    if not matches:
        raise ValueError(f"Vilenjak #{elf_num:02d} nije pronađen u ELF_PRODUCTION_ROSTER.")
    entry = matches[0]

    code = MASTER_STUDIO_TEMPLATE.read_text(encoding="utf-8")
    short_code = "_".join(entry["id"].split("_")[:2])  # e.g. S1_04
    num_str = f"{elf_num:02d}"

    # Prilagodba putanja, naziva objekata i N-panel zaglavlja
    code = code.replace(
        "Elf #10 (Stari Urar Tornja Varaždinske Vijećnice — S3_10_urar_vijecnice_M_stari)",
        f"Elf #{num_str} ({entry['hr_name']} — {entry['id']})",
    )
    code = code.replace("elf_10_urar_modular", entry["glb_folder"])
    code = code.replace("elf10_S3_10_", f"elf{num_str}_{short_code}_")
    code = code.replace("elf10_urar_rig_ready.blend", entry["blend_file"])
    code = code.replace("elf10_sculpt_rig_studio.py", entry["studio_script"])
    code = code.replace(
        'bl_label = "Elf #10 Rig Studio (Urar + Kapa)"',
        f'bl_label = "Elf #{num_str} Rig Studio ({entry["hr_name"][:26]})"',
    )
    if elf_num == 24:
        code = code.replace("RAW_HEAD_SCALE = 1.34", "RAW_HEAD_SCALE = 1.62")
        code = code.replace("RAW_HEAD_NECK_PIVOT = (0.0, 0.032, -0.095)", "RAW_HEAD_NECK_PIVOT = (0.0, 0.015, -0.015)")
        code = code.replace("DEFAULT_HEAD_PIVOT = (0.0, -0.016, 1.742)", "DEFAULT_HEAD_PIVOT = (0.0, -0.012, 1.662)")
        code = code.replace("DEFAULT_GLASSES_PIVOT = (0.004, -0.122, 1.908)", "DEFAULT_GLASSES_PIVOT = (0.002, -0.118, 1.778)")
        code = code.replace("RAW_HAT_SCALE = 0.90", "RAW_HAT_SCALE = 1.08")
        code = code.replace("DEFAULT_HAT_PIVOT = (0.014, -0.004, 1.972)", "DEFAULT_HAT_PIVOT = (0.004, 0.012, 1.772)")
    elif not entry.get("has_beard", False):
        code = code.replace("RAW_HEAD_SCALE = 1.34", "RAW_HEAD_SCALE = 1.04")
        code = code.replace("RAW_HEAD_NECK_PIVOT = (0.0, 0.032, -0.095)", "RAW_HEAD_NECK_PIVOT = (0.0, 0.020, -0.135)")

    out_path = TOOLS_ROOT / entry["studio_script"]
    out_path.write_text(code, encoding="utf-8")
    print(f"[OK] Generirana Elf Rig Studio skripta: {out_path}")
    return out_path


MOODBOARD_BOARD_JSON = Path(
    "/Users/timonterzic/Documents/Studio Varazdin/varazdin.studio/website/moodboard/data/boards/advent_vilenjaci.json"
)


def parse_moodboard_card_text(raw_text: str, default_gen: bool = True) -> Dict[str, Any]:
    """Parsira tekst iz moodboard kartice txt_seg_<ID> u strukturirane podatke (generate, status, rigger, segmenti, komentar)."""
    import re

    gen_m = re.search(r"\[GEN:(DA|NE)\]", raw_text, re.IGNORECASE)
    st_m = re.search(r"\[STATUS:([^\]]+)\]", raw_text)
    rig_m = re.search(r"\[RIGGER:([^\]]*)\]", raw_text)
    seg_m = re.search(
        r"SEGMENTI(?:\s+ZA\s+RASTAVLJANJE(?:\s*\([^)]*\))?)?:\s*([\s\S]*?)(?:\n+KOMENTAR(?:\s*/\s*TKO\s+RIGA)?:|$)",
        raw_text,
        re.IGNORECASE,
    )
    com_m = re.search(r"KOMENTAR(?:\s*/\s*TKO\s+RIGA)?:\s*([\s\S]*)$", raw_text, re.IGNORECASE)

    generate_now = (gen_m.group(1).upper() == "DA") if gen_m else default_gen
    status = st_m.group(1).strip() if st_m else ("done" if "[GOTOV PILOT]" in raw_text else "awaiting_segments")
    segments_str = seg_m.group(1).strip() if seg_m else raw_text.strip()
    segments_list = [s.strip() for s in re.split(r"[,;\n]+", segments_str) if s.strip()]
    return {
        "generate": generate_now,
        "status": status,
        "rigger": rig_m.group(1).strip() if rig_m else "",
        "segments_raw": segments_str,
        "segments": segments_list,
        "comment": com_m.group(1).strip() if com_m else "",
    }


def print_moodboard_segments(only_ready: bool = False, only_active: bool = False, elf_num: int = None) -> None:
    """Čita aktivne segmente i bilješke iz varazdin.studio moodboarda (advent_vilenjaci.json)."""
    if not MOODBOARD_BOARD_JSON.exists():
        print(f"[WARN] Moodboard JSON nije pronađen: {MOODBOARD_BOARD_JSON}")
        return

    data = json.loads(MOODBOARD_BOARD_JSON.read_text(encoding="utf-8"))
    items_by_id = {item.get("id"): item for item in data.get("items", []) if isinstance(item, dict)}

    print("=" * 134)
    print("VARAZDIN.STUDIO MOODBOARD — KORISNIČKI SEGMENTI I ZADACI ZA VILENJAKE (advent_vilenjaci.json)")
    print("=" * 134)
    print(f"{'#':<3} | {'GEN SADA':<11} | {'STATUS':<18} | {'RIGGER':<14} | {'ID LIKA':<36} | {'SEGMENTI ZA RASTAVLJANJE'}")
    print("-" * 134)

    for entry in sorted(ELF_PRODUCTION_ROSTER, key=lambda x: x["num"]):
        if elf_num is not None and entry["num"] != elf_num:
            continue
        card_id = f"txt_seg_{entry['id']}"
        card = items_by_id.get(card_id)
        def_gen = entry["wave"] in (0, 1)
        parsed = parse_moodboard_card_text(card.get("text", ""), default_gen=def_gen) if card else {
            "generate": def_gen,
            "status": "awaiting_segments",
            "rigger": "",
            "segments_raw": ", ".join(entry["parts"]),
            "segments": entry["parts"],
            "comment": "",
        }
        if only_active and not parsed["generate"]:
            continue
        if only_ready and parsed["status"] != "ready_to_split":
            continue
        gen_disp = "DA (AKTIV)" if parsed["generate"] else "NE (SKIP)"
        rigger_disp = parsed["rigger"] or "-"
        print(
            f"{entry['num']:02d}  | {gen_disp:<11} | {parsed['status']:<18} | {rigger_disp:<14} | {entry['id']:<36} | {parsed['segments_raw']}"
        )
        if parsed["comment"]:
            print(f"    └── KOMENTAR: {parsed['comment']}")
    print("=" * 134)


def main():
    parser = argparse.ArgumentParser(description="Universal Elf Studio Factory & Production Manager")
    parser.add_argument("--status", action="store_true", help="Prikaži tablicu stanja svih 34 vilenjaka")
    parser.add_argument("--read-moodboard", action="store_true", help="Pročitaj segmente i komentare ljudi iz varazdin.studio moodboarda")
    parser.add_argument("--only-active", action="store_true", help="Uz --read-moodboard prikaži samo vilenjake uključene za generiranje u ovoj fazi (GEN:DA)")
    parser.add_argument("--only-ready", action="store_true", help="Uz --read-moodboard prikaži samo vilenjake sa statusom ready_to_split")
    parser.add_argument("--elf", type=int, help="Filtriraj ispis na određeni broj vilenjaka (1-34)")
    parser.add_argument("--print-wave", type=int, choices=[0, 1, 2, 3, 4], help="Ispiši vilenjake u odabranom valu")
    parser.add_argument("--generate-studio", type=int, help="Generiraj tools/elf<XX>_sculpt_rig_studio.py za broj vilenjaka")
    parser.add_argument("--slice-sheet", type=str, help="Putanja do 3-view PNG lista za izrezivanje u 4x 1536x1536")
    parser.add_argument("--prefix", type=str, default="part", help="Prefiks za izrezane poglede")
    parser.add_argument("--out-dir", type=str, help="Izlazna mapa za izrezane poglede")
    args = parser.parse_args()

    if args.read_moodboard:
        print_moodboard_segments(only_ready=args.only_ready, only_active=args.only_active, elf_num=args.elf)
    elif args.status:
        print_status_table()
    elif args.print_wave is not None:
        wave_elves = [e for e in ELF_PRODUCTION_ROSTER if e["wave"] == args.print_wave]
        print(f"=== VAL {args.print_wave} ({len(wave_elves)} vilenjaka) ===")
        for e in wave_elves:
            print(f"  - #{e['num']:02d} [{e['id']}] -> {e['hr_name']} ({', '.join(e['parts'])})")
    elif args.generate_studio is not None:
        generate_studio_script_for_elf(args.generate_studio)
    elif args.slice_sheet:
        if not args.out_dir:
            raise ValueError("--out-dir je obavezan uz --slice-sheet")
        saved = slice_3view_sheet(Path(args.slice_sheet), args.prefix, Path(args.out_dir))
        for p in saved:
            print(f"Saved: {p}")
    else:
        print_status_table()


if __name__ == "__main__":
    main()
