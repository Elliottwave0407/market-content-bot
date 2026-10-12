"""Shared light theme + drawing helpers for every card (results, deals, FII/DII, news)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

BG, PANEL, BORDER = "#ffffff", "#f3f6fa", "#dde4ec"
TEXT, MUTED = "#0f1722", "#556577"
GREEN, RED, AMBER, BLUE = "#0f7a4b", "#c62f2f", "#a86a00", "#2a78d6"
BAR_OLD = "#b9c6d6"
RATING_COLORS = {"Excellent": "#0f7a4b", "Great": "#3a9a5b", "Good": "#7d9b1a", "OK": "#b97400", "Weak": "#c62f2f"}
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

def brand(fig, y=0.035):
    fig.text(0.96, y, "FinGod", color=MUTED, fontsize=12, fontweight="bold", ha="right", va="center")

def save(fig, path):
    fig.savefig(path, facecolor=BG)
    plt.close(fig)
