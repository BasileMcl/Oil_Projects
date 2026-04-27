"""Build the oil-portfolio chartbook as a PDF using reportlab.

This is the Python-only fallback for the LaTeX chartbook (.tex in same folder).
Runs without a LaTeX installation. Uses the same structure, same charts,
same narrative as the .tex file — just rendered via reportlab instead of
TeX.

Usage:
    cd Projects/_chartbook
    /opt/anaconda3/bin/python build_pdf.py
    # Produces: Oil_Portfolio_Chartbook_2026-04-24.pdf
"""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle,
    PageBreak, KeepTogether
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY


# === Paths & theme ==========================================================
ROOT = Path(__file__).resolve().parent.parent  # Projects/
OUT  = Path(__file__).resolve().parent / 'Oil_Portfolio_Chartbook_2026-04-24.pdf'

FIG = {
    'lsgo':          ROOT / 'Forward_Curves_Analysis' / 'outputs' / 'figures' / 'lsgo',
    'brent':         ROOT / 'Forward_Curves_Analysis' / 'outputs' / 'figures' / 'brent',
    'wti':           ROOT / 'Forward_Curves_Analysis' / 'outputs' / 'figures' / 'wti',
    'cross_market':  ROOT / 'Forward_Curves_Analysis' / 'outputs' / 'figures' / 'cross_market',
    'cracks':        ROOT / 'Spot_Cracks_Analysis'     / 'outputs' / 'figures' / 'cracks',
    'fund':          ROOT / 'Spot_Cracks_Analysis'     / 'outputs' / 'figures' / 'fundamentals',
    'regional':      ROOT / 'Spot_Cracks_Analysis'     / 'outputs' / 'figures' / 'regional',
    'executive':    ROOT / 'Spot_Cracks_Analysis'     / 'outputs' / 'figures' / 'executive',
    'arb':           ROOT / 'Physical_Arb_Analysis'    / 'outputs' / 'figures',
}

OB_BLUE   = colors.HexColor('#1f4e79')
OB_RED    = colors.HexColor('#c00000')
OB_ORANGE = colors.HexColor('#e8601b')
OB_GREEN  = colors.HexColor('#238b45')
OB_GREY   = colors.HexColor('#888888')
OB_BG     = colors.HexColor('#f5f5f5')

# === Styles ==================================================================
styles = getSampleStyleSheet()

STY_TITLE_BIG = ParagraphStyle(
    'TitleBig', parent=styles['Title'],
    fontSize=38, leading=42, textColor=OB_BLUE,
    alignment=TA_CENTER, spaceAfter=8)
STY_H1 = ParagraphStyle(
    'H1', parent=styles['Heading1'],
    fontSize=14, leading=18, textColor=OB_BLUE,
    spaceBefore=8, spaceAfter=6, fontName='Helvetica-Bold')
STY_H2 = ParagraphStyle(
    'H2', parent=styles['Heading2'],
    fontSize=11, leading=14, textColor=OB_ORANGE,
    spaceBefore=6, spaceAfter=3, fontName='Helvetica-Bold')
STY_BODY = ParagraphStyle(
    'Body', parent=styles['BodyText'],
    fontSize=9, leading=12, alignment=TA_JUSTIFY,
    spaceAfter=5)
STY_CAPTION = ParagraphStyle(
    'Caption', parent=styles['BodyText'],
    fontSize=8, leading=10, textColor=OB_GREY,
    alignment=TA_CENTER, italic=True, spaceBefore=2, spaceAfter=6,
    fontName='Helvetica-Oblique')
STY_CALLOUT = ParagraphStyle(
    'Callout', parent=styles['BodyText'],
    fontSize=8.5, leading=11, spaceAfter=3,
    backColor=OB_BG, borderColor=OB_BLUE, borderWidth=0.6,
    borderPadding=6, leftIndent=0, rightIndent=0)
STY_REDCALL = ParagraphStyle(
    'RedCall', parent=STY_CALLOUT,
    borderColor=OB_RED)
STY_BIG_NUM = ParagraphStyle(
    'BigNum', parent=styles['BodyText'],
    fontSize=24, leading=28, textColor=OB_RED,
    alignment=TA_CENTER, fontName='Helvetica-Bold')
STY_BIG_NUM_SUB = ParagraphStyle(
    'BigNumSub', parent=styles['BodyText'],
    fontSize=9, leading=11, textColor=OB_GREY,
    alignment=TA_CENTER, spaceAfter=4)


# === Page frame: header + footer =============================================
def page_frame(canvas, doc):
    canvas.saveState()
    canvas.setFont('Helvetica-Oblique', 8)
    canvas.setFillColor(OB_GREY)
    canvas.drawString(2*cm, A4[1] - 1.2*cm, 'Oil Portfolio Chartbook — Week 17, 2026')
    canvas.drawRightString(A4[0] - 2*cm, A4[1] - 1.2*cm, '24-Apr-2026')
    canvas.setStrokeColor(OB_BLUE)
    canvas.setLineWidth(0.4)
    canvas.line(2*cm, A4[1] - 1.4*cm, A4[0] - 2*cm, A4[1] - 1.4*cm)
    canvas.setFont('Helvetica', 8)
    canvas.drawCentredString(A4[0]/2, 1.2*cm,
                              f'Confidential — Page {doc.page}')
    canvas.restoreState()


