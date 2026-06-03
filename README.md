# BioClimate 3D Atlas

Visualise temperature and precipitation together on a single map using bivariate colour mapping, with reproducible 2D exports and an optional 3D terrain view.
Built for Norway and Pakistan, but easily extended to any country.

> **Author:** Muhammad Hassaan Farooq Butt

---

## What it produces

Three images are generated per run:

| File | Description |
|---|---|
| `outputs/nor_professional.png` | Subtle bivariate palette with city labels |
| `outputs/nor_public.png` | Vivid bivariate palette with city labels |
| `outputs/nor_3d.png` | 3D terrain coloured by climate zones |

The 2D maps export at `1080 x 1350` pixels by default. This can be changed in `utils/render.py`.

---

## How to read the map

Each pixel shows **two climate facts at once**:

```
         ← COOLER ────────────── HOTTER →
  ↑      ┌──────────┬──────────┬──────────┐
  │      │ Cool&Dry │ Mid &Dry │ Hot&Dry  │
MORE     ├──────────┼──────────┼──────────┤
RAIN     │ Cool&Mid │  Middle  │ Hot&Mid  │
  │      ├──────────┼──────────┼──────────┤
  ↓      │ Cool&Wet │ Mid &Wet │ Hot&Wet  │
         └──────────┴──────────┴──────────┘
```

The **professional** map uses the classic *DkBlue* bivariate palette.  
The **public** map uses the *Vivid* palette: orange = hot/dry, blue = cool/wet, green = hot/wet.

---

## Data sources

| Layer | Source | Resolution | Coverage |
|---|---|---|---|
| Temperature & Precipitation | [CHELSA V2.1](https://chelsa-climate.org/) | ~1 km | 1981–2010 |
| Temperature & Precipitation | [TerraClimate](https://www.climatologylab.org/terraclimate.html) | ~4 km | 1958–2024 |
| Country / Province boundaries | [GADM 4.1](https://gadm.org/) | — | Global |
| Elevation (3D) | [SRTM-3 / CGIAR-CSI](https://srtm.csi.cgiar.org/) | ~90 m | Global |

The script **automatically picks the right source** based on your year range:

- `1981–2010` → CHELSA V2.1 (cached, fast)
- Any other range inside `1958–2024` → TerraClimate (downloads year-by-year)

---

## Setup

```bash
git clone https://github.com/mhassaanbutt/bioclimate-3d-atlas.git
cd bioclimate-3d-atlas

pip install -r requirements.txt
```

**Requirements:** Python 3.9+, see `requirements.txt`.

---

## Usage

```bash
# Norway (default)
python main.py

# Any supported country
python main.py --country NOR
python main.py --country PAK
```

All downloaded data is cached in `data/` so subsequent runs are fast.
Outputs land in `outputs/`.

---

## Configuration

Open `config.py` — all settings are in one place.

### Switch country

```python
ACTIVE_COUNTRY = "NOR"   # change to "PAK" for Pakistan
```

Or pass a country on the command line: `python main.py --country PAK`

### Change the year range

Edit the `year_start` / `year_end` inside the country block:

```python
"PAK": {
    ...
    "year_start": 2000,   # any year 1958-2024
    "year_end":   2024,
},
```

The script validates the range and tells you clearly if it falls outside any available source:

```
No data source covers 2025–2030.

Available sources:
  CHELSA V2.1    : 1981–2010
  TerraClimate   : 1958–2024

Fix: set year_start / year_end inside COUNTRIES[...] in config.py
```

### Add a new country

```python
COUNTRIES["IND"] = {
    "name":       "India",
    "gadm_file":  "data/gadm41_IND_0.json",
    "gadm_url":   "https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_IND_0.json",
    "crs":        "EPSG:32644",   # UTM Zone 44N
    "dem_file":   "data/ind_dem.tif",
    "buffer":     0.5,
    "year_start": 2000,
    "year_end":   2024,
}
ADMIN1["IND"] = {
    "file": "data/gadm41_IND_1.json",
    "url":  "https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_IND_1.json",
    "col":  "NAME_1",
    "shorts": {},
}
```

All boundaries and climate data download automatically on the first run.

---

## Project structure

```
bioclimate-3d-atlas/
├── main.py           # Entry point — orchestrates everything
├── config.py         # All settings: countries, year ranges, palettes, cities
├── utils/
│   ├── data.py       # Download + cache: CHELSA, TerraClimate, SRTM, GADM
│   ├── classify.py   # Fisher natural-break bivariate classification
│   └── render.py     # 2D palette variants and 3D terrain rendering
├── data/             # Downloaded data files (git-ignored, auto-created)
├── outputs/          # Generated maps (git-ignored, auto-created)
├── requirements.txt
└── .gitignore
```

---

## City labels

City labels are configured in `config.py` under `CITIES`. Norway currently includes Oslo, Bergen, Trondheim, Stavanger, Tromso, Drammen, Fredrikstad, Kristiansand, Alesund, Bodo, Hamar, and Alta.

## Pakistan provinces

| Label on map | Full name |
|---|---|
| Punjab | Punjab |
| Sindh | Sindh |
| Balochistan | Balochistan |
| KPK | Khyber-Pakhtunkhwa |
| Gilgit Baltistan | Gilgit-Baltistan |
| AJK | Azad Jammu & Kashmir |
| ISB | Islamabad Capital Territory |
| Tribal Region | Former FATA — merged into KPK in 2018 |

---

## Why does this matter?

Bivariate climate maps make temperature and precipitation visible together, so dry-hot, cool-wet, and mixed climate zones can be read at a glance.
For Norway, the 2000–2024 TerraClimate view highlights strong coastal-to-inland contrasts, mountain effects, and regional precipitation gradients.
For Pakistan, the 1981–2010 CHELSA view highlights sharp contrasts between the Indus plain, the arid belt of Balochistan, and the northern mountains.

## Contributing

Contributions are welcome. Useful areas include:

- Add more countries and projected CRS settings
- Improve city lists and label placement rules
- Add alternative bivariate palettes
- Improve classification methods and validation
- Add tests for data loading, reprojection, and rendering helpers
- Improve documentation for new datasets and workflows

Please keep generated data and output images out of version control unless they are small examples intended for documentation.

---

## License

MIT — free to use, share, and adapt with attribution.

© Muhammad Hassaan Farooq Butt
