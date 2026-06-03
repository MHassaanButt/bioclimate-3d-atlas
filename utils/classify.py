"""Bivariate classification: Fisher breaks + RGBA color grid."""

import numpy as np
import matplotlib.colors as mcolors


def fisher_breaks(values: np.ndarray, n: int) -> np.ndarray:
    try:
        from jenkspy import JenksNaturalBreaks
        jnb = JenksNaturalBreaks(n_classes=n)
        jnb.fit(values)
        brks = np.array(jnb.breaks_)
        brks[0]  -= 1e-9
        brks[-1] += 1e-9
        return brks
    except ImportError:
        print("  jenkspy not found — falling back to quantile breaks")
        return np.percentile(values, np.linspace(0, 100, n + 1))


def bivariate_classify(temp: np.ndarray, prec: np.ndarray,
                       n_classes: int, palette: dict):
    """
    Classify temp × prec into n_classes × n_classes grid.
    Returns (t_cls, p_cls, valid_mask, rgba_array).
    """
    valid  = ~(np.isnan(temp) | np.isnan(prec))
    t_brks = fisher_breaks(temp[valid], n_classes)
    p_brks = fisher_breaks(prec[valid], n_classes)
    print(f"  Temp breaks : {t_brks.round(1)}")
    print(f"  Prec breaks : {p_brks.round(1)}")

    t_cls = np.clip(np.digitize(temp, t_brks[1:-1]) + 1, 1, n_classes)
    p_cls = np.clip(np.digitize(prec, p_brks[1:-1]) + 1, 1, n_classes)
    t_cls[~valid] = 0
    p_cls[~valid] = 0

    rgba = np.zeros((*temp.shape, 4), dtype=float)
    for key, hex_col in palette.items():
        tc, pc = map(int, key.split("-"))
        cell = valid & (t_cls == tc) & (p_cls == pc)
        rgba[cell] = mcolors.to_rgba(hex_col)

    return t_cls, p_cls, valid, rgba
