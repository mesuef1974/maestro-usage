"""تدقيق واجهات المنصّة بنظام التقييم الأولويّ لمهارة ui-ux-pro-max: عشر فئات بأوزان (حرج 4، عالٍ 3، متوسط 2، منخفض 1).

يفتح كل صفحة في Chromium (playwright) بثلاثة عروض (375/768/1440) وسمتين، ويقيس مؤشرات آلية ويصوّر، ثم يحسب درجة كل فئة وإجماليًّا من 100.
المخرجات أرقام وقيم منطقية فقط (لا نصوص صفحات): docs/ux_audit/<label>.json، ولقطات في reports/ux/<label>/ (خارج git).
التشغيل: python scripts/ux_audit.py --label before   ثم بعد التصميم --label after، ثم --compare before after.
فحوص تحتاج حكمًا بشريًّا (التباين على تدرّجات، دلالة اللون وحده، حالات الفراغ) تُدوَّن في docs/ux_audit.md ولا تدخل الدرجة الآلية.
"""
import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "http://127.0.0.1:8790/"
PAGES = ["index.html", "sessions.html", "hourly.html", "skills.html"]
VIEWS = {"mobile": (375, 812), "tablet": (768, 1024), "desktop": (1440, 900)}
WEIGHT = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
CATS = [("accessibility", "الوصول", "CRITICAL"), ("touch", "اللمس والتفاعل", "CRITICAL"), ("performance", "الأداء", "HIGH"),
        ("style", "اتساق النمط", "HIGH"), ("layout", "التخطيط والاستجابة", "HIGH"), ("typography", "الطباعة واللون", "MEDIUM"),
        ("animation", "الحركة", "MEDIUM"), ("forms", "النماذج والتغذية الراجعة", "MEDIUM"), ("navigation", "التنقّل", "HIGH"),
        ("charts", "الرسوم والبيانات", "LOW")]

