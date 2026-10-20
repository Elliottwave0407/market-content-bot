"""Shared light theme + drawing helpers for every card (results, deals, FII/DII, news)."""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

BG, PANEL, BORDER = "#ffffff", "#f3f6fa", "#dde4ec"
TEXT, MUTED, HEAD = "#03070c", "#4a596a", "#1d2937"
GREEN, RED, AMBER, BLUE = "#0a6a40", "#b3201c", "#8f5700", "#1f66c1"
BAR_OLD = "#b9c6d6"
RATING_COLORS = {"Blockbuster": "#0a5c3a", "Excellent": "#0f7a4b", "Strong": "#3a9a5b", "Steady": "#5f7ea3", "Weak": "#c9792b", "Poor": "#c62f2f"}
BADGE_NAME = "QUARTER VERDICT"   # placeholder name; one-line change
TAGS = {"ORDER WIN": "#2a78d6", "ACQUISITION": "#6250d6", "CREDIT RATING": "#b97400", "DIVIDEND": "#0f7a4b",
        "CORPORATE ACTION": "#0f7a4b", "CONCALL": "#52606f", "MANAGEMENT": "#8a4fa0", "RISK": "#c62f2f",
        "RBI": "#1f3a8a", "SEBI": "#1f3a8a", "UPDATE": "#52606f"}

def new_fig(w=16, h=10):
    return plt.figure(figsize=(w, h), dpi=100, facecolor=BG)

def panel(fig, x, y, w, h, fc=PANEL, ec=BORDER, r=0.012):
    fig.patches.append(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0.002,rounding_size={r}", transform=fig.transFigure, facecolor=fc, edgecolor=ec, linewidth=1))

def chip(fig, x, y, w, h, text, color, fs=15):
    fig.patches.append(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.002,rounding_size=0.012", transform=fig.transFigure, facecolor=color, edgecolor="none"))
    fig.text(x + w / 2, y + h / 2, text, color="#ffffff", fontsize=fs, fontweight="bold", ha="center", va="center")

def footer(fig, text, y=0.035):
    fig.text(0.04, y, text, color=MUTED, fontsize=11, va="center")

_LOGO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "fingod_logo.png")

def brand(fig, y=None, h_in=0.95, x_right=0.975, top=0.975):
    """FinGod logo in the header, top-right (falls back to plain text if the file is missing)."""
    if getattr(fig, "_branded", False):
        return
    try:
        img = plt.imread(_LOGO)
        W, H = fig.get_size_inches()
        hh = h_in / H
        ww = hh * (img.shape[1] / img.shape[0]) * H / W
        ax = fig.add_axes([x_right - ww, top - hh, ww, hh], zorder=10)
        ax.imshow(img)
        ax.axis("off")
        fig._branded = True
    except Exception:
        fig.text(0.96, 0.035, "FinGod", color=MUTED, fontsize=12, fontweight="bold", ha="right", va="center")

NAVY, GOLD = "#12263f", "#c8962b"

def frame(fig):
    """Professional border: navy outer line + gold hairline inside."""
    if getattr(fig, "_framed", False):
        return
    from matplotlib.patches import Rectangle
    fig.patches.append(Rectangle((0.004, 0.004), 0.992, 0.992, transform=fig.transFigure, facecolor="none", edgecolor=NAVY, linewidth=5, zorder=20))
    fig.patches.append(Rectangle((0.0105, 0.0105), 0.979, 0.979, transform=fig.transFigure, facecolor="none", edgecolor=GOLD, linewidth=1.4, zorder=20))
    fig._framed = True

def save(fig, path):
    if not getattr(fig, "_branded", False):
        brand(fig)
    frame(fig)
    fig.savefig(path, facecolor=BG)
    plt.close(fig)