# === Helpers =================================================================
def figimg(key: str, name: str, width=None, height=None, max_h=None):
    """Load a figure from the project outputs tree, preserving aspect ratio
    but capping height so it fits on the page."""
    path = FIG[key] / name
    if not path.exists():
        return Paragraph(f'[missing chart: {name}]', STY_CAPTION)
    if width is None:
        width = 16 * cm
    if height is not None:
        return Image(str(path), width=width, height=height)
    # Aspect-preserve with height cap
    img = Image(str(path), width=width)
    # Compute natural height; if too tall, resize to max_h keeping aspect
    if max_h is None:
        max_h = 10 * cm
    if img.drawHeight > max_h:
        ratio = max_h / img.drawHeight
        img.drawHeight = max_h
        img.drawWidth = img.drawWidth * ratio
    return img


def caption(text: str):
    return Paragraph(f'<i>{text}</i>', STY_CAPTION)


def body(text: str):
    return Paragraph(text, STY_BODY)


def h1(text: str):
    return Paragraph(text, STY_H1)


def h2(text: str):
    return Paragraph(text, STY_H2)


def callout(title: str, text: str, red: bool = False):
    """A bordered callout box."""
    style = STY_REDCALL if red else STY_CALLOUT
    return Paragraph(f'<b>{title}</b><br/>{text}', style)


def bignum(number: str, label: str):
    return [Paragraph(number, STY_BIG_NUM),
            Paragraph(label, STY_BIG_NUM_SUB)]


def two_col(left, right, left_w=10*cm, right_w=8.5*cm):
    """Build a 2-column Table of flowables."""
    return Table([[left, right]],
                 colWidths=[left_w, right_w],
                 style=TableStyle([
                     ('VALIGN', (0,0), (-1,-1), 'TOP'),
                     ('LEFTPADDING', (0,0), (-1,-1), 0),
                     ('RIGHTPADDING', (0,0), (-1,-1), 6),
                 ]))


# === Build pages =============================================================
story = []


def page_cover():
    story.extend([
        Spacer(1, 3*cm),
        Paragraph('<b>OIL PORTFOLIO</b>', STY_TITLE_BIG),
        Paragraph('<b>CHARTBOOK</b>', STY_TITLE_BIG),
        Spacer(1, 0.6*cm),
        Paragraph('<font color="#888888">Forward curves · cracks · physical arb</font>',
                  ParagraphStyle('sub', parent=styles['BodyText'],
                                  fontSize=14, alignment=TA_CENTER, leading=18)),
        Paragraph('<font color="#888888">Week 17, 2026</font>',
                  ParagraphStyle('sub2', parent=styles['BodyText'],
                                  fontSize=12, alignment=TA_CENTER, leading=16)),
        Spacer(1, 1.5*cm),
        Table([
            [Paragraph('<b>REGIME: HORMUZ-BLOCKADE CRISIS</b><br/>'
                      '<font size="9">EU 20th sanctions package released today<br/>'
                      'OFAC GL 134 wind-down expired 11 April<br/>'
                      'Freight WS 2–4× historical averages<br/>'
                      'Med ULSD inverted over NWE (first sustained this cycle)</font>',
                      ParagraphStyle('cover-cal', parent=STY_BODY,
                                      fontSize=12, alignment=TA_CENTER, leading=16))]
        ], colWidths=[13*cm],
        style=TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), OB_BG),
            ('BOX', (0,0), (-1,-1), 1, OB_BLUE),
            ('TOPPADDING', (0,0), (-1,-1), 12),
            ('BOTTOMPADDING', (0,0), (-1,-1), 12),
            ('LEFTPADDING', (0,0), (-1,-1), 12),
            ('RIGHTPADDING', (0,0), (-1,-1), 12),
        ])),
        Spacer(1, 2*cm),
        Paragraph('<font color="#888888">Published 24-Apr-2026</font>',
                  ParagraphStyle('ver', parent=styles['BodyText'],
                                  fontSize=10, alignment=TA_CENTER)),
        PageBreak(),
    ])


def page_contents():
    story.append(h1('Contents'))
    rows = [
        ['#', 'Theme', 'Page'],
        ['1',  'Executive summary — 90-second read', '3'],
        ['2',  'Market regime & sanctions landscape', '4'],
        ['3',  'Forward curves — LSGO (regime break)', '5'],
        ['4',  'Forward curves — Brent & WTI long history', '6'],
        ['5',  'Cross-market coupling — regime-conditional β', '7'],
        ['6',  'NWE / Med cracks & 2026 signature', '8'],
        ['7',  'Fundamentals I — stocks & US 43-yr utilisation', '9'],
        ['8',  'Fundamentals II — US yields & EU refinery runs', '10'],
        ['9',  'Fundamentals III — EU consumption deficit', '11'],
        ['10', 'Regional flows — Russia & OPEC trade', '12'],
        ['11', 'Physical arbitrage — engine & methodology', '13'],
        ['12', 'Physical arbitrage — historical scenarios', '14'],
        ['13', 'Trading ideas — dated 2026-04-24', '15'],
        ['14', 'Methodology, caveats & data sources', '16'],
    ]
    tbl = Table(rows, colWidths=[1*cm, 12*cm, 2*cm])
    tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), OB_BLUE),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('ALIGN', (0,0), (0,-1), 'CENTER'),
        ('ALIGN', (-1,1), (-1,-1), 'CENTER'),
        ('FONTSIZE', (0,0), (-1,-1), 9.5),
        ('LINEBELOW', (0,0), (-1,-1), 0.3, OB_GREY),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, OB_BG]),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 0.5*cm))
    story.append(callout('How to use this chartbook',
        'Each section is one page. Each callout flags the single number '
        'that sets the read. Every number is dated, every chart is regenerable '
        'from the GitHub repo (<code>Projects/</code> tree). The three engines: '
        '<code>ForwardCurveAnalysis</code>, <code>CrackSpreadAnalysis</code>, '
        '<code>CargoArb</code>. Data-source index on page 16.'))
    story.append(PageBreak())