PROBE = r"""
() => {
  const q = (s, r) => [...(r || document).querySelectorAll(s)];
  const vis = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const parse = c => { const m = c && c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; };
  const lin = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  const lum = c => 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b);
  const over = (f, b) => ({ r: f.r * f.a + b.r * (1 - f.a), g: f.g * f.a + b.g * (1 - f.a), b: f.b * f.a + b.b * (1 - f.a), a: 1 });
  const bgOf = e => { const stack = []; for (let n = e; n; n = n.parentElement) { const c = parse(getComputedStyle(n).backgroundColor); if (c && c.a > 0) { stack.push(c); if (c.a >= 1) break; } } let b = { r: 255, g: 255, b: 255, a: 1 }; for (let i = stack.length - 1; i >= 0; i--) b = over(stack[i], b); return b; };
  const cssText = [...document.styleSheets].map(s => { try { return [...s.cssRules].map(r => r.cssText).join('\n'); } catch (e) { return ''; } }).join('\n');
  const interactive = q('a[href]:not(.skip),button,input,select,textarea,summary,[tabindex]:not([tabindex="-1"])').filter(vis);
  const nameOf = e => (e.getAttribute('aria-label') || e.getAttribute('title') || e.textContent || (e.labels && e.labels[0] && e.labels[0].textContent) || e.getAttribute('placeholder') || '').trim();
  const unnamed = interactive.filter(e => !nameOf(e) && !(e.closest('label') && e.closest('label').textContent.trim())).length;
  const fields = q('input:not([type=hidden]),select,textarea').filter(vis);
  const unlabeled = fields.filter(e => !(e.getAttribute('aria-label') || e.getAttribute('aria-labelledby') || (e.labels && e.labels.length) || e.closest('label'))).length;
  const hs = q('h1,h2,h3,h4,h5,h6').map(h => +h.tagName[1]);
  let skips = 0; for (let i = 1; i < hs.length; i++) if (hs[i] - hs[i - 1] > 1) skips++;
  // التباين: عيّنة من عقد النص المرئية
  const seen = new Set(); let tested = 0, failed = 0; let tiny = 0, textChars = 0;
  const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (tw.nextNode() && tested < 500) {
    const n = tw.currentNode; const t = n.textContent.trim(); if (t.length < 2) continue; const e = n.parentElement; if (!e || seen.has(e) || !vis(e) || e.closest('script,style,svg')) continue; seen.add(e);
    const cs = getComputedStyle(e); const fg = parse(cs.color); if (!fg) continue; const bg = bgOf(e); const f = over(fg, bg);
    const L1 = lum(f), L2 = lum(bg); const ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
    const size = parseFloat(cs.fontSize), bold = parseInt(cs.fontWeight) >= 700; const need = (size >= 24 || (size >= 18.66 && bold)) ? 3 : 4.5;
    tested++; if (ratio < need) failed++;
    textChars += t.length; if (size < 12) tiny += t.length;
  }
  const small24 = interactive.filter(e => { const r = e.getBoundingClientRect(); return r.width < 24 || r.height < 24; }).length;
  const small44 = interactive.filter(e => { const r = e.getBoundingClientRect(); return r.height < 44 || r.width < 44; }).length;
  const btns = q('button').filter(vis); const ptr = btns.filter(b => getComputedStyle(b).cursor === 'pointer').length;
  const sizes = new Set(q('body *').filter(vis).slice(0, 3000).map(e => getComputedStyle(e).fontSize));
  const body = getComputedStyle(document.body);
  const tables = q('table'); const sortHdr = q('th').filter(th => th.querySelector('button')); const ariaSort = sortHdr.filter(th => th.hasAttribute('aria-sort'));
  const svgs = q('svg:not([aria-hidden=true])').filter(vis); const svgLabeled = svgs.filter(s => s.getAttribute('role') === 'img' || s.getAttribute('aria-label') || s.querySelector('title')).length;
  const navs = q('nav'); const nav = navs[0];
  const navLinks = nav ? q('a', nav) : [];
  const navStyle = nav ? getComputedStyle(nav) : null;
  const sidebar = q('[class*=side],[role=navigation],aside,nav').filter(vis).some(e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.height > r.width * 2 && (s.position === 'sticky' || s.position === 'fixed' || r.height > innerHeight * 0.8); });
  const persistent = q('nav,header,aside,[class*=side]').filter(vis).some(e => ['sticky', 'fixed'].includes(getComputedStyle(e).position));
  const h2 = q('h2').filter(vis);
  const collaps = q('details').length + q('[aria-expanded]').length;
  const nested = q('*').filter(e => { const s = getComputedStyle(e); return (s.overflowY === 'auto' || s.overflowY === 'scroll') && e.scrollHeight > e.clientHeight + 4 && e !== document.documentElement && e !== document.body; }).length;
  const rows = tables.map(t => t.querySelectorAll('tbody tr').length);
  const trans = q('body *').slice(0, 2500).map(e => getComputedStyle(e).transitionProperty).filter(p => p && p !== 'all' && p !== 'none');
  const layoutAnim = trans.filter(p => /(^|,\s*)(width|height|top|left|right|bottom|margin|padding)/.test(p)).length;
  const emoji = (document.body.innerText.match(/\p{Extended_Pictographic}/gu) || []).length;
  const page = q('.page,main,.container')[0]; const pageMax = page ? getComputedStyle(page).maxWidth : 'none';
  const paras = q('p,.sub,.note,dd').filter(vis).slice(0, 60); let longLine = 0;
  paras.forEach(p => { const r = p.getBoundingClientRect(); const fs = parseFloat(getComputedStyle(p).fontSize); if (r.width / (fs * 0.5) > 80) longLine++; });
  const inlineColor = q('[style]').filter(e => /color|background/.test(e.getAttribute('style') || '')).length;
  const rootVars = (cssText.match(/--[a-z0-9-]+\s*:/gi) || []).length;
  const vp = document.querySelector('meta[name=viewport]'); const vpc = vp ? vp.content : '';
  const inViewport = q('h2,h3').filter(h => { const r = h.getBoundingClientRect(); return vis(h) && r.top < innerHeight && r.bottom > 0; }).length;
  return {
    h: document.documentElement.scrollHeight, vh: innerHeight, sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth,
    dom: document.getElementsByTagName('*').length, inter: interactive.length, unnamed, fields: fields.length, unlabeled,
    h1: hs.filter(x => x === 1).length, hsk: skips, h2: h2.length, tables: tables.length, svgs: svgs.length, svgLabeled,
    tested, failed, tiny, textChars, small24, small44, btns: btns.length, ptr, fontSizes: sizes.size,
    lh: parseFloat(body.lineHeight) / parseFloat(body.fontSize), bodyFs: parseFloat(body.fontSize), tab: (body.fontVariantNumeric || '').includes('tabular'),
    focusVisible: /:focus-visible/.test(cssText), focus: /:focus/.test(cssText), reduced: /prefers-reduced-motion/.test(cssText), dark: /prefers-color-scheme:\s*dark/.test(cssText),
    themeToggle: !!q('button').find(b => /السمة|theme/i.test(b.textContent)),
    skip: !!q('a[href^="#"]').filter(a => /تخط|skip/i.test(a.textContent))[0], main: !!q('main,[role=main]')[0], navTag: navs.length > 0, header: !!q('header,[role=banner]')[0],
    lang: document.documentElement.lang, dir: document.documentElement.dir, live: q('[aria-live],[role=status],[role=alert]').length,
    sortHdr: sortHdr.length, ariaSort: ariaSort.length, tooltipKb: q('svg [tabindex],svg[tabindex]').length,
    navCurrent: q('nav [aria-current]').length, navLinks: navLinks.length, navIcons: navLinks.filter(a => a.querySelector('svg')).length,
    sidebar, persistent, h2Ids: h2.filter(e => e.id || (e.closest('[id]'))).length, toc: q('a[href^="#"]').length, search: q('input[type=search]').length,
    collaps, nested, maxRows: Math.max(0, ...rows), layoutAnim, emoji, pageMax, longLine, inlineColor, rootVars,
    vpOk: /width=device-width/.test(vpc) && !/user-scalable=no|maximum-scale=1\b/.test(vpc), cls: window.__cls || 0, inViewport,
    dcl: Math.round(performance.timing.domContentLoadedEventEnd - performance.timing.navigationStart),
    navSig: navLinks.map(a => a.getAttribute('href')).join('|'),
  };
}
"""

