import argparse
import json
from pathlib import Path
import re
import shutil
import sys
import warnings
import polars as pl
from utilities import (
    generate_qrcode_mikaelkirken,
    get_newest_file,
    merge_odt,
)

warnings.filterwarnings("ignore", category=FutureWarning)

# --- Faste stier ---
PROSJEKT_ROT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = PROSJEKT_ROT / "config.json"
DATA_DIR = PROSJEKT_ROT / "data"
OUTPUT_DIR = PROSJEKT_ROT / "output"
ASSETS_DIR = PROSJEKT_ROT / "assets"
MAL_PATH = PROSJEKT_ROT / "maler" / "giro.odt"
QR_KODE_STI = ASSETS_DIR / "qr-code.svg"


def last_konfigurasjon() -> dict:
    if not CONFIG_PATH.exists():
        print(f"\nFeil: Fant ikke konfigurasjonsfilen: {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def valider_og_hent_periode() -> tuple[str, int | None]:
    parser = argparse.ArgumentParser(
        description="Klargjør filer og flett tidsskrift-giroer."
    )
    parser.add_argument(
        "periode",
        nargs="?",
        help="År og utgavenummer i formatet YYYY-N (f.eks. 2026-3)",
    )
    parser.add_argument(
        "-l",
        "--limit",
        type=int,
        help="Begrens antall rader som flettes (kjekt for rask testkjøring)",
    )
    args = parser.parse_args()

    periode = args.periode
    if not periode:
        periode = input("Oppgi år og utgave (format YYYY-N, f.eks. 2026-3): ")

    periode = periode.strip()

    if not re.match(r"^\d{4}-[1-4]$", periode):
        print(
            f"\nFeil: Ugyldig format '{periode}'. Må være på formen YYYY-N (f.eks. 2026-3)."
        )
        sys.exit(1)

    return periode, args.limit


# ==========================================
# STEG 1: Hente og KOPIERE filer til data/
# ==========================================
def steg_1_hent_og_kopier_filer(
    periode_dir: Path, downloads_dir: Path, spesifikasjoner: list[dict]
):
    print(f"\n[Steg 1] Leter etter nyeste filer i: {downloads_dir}")

    for spec in spesifikasjoner:
        monster = spec["hint"]
        maal_navn = spec["file"]
        maal_sti = periode_dir / maal_navn

        funnet_fil = get_newest_file(downloads_dir, monster)

        if not funnet_fil:
            print(f"\nFeil: Fant ingen fil i {downloads_dir} som matcher '{monster}'")
            sys.exit(1)

        print(f"  -> Fant: {funnet_fil.name}")
        shutil.copy2(funnet_fil, maal_sti)
        print(f"     Kopiert til: {maal_sti}")

    print(f" Filene er lagret i data-katalogen: '{periode_dir.name}'")


# ==========================================
# STEG 2: Sammenstille data med Polars
# ==========================================
def steg_2_behandle_og_joine_data(
    periode_dir: Path, periode: str
) -> tuple[pl.DataFrame, str]:
    adresser_fil = periode_dir / "adresser.xlsx"
    kid_fil = periode_dir / "kid.xlsx"

    print("\n[Steg 2] Leser inn og joiner data med Polars...")

    df_adresser = pl.read_excel(adresser_fil)
    df_kid = pl.read_excel(kid_fil)

    df_adresser = df_adresser.with_columns(
        [
            pl.col("Cornerstone-ID").cast(pl.String).str.strip_chars(),
            pl.col("Postnummer").cast(pl.String).str.zfill(4),
        ]
    )

    df_kid = df_kid.with_columns(
        [
            pl.col("Cornerstone ID")
            .cast(pl.String)
            .str.strip_chars()
            .alias("Cornerstone-ID"),
            pl.col("KID").cast(pl.String).str.strip_chars(),
        ]
    )

    utgavekode = periode[-4:].replace("-", "")
    print(f"  Generert utgavekode: '{utgavekode}'")

    slutt_df = (
        df_adresser.join(
            df_kid.select(["Cornerstone-ID", "KID"]),
            on="Cornerstone-ID",
            how="inner",
        )
        .with_columns([pl.lit(utgavekode).alias("Utgavekode")])
        .select(
            [
                "Husholdningsnavn",
                "Adresse",
                "Postnummer",
                "Poststed",
                "Fornavn",
                "Etternavn",
                "Cornerstone-ID",
                "KID",
                "Utgavekode",
            ]
        )
    )

    print(f" Kobling fullført! Antall gyldige rader: {len(slutt_df)}")
    return slutt_df, utgavekode


# ==========================================
# STEG 3: Lagre flettegrunnlag i output/
# ==========================================
def steg_3_lagre_flettegrunnlag(
    df: pl.DataFrame, output_dir: Path, periode: str
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    maal_fil = output_dir / f"{periode}.xlsx"

    print(f"\n[Steg 3] Lagrer flettegrunnlag til Excel: {maal_fil}")
    df.write_excel(maal_fil)
    print(f" Fil lagret: {maal_fil.name}")
    return maal_fil


# ==========================================
# STEG 4: Generere Mikaelkirken QR-kode
# ==========================================
def steg_4_generer_qr_kode(utgavekode: str, maal_sti: Path) -> Path:
    url = f"https://bidrag.mikaelkirken.no/{utgavekode}"
    print(f"\n[Steg 4] Genererer Mikaelkirken QR-kode for: {url}")

    maal_sti.parent.mkdir(parents=True, exist_ok=True)
    generate_qrcode_mikaelkirken(url=url, output_file=str(maal_sti))

    print(f" QR-kode lagret: {maal_sti}")
    return maal_sti


# ==========================================
# STEG 5: Headless fletting og omdøping
# ==========================================
def steg_5_flett_dokumenter(
    mal_sti: Path,
    excel_fil: Path,
    output_dir: Path,
    periode: str,
    limit: int | None = None,
) -> list[Path]:
    print(f"\n[Steg 5] Starter fletting med merge_odt...")

    if not mal_sti.exists():
        print(f"Feil: Finner ikke mal-filen: {mal_sti}")
        sys.exit(1)

    genererte_filer = merge_odt(
        template_path=mal_sti,
        excel_path=excel_fil,
        output_dir=output_dir,
        output_format="both",
        combine=True,
        limit=limit,
    )

    ferdig_filer = []
    for fil in genererte_filer:
        nytt_navn = output_dir / f"{periode}{fil.suffix}"
        if nytt_navn.exists():
            nytt_navn.unlink()
        fil.rename(nytt_navn)
        ferdig_filer.append(nytt_navn)

    print(f" Fletting fullført! Filene har fått riktig navn:")
    for f in ferdig_filer:
        print(f"  -> {f.name}")

    return ferdig_filer


# ==========================================
# STEG 6: Arkivering til base_folder
# ==========================================
def steg_6_kopier_til_base_folder(periode: str, config: dict):
    base_folder_sti = config.get("base_folder")
    if not base_folder_sti:
        print("\n[Steg 6] Ingen 'base_folder' funnet i config.json, hopper over.")
        return

    base_folder = Path(base_folder_sti).expanduser()
    if not base_folder.exists():
        base_folder.mkdir(parents=True, exist_ok=True)

    # Mappestruktur i base_folder
    utgave_mappe = base_folder / f"{periode} Tidskriftet"
    utsending_mappe = utgave_mappe / "til utsending"

    # Opprett mapper uten å overskrive selve mappene
    utgave_mappe.mkdir(parents=True, exist_ok=True)
    utsending_mappe.mkdir(parents=True, exist_ok=True)

    print(f"\n[Steg 6] Kopierer til base_folder:\n  {utgave_mappe}")

    # 1. Filer i rot av utgavemappen (overskriver filene hvis de finnes)
    hovedfiler = [
        (QR_KODE_STI, "qr-code.svg"),
        (MAL_PATH, "giro.odt"),
        (OUTPUT_DIR / f"{periode}.xlsx", f"{periode}.xlsx"),
    ]

    for kilde, maal_filnavn in hovedfiler:
        if kilde.exists():
            shutil.copy2(kilde, utgave_mappe / maal_filnavn)
            print(f"  -> Kopierte {maal_filnavn}")
        else:
            print(f"  Advarsel: Kildefil mangler: {kilde}")

    # 2. Fraktbrev inn i 'til utsending/'
    # Sjekker både 'fraktbrev.pdf' og ev. 'fraktberv.pdf'
    fraktbrev_kilde = ASSETS_DIR / "fraktbrev.pdf"
    if not fraktbrev_kilde.exists() and (ASSETS_DIR / "fraktberv.pdf").exists():
        fraktbrev_kilde = ASSETS_DIR / "fraktberv.pdf"

    if fraktbrev_kilde.exists():
        shutil.copy2(fraktbrev_kilde, utsending_mappe / "fraktbrev.pdf")
        print(f"  -> Kopierte fraktbrev.pdf til 'til utsending/'")
    else:
        print(f"  Advarsel: Fant ikke fraktbrev i assets/ ({fraktbrev_kilde.name})")

    print(f" Arkivering til base_folder fullført!")


# ==========================================
# HOVEDPROGRAM
# ==========================================
def main():
    config = last_konfigurasjon()
    periode, limit = valider_og_hent_periode()

    data_periode_dir = DATA_DIR / periode
    data_periode_dir.mkdir(parents=True, exist_ok=True)

    downloads_dir = Path(config["download_folder"]).expanduser()
    fil_spesifikasjoner = config.get("fil_spesifikasjoner", [])

    # Steg 1: Kopiere rådata
    steg_1_hent_og_kopier_filer(data_periode_dir, downloads_dir, fil_spesifikasjoner)

    # Steg 2: Polars vask & join
    flette_df, utgavekode = steg_2_behandle_og_joine_data(data_periode_dir, periode)

    # Steg 3: Lagre Excel-flettegrunnlag
    excel_flettefil = steg_3_lagre_flettegrunnlag(flette_df, OUTPUT_DIR, periode)

    # Steg 4: Generer QR-kode
    steg_4_generer_qr_kode(utgavekode, QR_KODE_STI)

    # Steg 5: Flett til ferdig PDF
    if limit:
        print(f"\nBegrenser fletting til de første {limit} radene for test.")
    steg_5_flett_dokumenter(
        MAL_PATH, excel_flettefil, OUTPUT_DIR, periode=periode, limit=limit
    )

    # Steg 6: Overfør ferdig struktur til base_folder
    if not limit:
        steg_6_kopier_til_base_folder(periode, config)

    print("\n" + "=" * 60)
    print("PROSESSEN ER FULLFØRT!")
    print(f"Filer produsert i : {OUTPUT_DIR}")
    if not limit:
        print(f"Arkivert på server: {config.get('base_folder')}")
    print("=" * 60)


if __name__ == "__main__":
    main()