def page_exec_summary():
    story.append(h1('1. Executive summary — today\'s read in 90 seconds'))

    left = [
        body('<b>Three things matter this week.</b>'),
        body('<b>(1) Crack hedge β is regime-dependent.</b> Cross-project link: '
             'LSGO forward-curve regime conditions NWE crack β — '
             'Crisis ≈ 0.61 vs Normal ≈ 0.34, a <b><font color="#c00000">1.78× ratio</font></b>. '
             'LSGO is in Crisis today, so a static hedge is mis-sized by that '
             'factor. Portfolio\'s strongest cross-project finding.'),
        body('<b>(2) Med ULSD inverted over NWE</b> — first sustained session '
             'this cycle. CIF Med $1,402.50/mt vs CIF NWE $1,382.75/mt '
             '(<i>Med Cargo Wk-15</i>). Active trade is NWE → Med <i>import</i>, '
             'not Med → NWE. Engine returns negative net P&L as the flip signal.'),
        body('<b>(3) EU 20th sanctions package (today).</b> Bans transactions with '
             '<b>Tuapse</b>, Murmansk, Karimun (Indonesia); 46 new shadow-fleet '
             'vessels (632 total); mandatory due diligence on tanker sales. '
             'Urals arb increasingly non-executable for G7-linked participants — '
             'Project 3 thesis in a headline.'),
    ]

    right = [
        callout('Headline numbers — 24-Apr-2026',
            'Dated Brent &nbsp;&nbsp;~$110.4/bbl (diff +$5.04)<br/>'
            'ICE Brent M1 (Jun-26) &nbsp;&nbsp;$105.33<br/>'
            'ICE LSGO M1 (May-26) &nbsp;&nbsp;$1,249.00/mt<br/>'
            'ULSD CIF Med &nbsp;&nbsp;$1,308.00/mt<br/>'
            'ULSD CIF NWE &nbsp;&nbsp;$1,292.50/mt<br/>'
            '3-2-1 NWE crack &nbsp;&nbsp;~$37/bbl<br/>'
            'US refinery util &nbsp;&nbsp;89.1% (Apr 17 EIA)<br/>'
            'Hormuz transits &nbsp;&nbsp;7/day vs ~30 normal<br/>'
            'LSGO Crisis-days OOS &nbsp;&nbsp;31%'),
        Spacer(1, 4),
        callout('Trading ideas — see p.15',
            '1. Long NWE ULSD crack / short Brent <b>(HIGH, β=0.61)</b><br/>'
            '2. Fade ULSD–EBOB premium at extremes <b>(MED, watchlist)</b><br/>'
            '3. USGC→Med ULSD arb — on the edge <b>(MED/LOW, watchlist)</b>',
            red=True),
    ]
    story.append(two_col(left, right))
    story.append(Spacer(1, 0.3*cm))
    story.append(figimg('executive', 'chart_01_dashboard.png', width=17*cm))
    story.append(caption('Dashboard: 3-2-1 crack · SPR · US util · diesel-gas premium.'))
    story.append(PageBreak())


def page_regime():
    story.append(h1('2. Market regime & sanctions landscape'))
    story.append(h2('Regime context'))

    left = [
        body('The current regime is <b>Hormuz-blockade crisis</b>, starting '
             'February 2026 and escalating through April. US Navy activated a '
             'full blockade on 13 April 2026, locking in the loss of AG crude '
             'loadings that had averaged 3.8 mb/d in early April versus '
             'pre-war 17+ mb/d.'),
        body('Effects priced across the complex:<br/>'
             '• LSGO Crisis regime on 31% of OOS days vs 1% pre-2025 '
             '(16-month OOS; wide CI on level, direction unambiguous).<br/>'
             '• Brent–WTI basin spread widened to +$8/bbl peak.<br/>'
             '• Freight WS 2–4× historical averages on most dirty routes.<br/>'
             '• Jet CIF Med crack all-time high +$69/bbl; ULSD +$55.52/bbl.'),
        h2('Sanctions landscape — current'),
        body('<b>OFAC General License 134</b> (12 March 2026): wind-down '
             'authorisation for Russian-origin crude and products loaded <i>on '
             'or before</i> 12 March, executed through 11 April 2026. That '
             'window has now expired.'),
        body('<b>EU 20th package</b> (released today, 23-Apr-2026): transaction '
             'ban with <b>Tuapse, Murmansk</b>, and Karimun (Indonesia); 46 '
             'vessels added to port-access bans (total 632 shadow fleet); '
             'mandatory due diligence on tanker sales; maintenance services '
             'ban for Russian LNG tankers; from 1 January 2027, illegal to '
             'provide LNG terminal services to Russian entities.'),
    ]

    sanctions_table = Table([
        ['Port', 'Sanctions flag'],
        ['Novorossiysk', 'PRICE_CAP'],
        ['Primorsk', 'PRICE_CAP'],
        ['Tuapse', 'EU BANNED'],
        ['Murmansk', 'EU BANNED'],
        ['Karimun (ID)', 'EU BANNED'],
        ['Kulevi (GE)', '(shadow)'],
    ], colWidths=[3.5*cm, 3.5*cm])
    sanctions_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), OB_BLUE),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('TEXTCOLOR', (1,3), (1,5), OB_RED),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTNAME', (1,3), (1,5), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 8.5),
        ('LINEBELOW', (0,0), (-1,-1), 0.3, OB_GREY),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, OB_BG]),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))

    right = [sanctions_table, Spacer(1, 6),
             callout('Sources',
                     'OFAC GL 134 PDF<br/>consilium.europa.eu<br/>2026-04-23 press release')]
    story.append(two_col(left, right))
    story.append(Spacer(1, 0.2*cm))
    story.append(figimg('brent', 'chart_09_event_timeline.png', width=15*cm))
    story.append(caption('Brent event timeline — Hormuz window at right-edge.'))
    story.append(PageBreak())