INIT = "window.__cls=0;new PerformanceObserver(l=>{for(const e of l.getEntries())if(!e.hadRecentInput)window.__cls+=e.value}).observe({type:'layout-shift',buffered:true});"


def collect(label, shots):
    from playwright.sync_api import sync_playwright
    out = {}
    shot_dir = os.path.join(ROOT, "reports", "ux", label)
    if shots:
        os.makedirs(shot_dir, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        for page_name in PAGES:
            out[page_name] = {}
            for vname, (w, h) in VIEWS.items():
                for scheme in ("light", "dark"):
                    ctx = b.new_context(viewport={"width": w, "height": h}, color_scheme=scheme, has_touch=(vname == "mobile"))
                    ctx.add_init_script(INIT)
                    pg = ctx.new_page()
                    t0 = time.time()
                    resp = pg.goto(BASE + page_name, wait_until="load")
                    pg.wait_for_timeout(700)
                    res = pg.evaluate(PROBE)
                    res["bytes"] = len(resp.body()) if resp else 0
                    res["load_ms"] = round((time.time() - t0) * 1000)
                    out[page_name]["%s_%s" % (vname, scheme)] = res
                    if shots:
                        pg.screenshot(path=os.path.join(shot_dir, "%s_%s_%s.png" % (page_name[:-5], vname, scheme)))
                        if vname == "desktop" and scheme == "light":
                            pg.screenshot(path=os.path.join(shot_dir, "%s_full.jpg" % page_name[:-5]), full_page=True, type="jpeg", quality=45)
                    ctx.close()
        b.close()
    return out


def frac(bad, total):
    return 1.0 if not total else max(0.0, 1.0 - bad / total)


def band(x, good, ok, higher_is_better=False):
    """1 إذا ضمن الحدّ الجيد، 0.5 ضمن المقبول، وإلا 0."""
    if higher_is_better:
        return 1.0 if x >= good else 0.5 if x >= ok else 0.0
    return 1.0 if x <= good else 0.5 if x <= ok else 0.0


def score_page(d):
    """درجات الفحوص لصفحة واحدة: {فئة: {معرّف: 0..1}} من قياسات المكتب (فاتح/داكن) والجوال."""
    L, K, M = d["desktop_light"], d["desktop_dark"], d["mobile_light"]
    c = {k: {} for k, _, _ in CATS}
    a = c["accessibility"]
    a["color-contrast"] = min(frac(L["failed"], L["tested"]), frac(K["failed"], K["tested"]))
    a["focus-states"] = 1.0 if L["focusVisible"] else 0.5 if L["focus"] else 0.0
    a["aria-labels"] = frac(L["unnamed"], L["inter"])
    a["form-labels"] = frac(L["unlabeled"], L["fields"])
    a["skip-links"] = 1.0 if L["skip"] else 0.0
    a["heading-hierarchy"] = 1.0 if (L["h1"] == 1 and L["hsk"] == 0) else 0.5 if L["h1"] == 1 else 0.0
    a["reduced-motion"] = 1.0 if L["reduced"] else 0.0
    a["web-target-size"] = frac(L["small24"], L["inter"])
    a["landmarks"] = (int(L["main"]) + int(L["navTag"]) + int(L["header"])) / 3
    a["screen-reader-summary"] = frac(L["svgs"] - L["svgLabeled"], L["svgs"])
    a["lang-dir"] = 1.0 if (L["lang"] and L["dir"] == "rtl") else 0.0
    a["live-status"] = 1.0 if L["live"] else 0.0
    t = c["touch"]
    t["touch-target-size"] = frac(M["small44"], M["inter"])
    t["cursor-pointer"] = frac(L["btns"] - L["ptr"], L["btns"])
    t["touch-spacing"] = 1.0 if M["inter"] <= 80 else 0.5 if M["inter"] <= 160 else 0.0
    p = c["performance"]
    p["page-weight"] = band(L["bytes"], 400_000, 1_000_000)
    p["content-jumping"] = band(L["cls"], 0.1, 0.25)
    p["dom-size"] = band(L["dom"], 1500, 3000)
    p["main-thread"] = band(L["dcl"], 500, 1500)
    p["virtualize-lists"] = band(L["maxRows"], 50, 200)
    s = c["style"]
    s["no-emoji-icons"] = 1.0 if not L["emoji"] else 0.0
    s["dark-mode-pairing"] = (int(L["dark"]) + int(L["themeToggle"])) / 2
    s["semantic-tokens"] = 1.0 if L["rootVars"] >= 12 else 0.5 if L["rootVars"] >= 4 else 0.0
    s["no-inline-colors"] = frac(L["inlineColor"], max(1, L["inlineColor"] + 20))
    y = c["layout"]
    y["horizontal-scroll"] = 1.0 if M["sw"] <= M["cw"] + 1 else 0.0
    y["viewport-meta"] = 1.0 if L["vpOk"] else 0.0
    y["readable-text"] = frac(L["tiny"], L["textChars"])
    y["container-width"] = 1.0 if L["pageMax"] != "none" else 0.0
    y["scroll-depth"] = band(L["h"] / L["vh"], 4, 8)
    y["nested-scroll"] = 1.0 if L["nested"] <= 1 else 0.5 if L["nested"] <= 3 else 0.0
    y["line-length"] = frac(L["longLine"], 60)
    y["cognitive-load"] = band(L["inter"], 40, 90)
    ty = c["typography"]
    ty["number-tabular"] = 1.0 if L["tab"] else 0.0
    ty["font-scale"] = band(L["fontSizes"], 8, 12)
    ty["line-height"] = 1.0 if L["lh"] >= 1.5 else 0.5 if L["lh"] >= 1.3 else 0.0
    ty["body-size"] = 1.0 if L["bodyFs"] >= 16 else 0.5 if L["bodyFs"] >= 14 else 0.0
    an = c["animation"]
    an["transform-performance"] = 1.0 if not L["layoutAnim"] else 0.0
    an["reduced-motion"] = 1.0 if L["reduced"] else 0.0
    f = c["forms"]
    f["input-labels"] = frac(L["unlabeled"], L["fields"])
    f["progressive-disclosure"] = min(1.0, (L["collaps"] / max(1, L["h2"])) / 0.4)
    f["status-feedback"] = 1.0 if L["live"] else 0.0
    n = c["navigation"]
    n["nav-state-active"] = 1.0 if L["navCurrent"] else 0.0
    n["persistent-nav"] = 1.0 if L["persistent"] else 0.0
    n["adaptive-navigation"] = 1.0 if L["sidebar"] else 0.0
    n["deep-linking"] = frac(L["h2"] - L["h2Ids"], L["h2"]) * (1.0 if L["toc"] else 0.5)
    n["nav-label-icon"] = frac(L["navLinks"] - L["navIcons"], L["navLinks"])
    n["search"] = 1.0 if L["search"] else 0.0
    ch = c["charts"]
    ch["chart-summary"] = frac(L["svgs"] - L["svgLabeled"], L["svgs"])
    ch["sortable-aria"] = 1.0 if not L["sortHdr"] else L["ariaSort"] / L["sortHdr"]
    ch["tooltip-keyboard"] = 1.0 if (not L["svgs"] or L["tooltipKb"]) else 0.0
    ch["responsive-chart"] = 1.0 if M["sw"] <= M["cw"] + 1 else 0.0
    return c


def summarize(raw):
    pages, navsig = {}, set()
    for name, d in raw.items():
        c = score_page(d)
        navsig.add(d["desktop_light"]["navSig"])
        cats = {k: round(100 * sum(v.values()) / len(v), 1) for k, v in c.items()}
        total = round(sum(cats[k] * WEIGHT[w] for k, _, w in CATS) / sum(WEIGHT[w] for _, _, w in CATS), 1)
        L = d["desktop_light"]
        pages[name] = dict(total=total, cats=cats, checks={k: {i: round(x, 2) for i, x in v.items()} for k, v in c.items()},
                           metrics=dict(height=L["h"], viewports=round(L["h"] / L["vh"], 1), h2=L["h2"], tables=L["tables"], controls=L["inter"],
                                        buttons=L["btns"], dom=L["dom"], bytes=L["bytes"], rows_max=L["maxRows"], collapsibles=L["collaps"]))
    consistent = len(navsig) == 1
    allp = list(pages.values())
    overall = round(sum(p["total"] for p in allp) / len(allp), 1)
    return dict(overall=overall, nav_consistent=consistent, pages=pages)


def compare(a, b):
    A = json.load(open(os.path.join(ROOT, "docs", "ux_audit", a + ".json"), encoding="utf-8"))["summary"]
    B = json.load(open(os.path.join(ROOT, "docs", "ux_audit", b + ".json"), encoding="utf-8"))["summary"]
    print("الإجمالي %s → %s (%+.1f)" % (A["overall"], B["overall"], B["overall"] - A["overall"]))
    for name in PAGES:
        pa, pb = A["pages"][name], B["pages"][name]
        print("%-14s %5.1f → %5.1f  ارتفاع %6d → %6d  تحكّمات %3d → %3d  جداول %2d → %2d" % (
            name, pa["total"], pb["total"], pa["metrics"]["height"], pb["metrics"]["height"], pa["metrics"]["controls"], pb["metrics"]["controls"],
            pa["metrics"]["tables"], pb["metrics"]["tables"]))
        for k, lab, _ in CATS:
            print("    %-24s %5.1f → %5.1f" % (lab, pa["cats"][k], pb["cats"][k]))


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--label")
    ap.add_argument("--no-shots", action="store_true")
    ap.add_argument("--compare", nargs=2)
    a = ap.parse_args(argv)
    if a.compare:
        compare(*a.compare)
        return 0
    if not a.label:
        ap.error("--label مطلوب")
    raw = collect(a.label, not a.no_shots)
    summ = summarize(raw)
    os.makedirs(os.path.join(ROOT, "docs", "ux_audit"), exist_ok=True)
    with open(os.path.join(ROOT, "docs", "ux_audit", a.label + ".json"), "w", encoding="utf-8") as f:
        json.dump(dict(label=a.label, summary=summ, raw=raw), f, ensure_ascii=False, indent=1)
    print("الإجمالي", summ["overall"], "اتساق التنقّل", summ["nav_consistent"])
    for n, p in summ["pages"].items():
        print("%-14s %5.1f  ارتفاع %6d  تحكّمات %3d  جداول %2d" % (n, p["total"], p["metrics"]["height"], p["metrics"]["controls"], p["metrics"]["tables"]))
        print("   ", {k: v for k, v in p["cats"].items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
