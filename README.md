# Utsendelsessystem for Tidsskrift og Giroer

Dette systemet automatiserer hele prosessen fra Cornerstone CRM-eksporter til ferdig flettede, trykkeklare PDF-dokumenter for postutsendelse av tidsskriftet, samt arkivering på organisasjonens server.

Systemet håndterer automatisk sammenslåing av medlems- og bidragsdata (Polars), generering av skreddersydd Mikaelkirken-QR-kode (SVG), massefletting mot en LibreOffice-mal kalibrert for **F60-1-giroblanketter** og **C5-vinduskonvolutter**, og til slutt strukturert overføring til serverarkiv (`base_folder`).

---

## 🚀 Rask oppstart (Hvordan bruke systemet)

### 1. Forberedelse i Cornerstone CRM

Gjør dine vanlige forberedelser i Cornerstone og eksporter de to vanlige Excel-filene:

1. Adresselisten (f.eks. `Export+....xlsx`)
2. Bidrags-/KID-listen for tidsskriftet (f.eks. `Tidsskriftet+-+....xlsx`)

*Filene lagres som normalt i din nedlastingskatalog (f.eks. `~/syncthing/Downloads`). Du trenger ikke å flytte eller gi dem nye navn manuelt.*

---

### 2. Viktig før kjøring

Lukk LibreOffice på maskinen din før du starter massefletting. Hvis LibreOffice kjører på skrivebordet, vil Linux nekte headless-motoren å konvertere store PDF-filer.
*(Skulle en prosess henge, kan den enkelt avsluttes med `killall -9 soffice.bin`).*

---

### 3. Kjør skriptet

Gå til prosjektmappen og kjør med **`uv`**:

```bash
cd lag-tidskrift-giroer

# Kjør for en spesifikk utgave (ÅR-NUMMER):
uv run python src/lag_tidskrift_giroer/main.py 2026-3
```

*(Hvis du glemmer å oppgi perioden bak, spør skriptet deg pent i terminalen).*

#### 🧪 Tips for rask testkjøring

Vil du bare generere 3 prøvesider for å sjekke utskriften på blanketten, legger du på `--limit`:

```bash
uv run python src/lag_tidskrift_giroer/main.py 2026-3 --limit 3
```

---

### 4. Resultat

Når terminalen melder `PROSESSEN ER FULLFØRT!`:

1. **Lokalt i `output/`:**
   * 📄 **`output/2026-3.pdf`** – Den komplette utskriftsfilen med alle giroene klar for trykk.
   * 📝 **`output/2026-3.odt`** – Flettet LibreOffice-dokument.
   * 📊 **`output/2026-3.xlsx`** – Flettegrunnlaget med utgavekoder og vaskede adressedata.

2. **På serveren (`base_folder/`):**
   Mappen `2026-3 Tidskriftet/` er automatisk opprettet eller oppdatert med produksjonsfiler og fraktbrev:

   ```text
   /mnt/server/system-ssd/mount/Mikaelkirken/Kommunikasjon/Tidsskriftet/
   └── 2026-3 Tidskriftet/
       ├── qr-code.svg
       ├── giro.odt
       ├── 2026-3.xlsx
       └── til utsending/
           ├── giroer.pdf
           └── fraktbrev.pdf
   ```

---

## ⚙️ Hva systemet gjør (Arbeidsflyten steg for steg)

```text
Cornerstone Eksport (Downloads)
       │
       ▼
[Steg 1: Filkopiering] ───────► Kopi til data/<periode>/ (adresser.xlsx og kid.xlsx)
       │
       ▼
[Steg 2: Polars Vask/Join] ───► Standardiserer postnr (zfill 4) og ID-er.
       │                        Genererer Utgavekode (f.eks. '2026-3' ➔ '263').
       ▼
[Steg 3: Excel-arkivering] ───► Lagrer flettegrunnlag: output/<periode>.xlsx
       │
       ▼
[Steg 4: QR-kodegenerering] ──► Genererer https://bidrag.mikaelkirken.no/263
       │                        Overskriver assets/qr-code.svg
       ▼
[Steg 5: Headless Fletting] ──► merge_odt fletter mot maler/giro.odt (combine=True)
       │                        Konverterer til ferdig PDF: output/<periode>.pdf
       ▼
[Steg 6: Serverarkivering] ───► Oppretter '<periode> Tidskriftet/' i base_folder.
                                Kopierer qr-code, mal, excel og fraktbrev.
```

---

## 📐 Maloppsett og Layout (`maler/giro.odt`)

Malen er bygd for å treffe **C5-vinduskonvolutter** (16,1 × 23 cm) og standard **F60-1-lasergiroer** (nederste 105 mm av arket).

### Viktig regel for malen

All tekst og alle flettefelter må ligge i **brødteksten**, aldri i topp- eller bunntekst! For å oppnå millimeterpresisjon uten at feltene forskyver seg, brukes **tekstrammer** (*Frames*):

* **Forankring (Anchor):** Må alltid være satt til **`To paragraph`** *(slik at rammen blir med over på hver nye side i flettingen)*.
* **Posisjon:** Måles fra **`Entire page`** med usynlig kant (**`Borders: None`**).

### Mål-tabell for rammene

| Formål | Forankring | Bredde | Høyde | Horisontalt (fra venstre) | Vertikalt (fra toppen) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Vinduskonvolutt** | To paragraph | `80 mm` | `35 mm` | `18 mm` | `40 mm` |
| **KID på F60-1 giro** | To paragraph | `65 mm` | `10 mm` | `108 mm` | `238 mm` |
| **QR-kode bilde** | To paragraph | *(koblet)* | *(koblet)* | Justeres etter behov | Justeres etter behov |

### Tilgjengelige flettetagger

Taggene skrives som ren tekst rett fra tastaturet med **én enkel krøllparentes og uten mellomrom**:

* `{Husholdningsnavn}`
* `{Fornavn}`
* `{Etternavn}`
* `{Adresse}`
* `{Postnummer}`
* `{Poststed}`
* `{KID}`
* `bidrag.mikaelkirken.no/{Utgavekode}`

### QR-koden i malen

QR-koden er satt inn som en **kobling** (*Link*) til `../assets/qr-code.svg`. LibreOffice leser inn den ferske bildefilen fra disken for hvert nummer automatisk.

---

## 🛠️ Konfigurasjon (`config.json`)

Stier og søkemønstre styres fra `config.json` i rotkatalogen:

```json
{
  "base_folder": "/mnt/server/system-ssd/mount/Mikaelkirken/Kommunikasjon/Tidsskriftet",
  "download_folder": "~/syncthing/Downloads",
  "fil_spesifikasjoner": [
    {
      "hint": "Export+*.xlsx",
      "file": "adresser.xlsx"
    },
    {
      "hint": "Tidsskriftet*.xlsx",
      "file": "kid.xlsx"
    }
  ]
}
```

---

## 💡 Feilsøking

* **Feilmelding: `RuntimeError: Konvertering feilet:`**  
  *Årsak:* LibreOffice kjører i bakgrunnen på maskinen og blokkerer headless-konverteringen.  
  *Løsning:* Lukk LibreOffice, eller kjør `killall -9 soffice.bin` i terminalen, og kjør skriptet på nytt.

* **Noen bokser mangler på side 2, 3 og utover:**  
  *Løsning:* Høyreklikk på boksen i Writer ➔ `Anchor` ➔ velg `To paragraph`.