def page_lsgo():
    story.append(h1('3. Forward curves — LSGO (regime break)'))

    left = [
        body('LSGO M1-M3 peak at <b>293.75 USD/MT</b> on 2026-04-02 — widest '
             'on record. Backwardation is the default state of European diesel '
             '(68% of full-sample days), but 2025–2026 is a <i>regime break</i>, '
             'not an amplification: Crisis state 31% of OOS days vs 1% '
             'in-sample.'),
        body('CDF thresholds (80/95/99 pct pre-2025 M1-M6): Tight 3.60, Stress '
             '6.71, Crisis 8.25 USD/MT. Peak Z-score 139.8 on 2026-04-02 under '
             'IS-anchored methodology — the pre-2025 distribution cannot '
             'generate this print.'),
        body('Volatility tracks curve width, not flat price: corr(M1-M6, '
             'annualised vol) = 0.77. A tight-curve regime is a high-vol '
             'regime; size position risk accordingly.'),
        callout('Sample length',
                '<b>16-month OOS window.</b> Every regime-frequency claim '
                'carries wide error bars at this sample length. Treat '
                '"Crisis 31%" as descriptive of the current episode, not '
                'predictive of a distribution.'),
    ]
    right = [
        figimg('lsgo', 'chart_01_price_vol.png', width=9*cm),
        caption('LSGO price + 20-day annualised vol, full sample.'),
        figimg('lsgo', 'chart_11_regime.png', width=9*cm),
        caption('CDF regime classification, IS-calibrated.'),
    ]
    story.append(two_col(left, right))
    story.append(Spacer(1, 0.2*cm))
    story.append(figimg('lsgo', 'chart_13_hmm_regime.png', width=15*cm))
    story.append(caption('HMM 2-state Gaussian on M1-M6 — BIC justifies K=2 '
                         'over K=3, 4. Next-day transition-matrix forecast in underlying notebook.'))
    story.append(PageBreak())


def page_brent_wti():
    story.append(h1('4. Forward curves — Brent & WTI (long-history context)'))
    left = [
        body('<b>Brent</b>: backwardation 68.9% full-sample, OOS regime '
             'bimodal — either Normal (82%) or Crisis (17%), Tight/Stress '
             'nearly empty. Brent prices geopolitical premium '
             '<i>discontinuously</i>; paper-only risk models miss the jump.'),
        body('<b>April 2026 Dated-vs-paper dislocation</b>: Dated printed '
             '$144.42/bbl on 2026-04-07 while Jun-26 futures settled $109.27 '
             '— a ≈ $35 cash-over-paper premium. Dated file covers 69 days '
             'only; treat as event study, not basis distribution.'),
        body('<b>WTI</b>: the tempered crude. Crisis regime ≈ 13% OOS '
             '(vs 17% Brent, 31% LSGO). US-crude insulation from Hormuz is '
             'the mechanism: disrupted AG barrels price Brent first; WTI '
             'only via basin-arb economics.'),
        body('OPEC ASB T74 monthly 1990+ provides the long-history sanity '
             'check: today\'s Brent ≈ top-quartile of 36 years, not '
             'unprecedented (2008 peak $134, 2011–2014 sustained $100+).'),
    ]
    right = [
        figimg('brent', 'chart_14_opec_asb_long_history.png', width=9.5*cm),
        caption('Brent & WTI monthly 1990+, OPEC ASB T74, IS/OOS shading.'),
    ]
    story.append(two_col(left, right))
    story.append(Spacer(1, 0.3*cm))
    story.append(figimg('brent', 'chart_12_dated_event_study.png', width=16*cm))
    story.append(caption('Dated Brent vs paper M1 during April 2026 dislocation window.'))
    story.append(PageBreak())


