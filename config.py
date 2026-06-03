"""
Central configuration.
To switch countries, change ACTIVE_COUNTRY below (e.g. "NOR").
To change the climate period, edit year_start / year_end inside each country block.
"""

AUTHOR     = "Muhammad Hassaan Farooq Butt"
SOURCE_CRS = "EPSG:4326"
NODATA     = -9999.0
N_CLASSES  = 3
MAX_DEM_PX = 2000

# ── Available data sources ────────────────────────────────────────────────────
# The script auto-selects the right source based on the country's year range.
DATA_SOURCES = {
    "CHELSA_V2.1": {
        "year_start": 1981,
        "year_end":   2010,
        "note": "Only the 1981-2010 climatology is published on the CHELSA CDN.",
    },
    "TerraClimate": {
        "year_start": 1958,
        "year_end":   2024,
        "note": "Monthly global climate data at ~4 km. Covers 1958-2024.",
    },
}

# ── Country settings ──────────────────────────────────────────────────────────
COUNTRIES = {
    "PAK": {
        "name":       "Pakistan",
        "gadm_file":  "data/gadm41_PAK_0.json",
        "gadm_url":   "https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_PAK_0.json",
        "crs":        "EPSG:32642",   # WGS 84 / UTM Zone 42N
        "dem_file":   "data/pak_dem.tif",
        "buffer":     0.5,
        # ── Year range: change these two lines to select any period 1958-2024 ──
        "year_start": 1981,
        "year_end":   2010,
    },
    "NOR": {
        "name":       "Norway",
        "gadm_file":  "data/gadm41_NOR_0.json",
        "gadm_url":   "https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_NOR_0.json",
        "crs":        "EPSG:25833",   # ETRS89 / UTM Zone 33N
        "dem_file":   "data/nor_dem.tif",
        "buffer":     0.5,
        # ── Year range ─────────────────────────────────────────────────────────
        "year_start": 2000,
        "year_end":   2024,
    },
}

# ── Change this line to switch country ──────────────────────────
ACTIVE_COUNTRY = "NOR"
# ────────────────────────────────────────────────────────────────

# Province / state level-1 boundaries and label config
ADMIN1 = {
    "PAK": {
        "file": "data/gadm41_PAK_1.json",
        "url":  "https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_PAK_1.json",
        "col":  "NAME_1",
        # Keys must match the exact NAME_1 strings in GADM 4.1
        "shorts": {
            "Khyber-Pakhtunkhwa":              "KPK",
            "FederallyAdministeredTribalAr":   "Tribal\nRegion",  # FATA, merged into KPK 2018
            "Gilgit-Baltistan":                "Gilgit\nBaltistan",
            "AzadKashmir":                     "AJK",
            "Islamabad":                       "ISB",
            # Sindh, Balochistan, Punjab — full names are fine, no short needed
        },
    },
    "NOR": {
        "file": "data/gadm41_NOR_1.json",
        "url":  "https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_NOR_1.json",
        "col":  "NAME_1",
        "shorts": {},
    },
}

# Major cities (longitude, latitude) in WGS84
CITIES = {
    "PAK": {
        "Karachi":    (67.010, 24.861),
        "Lahore":     (74.344, 31.550),
        "Islamabad":  (73.048, 33.684),
        "Peshawar":   (71.525, 34.015),
        "Quetta":     (66.975, 30.180),
        "Multan":     (71.525, 30.158),
        "Faisalabad": (73.135, 31.450),
    },
    "NOR": {
        "Oslo":        (10.752, 59.914),
        "Bergen":      (5.322,  60.391),
        "Trondheim":   (10.395, 63.431),
        "Stavanger":   (5.733,  58.970),
        "Tromso":      (18.956, 69.649),
        "Drammen":     (10.205, 59.744),
        "Fredrikstad": (10.939, 59.219),
        "Kristiansand": (7.996, 58.146),
        "Alesund":     (6.149,  62.472),
        "Bodo":        (14.405, 67.280),
        "Hamar":       (11.068, 60.795),
        "Alta":        (23.271, 69.968),
    },
}

PALETTES = {
    # Classic bivariate palette — professional/LinkedIn version
    "DkBlue": {
        "1-1": "#e8e8e8", "2-1": "#b0d5df", "3-1": "#64acbe",
        "1-2": "#e4acac", "2-2": "#ad9ea5", "3-2": "#627f8c",
        "1-3": "#c85a5a", "2-3": "#985356", "3-3": "#574249",
    },
    # Intuitive palette — public/Facebook version
    # Orange = hot, Blue = cool, Green = wet, Sandy = dry
    "Vivid": {
        "1-1": "#f5deb3",  # cool + dry  → wheat/steppe
        "2-1": "#f0a030",  # mild + dry  → amber
        "3-1": "#d05010",  # hot  + dry  → burnt orange / desert
        "1-2": "#90c8e0",  # cool + mid  → sky blue
        "2-2": "#68a878",  # mild + mid  → sage green
        "3-2": "#c07818",  # hot  + mid  → dark amber
        "1-3": "#3878c0",  # cool + wet  → deep blue / glacial
        "2-3": "#28884c",  # mild + wet  → forest green
        "3-3": "#104a28",  # hot  + wet  → dark green / tropical
    },
}

PALETTE_PROFESSIONAL = "DkBlue"
PALETTE_PUBLIC       = "Vivid"

CLIMATE_MESSAGES = {
    "professional": (
        "Climatology shows measurable shifts in temperature & precipitation — "
        "a clear signal of accelerating climate change.\n"
        "Data: TerraClimate / CHELSA V2.1  |  GADM 4.1  |  SRTM  |  Fisher natural-break classes"
    ),
    "public": (
        "Our climate IS changing — temperatures are rising and rains are shifting year by year.\n"
        "What YOU can do right now:"
        "   Plant trees      Save water      Say no to plastic      Tell your friends!"
    ),
}
