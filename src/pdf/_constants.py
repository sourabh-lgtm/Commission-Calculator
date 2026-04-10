"""Brand colours and page layout constants for PDF generation."""
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm

# Brand colours matching arr-dashboard design system
CORAL   = colors.HexColor("#FF9178")
GREEN   = colors.HexColor("#16a34a")
PURPLE  = colors.HexColor("#7c3aed")
RED     = colors.HexColor("#dc2626")
DIM     = colors.HexColor("#595959")
BORDER  = colors.HexColor("#E0E0E0")
CARD_BG = colors.HexColor("#F5F5F5")
BLACK   = colors.black
WHITE   = colors.white

# Landscape A4: 297 × 210 mm  ->  usable width = 297 - 2x20 = 257 mm
PAGE_W, PAGE_H = landscape(A4)
MARGIN = 20 * mm
CONTENT_W = PAGE_W - 2 * MARGIN   # 257 mm