def page_cross_market():
    story.append(h1('5. Cross-market coupling — regime-conditional β'))
    left = [
        body('The portfolio\'s strongest finding. LSGO–Brent ΔM1-M3 correlation: '
             '<b>Normal 0.39, Crisis 0.81, ratio 2.1×</b>.'),
        body('Rolling 90-day β latest reading ≈ 12.7 vs full-sample mean 2.85 '
             '— a <b>4.5× mis-sizing</b> for static hedges. The annual-coupling '
             'chart shows the trend rising 2020 → 2026, but the regime-'
             'conditional breakdown reveals the rise is <i>time spent in '
             'Crisis</i>, not a structural shift.'),
        body('<b>End-2020 correlation jump — explained.</b> The rolling '
             'Δ-correlation steps from ≈ 0.3 to ≈ 0.6 within a four-week '
             'window centred on December 2020. The 3 Dec OPEC+ meeting '
             'rebalanced quotas, and the 8 Dec UK Pfizer / 11 Dec US EUA '
             'rollout re-anchored demand expectations for both crude and '
             'distillate on the same vaccine-enabled-recovery narrative.'),
        body('<b>March 2026 Brent-WTI brutal move — explained.</b> +$7–8/bbl '
             'basin spread through March-April 2026. ≈ 18 mb/d of pre-war AG '
             'loadings transit Hormuz and feed the Brent-pricing waterborne '
             'pool; WTI insulated behind US export logistics.'),
    ]
    right = [
        figimg('cross_market', 'cross_04_annual_coupling.png', width=9*cm),
        caption('Annual LSGO-Brent coupling, 2020 → 2026.'),
        figimg('cross_market', 'cross_09_basin_spread.png', width=9*cm),
        caption('Brent − WTI M1 spread with event markers.'),
    ]
    story.append(two_col(left, right))
    story.append(Spacer(1, 0.2*cm))
    story.append(figimg('cracks', 'chart_09b_rolling_hedge_ratio_by_regime.png', width=15*cm))
    story.append(caption('Cross-project link: NWE crack β scattered by LSGO curve regime. '
                         'Crisis β = 0.61, Normal β = 0.34, ratio 1.78×.'))
    story.append(PageBreak())


def page_cracks():
    story.append(h1('6. NWE / Med cracks & the 2026 signature'))
    left = [
        body('NWE 3-2-1 refining margin peaked at 105.07 USD/bbl on 2022-06-06 '
             '(post-invasion squeeze). The 2026 composite peak is lower — a '
             '<b>slate artefact</b>: 3-2-1 weights gasoline 2× distillate, so '
             'a cross-product squeeze (2022: both legs widened) dwarfs a '
             'diesel-specific shock (2026).'),
        body('Switch to <b>ULSD-only slate</b> and the 2026 Crisis-High '
             'cluster is visible — the signal was dilution-hidden in the '
             'composite.'),
        body('<b>External anchoring</b>: OPEC ASB T76 (Rotterdam gasoil 10 ppm '
             'vs Brent, 1983–2024) cross-checks our Platts-derived Brent-ULSD '
             'NWE crack at r ≈ 1.0 on overlap years. Level offset ≈ $2/bbl '
             'reflects product-spec and regional assessment differences.'),
        callout('Volumetric P&L — today',
                '100 kbpd refinery, current 3-2-1 crack $33.86/bbl:<br/>'
                '<b>Normal regime (90% util)</b>: $1.1 B/year gross<br/>'
                '<b>Current regime (70% util)</b>: $860 M/year gross<br/>'
                'War-crisis logistics cut 22% of nameplate P&L.'),
    ]
    right = [
        figimg('cracks', 'chart_01_time_series.png', width=9*cm),
        caption('3-2-1 NWE crack, full sample with event overlay.'),
        figimg('cracks', 'chart_04_regime.png', width=9*cm),
        caption('ULSD slate — 2026 Crisis cluster visible.'),
    ]
    story.append(two_col(left, right))
    story.append(figimg('cracks', 'chart_08_opec_crosscheck.png', width=14*cm))
    story.append(caption('Platts-derived NWE ULSD crack vs OPEC ASB Rotterdam gasoil, '
                         'r = +1.00 on 4 overlap years.'))
    story.append(PageBreak())


def page_fund1():
    story.append(h1('7. Fundamentals I — stocks & US 43-year utilisation'))
    left = [
        body('<b>US stocks asymmetry</b> is the current tell: Gasoline 84th '
             'pct, Distillate 50th pct, Crude incl. SPR 72nd pct. The <b>'
             'diesel leg</b> responds structurally harder to any supply '
             'shock than the gasoline leg — exactly the 2026 OOS pattern.'),
        body('<b>US refinery utilisation</b>: full EIA weekly 1982+ puts '
             'today\'s 91.4% at only the <b>44th pct of a 43-year '
             'distribution</b>, even though it\'s top-third on a 5y view. '
             'Counters recency bias: "tight vs recent memory, not vs '
             'structural history".'),
        body('<b>SPR drawdown</b> ≈ 45% from 2022 peak. A 291 Mbbl draw is '
             'unprecedented; the reverse flow (refill) is a multi-year '
             'sour-crude demand story that the market has not priced.'),
    ]
    right = [
        figimg('fund', 'chart_08_us_util_long.png', width=9*cm),
        caption('US refinery utilisation, full EIA 1982+ context.'),
        figimg('fund', 'chart_02_spr_drawdown.png', width=9*cm),
        caption('SPR drawdown since 2021 peak.'),
    ]
    story.append(two_col(left, right))
    story.append(PageBreak())


