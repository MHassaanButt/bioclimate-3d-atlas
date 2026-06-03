"""
render.py — single, beautiful bivariate climate map.

Design rules:
  • White background — clean, like original R/biscale output
  • Figure sized to the data aspect ratio → zero wasted space
  • Hillshade from the SRTM DEM adds terrain depth
  • City labels highlight recognizable places for social posts
  • Legend lives bottom-right above the centered author credit
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.patheffects as pe
from matplotlib.ticker import NullLocator
from scipy.ndimage import gaussian_filter

BG = "#ffffff"
LINKEDIN_DPI = 200
LINKEDIN_FIG_W = 5.4   # 1080 px at 200 dpi
LINKEDIN_FIG_H = 6.75  # 1350 px at 200 dpi

# Minimum province area as a fraction of the country total
MIN_AREA_FRAC = 0.04

# Bottom strip that holds the author credit and data sources (inches)
AUTHOR_H = 0.68
TITLE_H = 0.72


# ── Hillshade ─────────────────────────────────────────────────────────────────

def _hillshade(dem: np.ndarray,
               azimuth: float = 315.0,
               altitude: float = 45.0,
               z_factor: float = 2.5) -> np.ndarray:
    dem_s  = gaussian_filter(dem.astype(float), sigma=2.0)
    dy, dx = np.gradient(dem_s * z_factor)
    az     = np.radians(360.0 - azimuth + 90.0)
    alt    = np.radians(altitude)
    slope  = np.arctan(np.sqrt(dx**2 + dy**2))
    aspect = np.arctan2(-dy, dx)
    hs = (np.cos(alt) * np.cos(slope) +
          np.sin(alt) * np.sin(slope) * np.cos(az - aspect))
    return np.clip(hs, 0.0, 1.0)


def _blend_hillshade(rgba: np.ndarray, hs: np.ndarray,
                     shadow: float = 0.55) -> np.ndarray:
    """Multiply-blend hillshade: darken shadows while keeping colours vibrant."""
    out  = rgba.copy()
    mask = rgba[..., 3] > 0
    hs3  = hs[..., np.newaxis]
    out[mask, :3] = np.clip(
        rgba[mask, :3] * (1.0 - shadow + shadow * hs3[mask]), 0, 1)
    return out


# ── Province labels ───────────────────────────────────────────────────────────

def _province_labels(ax, admin1_proj, short_names: dict):
    if admin1_proj is None:
        return

    total_area = admin1_proj.geometry.area.sum()
    stroke = [pe.withStroke(linewidth=2.5, foreground="white")]

    for _, row in admin1_proj.iterrows():
        frac = row.geometry.area / total_area
        if frac < MIN_AREA_FRAC:
            continue

        label     = short_names.get(row["NAME_1"], row["NAME_1"])
        pt        = row.geometry.representative_point()
        font_size = 7.5 + 4.5 * (frac ** 0.45)

        ax.annotate(label,
                    xy=(pt.x, pt.y), ha="center", va="center",
                    fontsize=font_size, fontweight="bold",
                    color="#111111",
                    path_effects=stroke,
                    zorder=10, multialignment="center", clip_on=False)


def _city_labels(ax, cities_xy: dict):
    if not cities_xy:
        return

    stroke = [pe.withStroke(linewidth=2.4, foreground="white")]
    leader_col = "#b06a2d"
    label_col = "#1f252b"
    offsets = {
        "Oslo": (34, 10),
        "Drammen": (50, -8),
        "Fredrikstad": (8, -16),
        "Kristiansand": (8, -6),
        "Stavanger": (-6, -8),
        "Bergen": (-9, 6),
        "Alesund": (-9, 7),
        "Trondheim": (8, 8),
        "Tromso": (8, 8),
        "Bodo": (8, 7),
        "Alta": (8, 7),
        "Hamar": (8, 8),
    }

    for name, (x, y) in cities_xy.items():
        dx, dy = offsets.get(name, (7, 7))
        va = "center" if dy == 0 else ("bottom" if dy > 0 else "top")
        ha = "left" if dx >= 0 else "right"

        ax.scatter([x], [y], s=29, marker="o", color="#111111",
                   edgecolor="white", linewidth=1.1, zorder=11)
        ax.annotate(name,
                    xy=(x, y), xytext=(dx, dy), textcoords="offset points",
                    ha=ha, va=va,
                    fontsize=9.7, fontweight="bold",
                    color=label_col,
                    arrowprops=dict(arrowstyle="-", color=leader_col,
                                    lw=1.0, alpha=0.85,
                                    shrinkA=2, shrinkB=3),
                    path_effects=stroke,
                    zorder=12, clip_on=False)


def _padded_bounds(bounds, pad_frac: float = 0.035):
    minx, miny, maxx, maxy = bounds
    dx = maxx - minx
    dy = maxy - miny
    pad = max(dx, dy) * pad_frac
    return minx - (pad * 3.2), miny - pad, maxx + pad, maxy + pad


# ── Legend ───────────────────────────────────────────────────────────────────

def _draw_legend(fig, palette: dict, n_classes: int, fig_w: float, fig_h: float):
    """
    Place the bivariate colour legend in the lower-right figure whitespace,
    above the centered author credit.
    """
    leg_in = min(1.34, fig_w * 0.25)    # legend square size, inches
    pad_r  = 0.28                       # from right figure edge
    pad_b  = 1.18                       # from bottom figure edge
    pad_l  = max(0.45, fig_w - pad_r - leg_in)

    axins = fig.add_axes([
        pad_l  / fig_w,
        pad_b  / fig_h,
        leg_in / fig_w,
        leg_in / fig_h,
    ])
    axins.set_facecolor(BG)

    for key, hex_col in palette.items():
        tc, pc = map(int, key.split("-"))
        axins.add_patch(mpatches.Rectangle(
            [(tc - 1) / n_classes, (pc - 1) / n_classes],
            1 / n_classes, 1 / n_classes,
            color=hex_col, ec="#ffffff", lw=0.7))

    axins.set_xlim(0, 1)
    axins.set_ylim(0, 1)
    for sp in axins.spines.values():
        sp.set_visible(False)
    axins.xaxis.set_minor_locator(NullLocator())
    axins.yaxis.set_minor_locator(NullLocator())
    axins.tick_params(left=False, bottom=False,
                      labelleft=False, labelbottom=False)

    akw = dict(xycoords="axes fraction",
               arrowprops=dict(arrowstyle="-|>", color="#444444", lw=1.4,
                               mutation_scale=10))
    axins.annotate("", xy=(1.05, -0.10), xytext=(0.00, -0.10), **akw)
    axins.annotate("", xy=(-0.10, 1.05), xytext=(-0.10, 0.00), **akw)

    axins.text(0.5, -0.22, "Temperature",
               ha="center", transform=axins.transAxes,
               fontsize=11.0, color="#333333", fontweight="semibold")
    axins.text(-0.20, 0.5, "Precipitation",
               ha="center", va="center", rotation=90,
               transform=axins.transAxes, fontsize=11.0, color="#333333",
               fontweight="semibold")


# ── Main render ───────────────────────────────────────────────────────────────

def make_map(rgba: np.ndarray,
             dem,
             extent: list,
             country_proj,
             admin1_proj,
             short_names: dict,
             cities_xy: dict,
             palette: dict,
             n_classes: int,
             country_name: str,
             period: str,
             author: str,
             output_path: str):

    # Figure sized to the country bounds, not the padded raster extent.
    view_minx, view_miny, view_maxx, view_maxy = _padded_bounds(
        country_proj.total_bounds)
    fig_w = LINKEDIN_FIG_W
    fig_h = LINKEDIN_FIG_H

    bottom_frac = AUTHOR_H / fig_h
    top_frac = TITLE_H / fig_h

    fig = plt.figure(figsize=(fig_w, fig_h), dpi=LINKEDIN_DPI)
    fig.patch.set_facecolor(BG)

    fig.text(0.5, 1.0 - (0.27 / fig_h),
             f"{country_name}'s Climate Fingerprint",
             ha="center", va="center",
             fontsize=15.2, fontweight="bold", color="#222222",
             transform=fig.transFigure)
    fig.text(0.5, 1.0 - (0.54 / fig_h),
             f"({period})",
             ha="center", va="center",
             fontsize=10.8, fontweight="semibold", color="#444444",
             transform=fig.transFigure)

    # Map axes occupies the area between title and footer
    ax = fig.add_axes([0, bottom_frac, 1, 1 - bottom_frac - top_frac])
    ax.set_facecolor(BG)

    # Hillshade + bivariate render
    if dem is not None and dem.shape == rgba.shape[:2]:
        rgba_vis = _blend_hillshade(rgba, _hillshade(dem))
    else:
        rgba_vis = rgba

    ax.imshow(rgba_vis, extent=extent, origin="upper",
              aspect="equal", interpolation="bilinear")

    # Country boundary (dark, prominent)
    country_proj.boundary.plot(ax=ax, color="#222222", linewidth=0.9, zorder=5)

    # Province boundaries (subtle)
    if admin1_proj is not None:
        admin1_proj.boundary.plot(ax=ax, color="#888888", linewidth=0.35,
                                  linestyle="--", zorder=4)

    # Lock axis to tight country bounds after boundary.plot() resets it
    ax.set_xlim(view_minx, view_maxx)
    ax.set_ylim(view_miny, view_maxy)
    ax.set_axis_off()

    _city_labels(ax, cities_xy)

    # Legend in the lower-right whitespace, above the centered author credit
    _draw_legend(fig, palette, n_classes, fig_w, fig_h)

    # Author credit and data sources — centered for feed-size readability
    fig.text(0.5, 0.40 / fig_h,
             f"© {author}",
             ha="center", va="center",
             fontsize=9.8, color="#333333",
             transform=fig.transFigure)
    fig.text(0.5, 0.17 / fig_h,
             "CHELSA V2.1 / TerraClimate  ·  GADM 4.1  ·  SRTM",
             ha="center", va="center",
             fontsize=8.7, color="#333333",
             transform=fig.transFigure)

    fig.savefig(output_path, dpi=LINKEDIN_DPI, facecolor=BG)
    plt.close(fig)
    print(f"  Saved: {output_path}")


# ── Backwards-compat shims ────────────────────────────────────────────────────

def make_professional_map(rgba, extent, country_proj, admin1_proj,
                          short_names, cities_xy, palette, n_classes,
                          country_name, period, author,
                          output_path, dem=None, **_):
    make_map(rgba, dem, extent, country_proj, admin1_proj,
             short_names, cities_xy, palette, n_classes,
             country_name, period, author, output_path)


def make_public_map(rgba, extent, country_proj, admin1_proj,
                    short_names, cities_xy, palette, n_classes,
                    country_name, period, author,
                    output_path, dem=None, **_):
    make_map(rgba, dem, extent, country_proj, admin1_proj,
             short_names, cities_xy, palette, n_classes,
             country_name, period, author, output_path)


def make_3d_map(*args, **kwargs):
    pass