def page_fund2():
    story.append(h1('8. Fundamentals II — US yields & EU refinery runs'))
    left = [
        body('<b>US yield slate — the response that didn\'t come.</b> '
             'Distillate tilt flat at –17 pp through 2025–2026. Refiners '
             'have <i>not</i> structurally swung toward diesel despite '
             'the crack squeeze. Either: perceived as short-lived, or '
             'kinetic constraints at max-distillate cutpoint. Either way, '
             '<b>supply response from yield mix is not coming</b>. Cracks '
             'clear via price or imports.'),
        body('<b>EU refinery intake</b>: Germany, Netherlands, Italy, '
             'France, Spain drive the line. Total runs ≈ 50–55 Mt/month. '
             'Current prints below 12-month MA — mild run cut consistent '
             'with margin + crude-supply stress.'),
        body('Trailing months with < 10 country reporters dropped — '
             'Eurostat publishes with 2–3 month lag.'),
    ]
    right = [
        figimg('fund', 'chart_09_us_yields.png', width=9*cm),
        caption('US refinery yields 2010+, flat distillate tilt.'),
        figimg('fund', 'chart_10_eu_refinery_intake.png', width=9*cm),
        caption('EU refinery crude intake, top-8 + 12-mo MA.'),
    ]
    story.append(two_col(left, right))
    story.append(PageBreak())


def page_fund3():
    story.append(h1('9. Fundamentals III — EU diesel consumption deficit'))
    left = []
    left.extend(bignum('≈ 29 Mt/year', 'EU structural diesel import dependence'))
    left += [
        Spacer(1, 0.3*cm),
        body('Consumption (Eurostat gross inland deliveries) minus EU '
             'refinery output ≈ +2,400 kt/month positive gap. Europe imports '
             'that deficit via USG / India / AG / Russia shadow-fleet. '
             '<b>The imported barrel sets NWE ULSD pricing.</b>'),
        body('This is why NWE ULSD can decouple from WTI-anchored paper '
             'cracks under stress, and why the Med → NWE arb inversion '
             '(today\'s situation) is a real signal, not a data quirk.'),
        body('The "Med trades over NWE by $4/mt" print in <i>Med Cargo '
             'Week-15</i> is the direct consequence of the deficit meeting '
             'a supply-cut (Hormuz). The reverse arb (NWE → Med import) is '
             'actively pulling USG and ARA cargoes into Algeciras.'),
    ]
    right = [
        figimg('fund', 'chart_12_eu_consumption_vs_output.png', width=9.5*cm),
        caption('EU diesel balance — consumption vs output; gap = imports needed.'),
        figimg('fund', 'chart_13_eu_consumption_annual.png', width=9.5*cm),
        caption('Annual deficit — post-2022 mean step-changed up.'),
    ]
    story.append(two_col(left, right))
    story.append(PageBreak())


def page_regional():
    story.append(h1('10. Regional flows — Russia reroute & OPEC trade'))
    left = [
        body('<b>Russian diesel post-price-cap</b>: Turkey, Brazil, Middle '
             'East dominate destinations. The flow did not die; it rerouted. '
             'Russian barrels still in the global pool but not reaching '
             'Europe — meaning the EU <i>replacement supply</i> is what sets '
             'NWE price.'),
        body('<b>EU diesel imports</b> — diversified across US / India / ME '
             '/ WAF. No single country dominates post-2022, which means '
             'supply resilience when any single source drops out, but every '
             'arb change moves the mix.'),
        body('<b>OPEC ASB structural view</b>: US + Saudi + Russia dominate '
             'crude exports. US product exports grew from a footnote '
             'pre-2015-export-ban-repeal to the world\'s largest flow today.'),
        body('<b>Freight</b>: 2022 invasion + 2024 Red Sea + 2026 Hormuz '
             'visible as synchronised WS% spikes across dirty and clean '
             'routes — ton-mile expansion is the mechanism.'),
    ]
    right = [
        figimg('regional', 'chart_04_russia_export.png', width=9*cm),
        caption('Russia diesel exports by destination.'),
        figimg('regional', 'chart_07_opec_trade_flows.png', width=9*cm),
        caption('OPEC ASB global crude & product exports top-12.'),
    ]
    story.append(two_col(left, right))
    story.append(figimg('regional', 'chart_08_opec_tanker_freight.png', width=14*cm))
    story.append(caption('OPEC ASB tanker freight WS% — 2022 / 2024 / 2026 spikes visible.'))
    story.append(PageBreak())


def page_arb_method():
    story.append(h1('11. Physical arbitrage — engine & methodology'))
    left = [
        body('The parametric <code>CargoArb</code> class turns any cargo '
             'decision into a 9-item P&L waterfall: gross spread → freight '
             '→ port costs → canal tolls → financing → insurance → '
             'demurrage → broker → net arb.'),
        body('User selects: origin, destination, vessel class (MR/LR1/LR2/'
             'Aframax/Suezmax/VLCC), grade, cargo tonnage or capacity '
             'utilisation, WS rate, forward-price base, regional premium/'
             'discount on each side.'),
        body('Freight via standard Worldscale: <i>freight = WS × flat / 100</i>. '
             'Voyage days computed from distance / laden speed. Density per '
             'grade converts MT ↔ bbl.'),
        body('<b>Validation</b>: reproduces a 2026-Q2 TD6-class Suezmax '
             'fixture (WS 230.56, flat 11.09) to the dollar — freight '
             '$25.57/MT, cargo freight $3.45 M on 135 kMT.'),
    ]
    right = [
        figimg('arb', 'waterfall_single_cargo.png', width=9*cm),
        caption('Default example — BSea → Med Aframax, net +$23.31/bbl.'),
        figimg('arb', 'sensitivity_grid.png', width=9*cm),
        caption('2-D P&L surface: WS × gross spread. Dashed = break-even.'),
    ]
    story.append(two_col(left, right))
    story.append(PageBreak())


def page_arb_scenarios():
    story.append(h1('12. Physical arbitrage — historical scenarios'))
    left = [
        body('Four documented events replayed through the same engine.'),
        body('<b>2020-04 COVID</b> (WS 50, spread +$3): arithmetically open '
             'but tiny absolute $. Vol of flat price was the real risk.'),
        body('<b>2022-03 Russia invasion</b> (WS 220, spread +$35): '
             'arithmetically enormous. G7 price cap then reshaped the trade '
             '— 2023 Urals cargo at these economics could not find a '
             'compliant shipowner / insurer.'),
        body('<b>2024-01 Red Sea</b> (WS 145, spread +$10): Cape re-routing '
             'killed the economics. Engine says closed; market responded '
             'with Nigerian crude re-routing West.'),
        body('<b>2026-04 Hormuz</b> (WS 230, spread +$28 for BSea→Med Aframax): '
             '$23/bbl net, $13 M cargo. Arithmetically wide open; compliance-'
             'gated.'),
        callout('The arithmetic is never the full trade',
                '2022 Urals is the canonical case — enormous paper P&L, '
                'killed by compliance.'),
    ]
    right = [
        figimg('arb', 'scenario_backtest_pnl.png', width=9*cm),
        caption('Scenario backtest — WS (top) and net P&L (bottom).'),
        figimg('arb', 'route_comparison_pnl.png', width=9*cm),
        caption('Lane comparison — 5 canonical lanes, today\'s prints.'),
    ]
    story.append(two_col(left, right))
    story.append(PageBreak())


def page_trade_ideas():
    story.append(h1('13. Trading ideas — dated 24-Apr-2026'))

    story.append(h2('1. Long NWE ULSD crack, short Brent hedge — HIGH conviction'))
    story.append(body(
        '<b>View</b>. EU structurally ≈ 29 Mt/year short of diesel. US yields '
        'still gasoline-heavy (−17 pp distillate tilt, unchanged through '
        '2025–2026 despite margin signal). Hormuz kept AG loadings depressed. '
        'When three asymmetries point the same way and yield has failed to '
        'adjust, the clearing mechanism is price.'))
    story.append(body(
        '<b>Trade</b>. Long ULSD-only crack (not 3-2-1 composite — we want the '
        'pure diesel signal); hedge with Brent short. <b>Size with regime-'
        'conditioned β</b>: current LSGO = Crisis → β ≈ 0.61 vs Normal β ≈ 0.34, '
        'so roughly 1.8× more Brent short per ULSD long than a static hedge '
        'would imply.'))
    story.append(body(
        '<b>Trigger</b>. ULSD crack > IS 80th pct <i>and</i> US distillate '
        'stocks in bottom quintile of 5y range. Both conditions today.'))
    story.append(body(
        '<b>Kill switch</b>. Credible Hormuz de-escalation headline — the '
        'April 7 ceasefire-rumour tape unwound jet cracks $29/bbl in one '
        'session.'))

    story.append(h2('2. Fade the diesel–gasoline premium at extremes — MED conviction'))
    story.append(body(
        '<b>View</b>. ULSD-EBOB crack premium is mean-reverting around +$10, '
        'σ ≈ $8. Positive on >99% of days (EU structural diesel bias). Fade '
        'when >+$18 or <+$2.'))
    story.append(body(
        '<b>Today</b>. Mid-range, no signal. Watchlist weekly.'))
    story.append(body(
        '<b>Kill switch</b>. Structural regime change — EV adoption erodes '
        'diesel demand faster than expected, or major hydrocracker closure '
        'shifts output balance.'))

    story.append(h2('3. USGC→Med ULSD arb — MED/LOW conviction, watchlist'))
    story.append(body(
        '<b>View</b>. USGC–Med ULSD spread currently ≈ +$3.80/bbl net after '
        'freight — on the edge, not open to size. To open: MR Atlantic TCE '
        '< $100k/day (currently ≈ $120k) <i>and</i> Med ULSD CIF holding '
        '> $1,400/mt.'))
    story.append(body(
        '<b>Watch</b>. Freight regime + Med CIF.'))

    story.append(h2('Sizing notes'))
    story.append(body(
        'All sizing above is illustrative. Real desk execution goes through '
        'vol-targeted Kelly, margin-efficient vehicle selection (swaps vs '
        'futures), broker commission, and firm-level risk limits. The value '
        'of these ideas is the <b>triggers</b> — observable, falsifiable, '
        'unambiguous.'))
    story.append(PageBreak())


def page_methodology():
    story.append(h1('14. Methodology, caveats & data sources'))

    story.append(h2('The three engines'))
    eng_rows = [
        ['ForwardCurveAnalysis',
         'ICE Brent / LSGO / WTI M1-M12 daily pre-rolled settlements. Term '
         'structure, vol, IS-anchored Z-score, CDF-calibrated regime '
         'classification, 2-state Gaussian HMM with BIC model selection. '
         'Cross-market module: pair-wise correlation, rolling β, regime-'
         'conditional coupling, basin spread.'],
        ['CrackSpreadAnalysis',
         'NWE / Med 3-2-1 / 2-1-1 / ULSD / EBOB / FO35 slates. Platts USD/MT → '
         'USD/bbl via density. OPEC T76 external cross-check. Volumetric P&L '
         'normal-regime vs war-crisis. Rolling β optionally conditioned on '
         'Project 1 LSGO regime. HMM + next-day forecast.'],
        ['CargoArb',
         'Parametric P&L waterfall (9 components). Origin/destination/vessel/'
         'grade/cargo/WS/flat all user-variable. Voyage days from distance / '
         'laden speed. Canal tolls, port costs, financing, insurance, '
         'demurrage, broker commission. Break-even in WS and spread. 2-D '
         'sensitivity grid.'],
    ]
    eng_tbl = Table([
        [Paragraph(f'<b>{r[0]}</b>', STY_BODY),
         Paragraph(r[1], STY_BODY)] for r in eng_rows],
        colWidths=[4*cm, 13*cm])
    eng_tbl.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LINEBELOW', (0,0), (-1,-2), 0.3, OB_GREY),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(eng_tbl)

    story.append(h2('Data sources'))
    data_rows = [
        ['Domain', 'Source', 'As of'],
        ['Forward curves', 'Config FORWARD_PRICES_USD_BBL', '2026-04-24'],
        ['Physical prints', 'Platts European/AsiaPac/US Marketscan', '2026-04-24'],
        ['Tanker fixtures + WS', 'Platts Dirty/Clean Tankerwire', '2026-04-24'],
        ['US stocks + util', 'EIA weekly / monthly', '2026-04-17'],
        ['US yields', 'EIA monthly', '2026-01'],
        ['EU stocks + consumption', 'Eurostat nrg_cb_oilm', '2026-02'],
        ['WS freight (annual)', 'OPEC ASB 2025 T62 / T63', '2011-2024'],
        ['Sanctions — US', 'OFAC, Treasury (Hengli RFN Apr 24)', '2026-04-24'],
        ['Sanctions — EU', '20th package, consilium.europa.eu', '2026-04-23'],
    ]
    data_tbl = Table(data_rows, colWidths=[5*cm, 8*cm, 4*cm])
    data_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), OB_BLUE),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 8.5),
        ('LINEBELOW', (0,0), (-1,-1), 0.3, OB_GREY),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, OB_BG]),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))
    story.append(data_tbl)

    story.append(h2('Caveats — up front'))
    story.append(body(
        '• <b>16-month OOS window</b>. Regime-frequency claims carry wide '
        'error bars; direction unambiguous, level descriptive.<br/>'
        '• <b>Dated Brent</b> is 69 days only; treated as event study.<br/>'
        '• <b>Z-score axis capped ±5</b> for readability; actual peaks '
        'annotated (LSGO peak Z ≈ 140).<br/>'
        '• <b>Eurostat 2–3 month publication lag</b>; trailing months with '
        '< 10 country reporters dropped.<br/>'
        '• <b>UK post-Brexit</b> drops out of Eurostat after Dec-2020.<br/>'
        '• <b>WS sources</b> in Project 3 scenarios are a mix of direct prints '
        '(Baltic / Howe Robinson / Clarksons) and triangulated proxies.<br/>'
        '• <b>Not live</b>. Every price is a dated snapshot; cite 2026-04-24 '
        'when presenting.'))

    story.append(h2('What this chartbook does NOT model'))
    story.append(body(
        'Bunker-price pass-through • FFA forward-freight hedging • Vetting / '
        'OCIMF SIRE gates • EU ETS maritime cost (2024–2026 phase-in) • '
        'Sanctions / compliance overlay beyond port flags • Dirty ↔ clean '
        'vessel switching option • Laytime asymmetry • Counterparty / LC / '
        'sovereign risk. See <code>Physical_Arb_Analysis/docs/BLIND_SPOTS_FULL.md</code>.'))

    story.append(h2('Reproducibility'))
    story.append(body(
        'All charts regenerable via <code>bash generate_reports.sh</code> in '
        'each project folder. Shared palette in <code>plot_config.yaml</code>, '
        'event timeline in <code>major_dates.yaml</code>. Chartbook source: '
        '<code>Projects/_chartbook/Oil_Portfolio_Chartbook_2026-04-24.tex</code> '
        '(LaTeX) and <code>build_pdf.py</code> (Python fallback, this document).'))

    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph(
        '<font color="#888888">— End of chartbook —</font>',
        ParagraphStyle('end', parent=styles['BodyText'],
                        fontSize=9, alignment=TA_CENTER, textColor=OB_GREY)))


# === Assemble ===============================================================
def build():
    page_cover()
    page_contents()
    page_exec_summary()
    page_regime()
    page_lsgo()
    page_brent_wti()
    page_cross_market()
    page_cracks()
    page_fund1()
    page_fund2()
    page_fund3()
    page_regional()
    page_arb_method()
    page_arb_scenarios()
    page_trade_ideas()
    page_methodology()

    doc = SimpleDocTemplate(
        str(OUT), pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2.5*cm, bottomMargin=2*cm,
        title='Oil Portfolio Chartbook — 2026-04-24',
        author='Basile', creator='matplotlib + reportlab')
    doc.build(story, onFirstPage=page_frame, onLaterPages=page_frame)
    size_kb = OUT.stat().st_size / 1024
    print(f'Built {OUT.name} ({size_kb:,.0f} KB)')


if __name__ == '__main__':
    build()
