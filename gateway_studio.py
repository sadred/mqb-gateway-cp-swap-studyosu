#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Denizli Garaj MQB Gateway CP & SWaP Stüdyo

Continental VAG MQB J533 (3Q0 907 530) — Renesas RH850/F1L gateway için
bileşen koruması (CP/KSCHUTZ) bağlama, Engineering Mode, RSA-1024 / SWaP (FSC)
imzalama ve dump inceleme aracı.

Yama motoru (mqb_contitool / PerkTheFox) bu programın İÇİNE gömülüdür:
harici .py dosyası gerekmez, program internete bağlanmaz.

Tek dosya, Tkinter, harici Python paketi yok.
"""

from __future__ import annotations

import base64
import importlib.util
import io
import json
import os
import queue
import random
import re
import shutil
import sys
import threading
import traceback
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# ─────────────────────────────────────────────────────────────── kimlik
APP_TITLE = "Denizli Garaj MQB Gateway CP & SWaP Stüdyo"
APP_SHORT = "DG MQB Gateway Stüdyo"
APP_VERSION = "2.3"
APP_SUBTITLE = ("Continental J533 · 3Q0 907 530 AC/AG/AJ/AL/AM/AN/AP/AQ/AR · RH850/F1L · "
                "CP bağlama · Engineering Mode · RSA-1024 / SWaP")
SOURCE_PROJECT = "mqb_contitool / PerkTheFox — https://github.com/perkthefox/mqb_contitool"
CREDIT_LINE = ("Kaynak: mqb_contitool — PerkTheFox  ·  github.com/perkthefox/mqb_contitool"
               "  ·  Denizli Garaj")

HERE = Path(__file__).resolve().parent
FROZEN = bool(getattr(sys, "frozen", False))
ASSET_DIR = Path(getattr(sys, "_MEIPASS", HERE)) / "assets"
APP_DIR = Path(sys.executable).resolve().parent if FROZEN else HERE
ENGINE_BUNDLED = ASSET_DIR.parent / "motor"
ENGINE_FILE = "conti_cp_tool.py"
CFG_PATH = APP_DIR / "studyo_ayarlar.json"
# Pakete gömülü anahtar (RSA-1024, e=3) — kullanıcı anahtar üretmez/seçmez
KEY_BUNDLED = ASSET_DIR / "anahtar" / "swap_rsa1024.json"


def bundled_key() -> Path | None:
    """Paketle gelen anahtarın yolunu döndürür (exe içinde: _MEIPASS/assets/anahtar)."""
    for c in (KEY_BUNDLED, HERE / "assets" / "anahtar" / "swap_rsa1024.json",
              APP_DIR / "anahtar" / "swap_rsa1024.json"):
        if c.is_file():
            return c
    return None


def bundled_modulus() -> str:
    """Gömülü anahtarın modulus N'sini kısa hex olarak döndürür."""
    p = bundled_key()
    if p is None:
        return "—"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        n = data.get("n_hex", "")
        return n[:24] + "…" if n else "—"
    except (OSError, ValueError):
        return "—"

CFLASH_SIZES = {1_523_200, 1_572_864}
DFLASH_SIZE = 65_536
UFLASH_SIZE = 32_768

_ENGINE = None
_ENGINE_ERROR = ""


# ─────────────────────────────────────────────────────── motor yükleme
def engine_source() -> Path | None:
    """Gömülü motorun klasörünü döndürür (exe içinde: _MEIPASS/motor)."""
    cands = [ENGINE_BUNDLED, HERE / "motor", HERE, APP_DIR / "motor"]
    for c in cands:
        if (c / ENGINE_FILE).is_file():
            return c
    return None


def get_engine():
    """Motoru modül olarak yükler (tek sefer)."""
    global _ENGINE, _ENGINE_ERROR
    if _ENGINE is not None:
        return _ENGINE
    src = engine_source()
    if src is None:
        _ENGINE_ERROR = f"motor bulunamadı (aranan: {ENGINE_BUNDLED})"
        return None
    try:
        spec = importlib.util.spec_from_file_location("conti_engine", src / ENGINE_FILE)
        if spec is None or spec.loader is None:
            _ENGINE_ERROR = "motor yüklenemedi (spec hatası)"
            return None
        mod = importlib.util.module_from_spec(spec)
        sys.modules["conti_engine"] = mod      # dataclass'lar için şart
        old_argv = sys.argv
        sys.argv = ["conti_engine"]
        try:
            spec.loader.exec_module(mod)
        finally:
            sys.argv = old_argv
        try:
            mod.set_lang("en")
        except Exception:  # noqa: BLE001
            pass
    except Exception:  # noqa: BLE001
        _ENGINE_ERROR = traceback.format_exc(limit=4)
        return None
    _ENGINE = mod
    _ENGINE_ERROR = ""
    return _ENGINE


def engine_ready() -> bool:
    return get_engine() is not None


def run_engine(tokens: list[str], timeout: int | None = None) -> tuple[int, str]:
    """Motorun kendi argparse'ı ile komut çalıştırır, çıktıyı metin olarak döndürür."""
    eng = get_engine()
    if eng is None:
        return 2, f"✘ yama motoru yüklenemedi: {_ENGINE_ERROR}"
    parser = eng.build_arg_parser()
    argv = ["-l", "en", "--no-color"] + list(tokens)
    try:
        ns = parser.parse_args(argv)
    except SystemExit as exc:              # argparse hatası
        return int(exc.code or 2), "parametre hatası (argparse)"
    if getattr(ns, "func", None) is None:
        return 2, "komut seçilmedi"
    buf = io.StringIO()
    try:
        with redirect_stdout(buf), redirect_stderr(buf):
            rc = ns.func(ns) or 0
    except SystemExit as exc:
        rc = int(exc.code or 0)
    except Exception as exc:  # noqa: BLE001
        buf.write(f"\n✘ SEBEP: {exc}\n")
        buf.write(traceback.format_exc(limit=6))
        rc = 1
    return rc, buf.getvalue()


# ────────────────────────────────────────────────── dump analiz yardımcıları
def is_cflash(p: Path) -> bool:
    n = p.name.lower()
    if p.stat().st_size in CFLASH_SIZES:
        return True
    return any(k in n for k in ("cflash", "codeflash", "fd_0data", "fd0data"))


def is_dflash(p: Path) -> bool:
    n = p.name.lower()
    if p.stat().st_size == DFLASH_SIZE:
        return True
    return any(k in n for k in ("dflash", "dataflash"))


def is_uflash(p: Path) -> bool:
    n = p.name.lower()
    if p.stat().st_size == UFLASH_SIZE:
        return True
    return "uflash" in n


def scan_dumps(roots: list[Path]) -> dict[str, Path | None]:
    """Klasörlerde CodeFlash/DataFlash/Uflash arar (isim + boyut doğrulaması)."""
    found: dict[str, Path | None] = {"cflash": None, "dflash": None, "uflash": None}
    seen: set[Path] = set()
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        pats = ["*.bin", "*.BIN", "*.raw", "*.RAW", "*.bin.*"]
        files: list[Path] = []
        if root.is_file():
            files = [root]
        else:
            for pat in pats:
                files += list(root.glob(pat))
            files += list(root.glob(f"*/{pats[0]}"))
        for f in files:
            if f in seen or not f.is_file():
                continue
            seen.add(f)
            try:
                sz = f.stat().st_size
            except OSError:
                continue
            if sz not in CFLASH_SIZES | {DFLASH_SIZE, UFLASH_SIZE}:
                continue
            key = None
            if sz in CFLASH_SIZES or is_cflash(f):
                key = "cflash"
            if sz == DFLASH_SIZE or ("dflash" in f.name.lower() or "dataflash" in f.name.lower()):
                key = "dflash"
            if sz == UFLASH_SIZE or "uflash" in f.name.lower():
                key = "uflash"
            if key and found[key] is None:
                found[key] = f
    return found


def fmt_size(n: int) -> str:
    return f"{n:,} B".replace(",", ".")


def random_ika() -> str:
    return os.urandom(16).hex().upper()


# ────────────────────────────────────────────────────────────── tooltip
class Tooltip:
    """Fare ile üzerine gelince Türkçe açıklama gösteren balon."""

    def __init__(self, widget: tk.Widget, text: str, delay: int = 350):
        self.widget = widget
        self.text = text
        self.delay = delay
        self._after: str | None = None
        self._tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _evt=None) -> None:
        self._after = self.widget.after(self.delay, self._show)

    def _show(self) -> None:
        if self._tip or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 18
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        except tk.TclError:
            return
        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        tip.wm_geometry(f"+{x}+{y}")
        frame = tk.Frame(tip, background="#2d333b", borderwidth=1, relief="solid")
        frame.pack()
        tk.Label(frame, text=self.text, justify="left", background="#2d333b",
                 foreground="#e6edf3", font=("Segoe UI", 8), wraplength=460,
                 padx=8, pady=5).pack()
        self._tip = tip

    def _hide(self, _evt=None) -> None:
        if self._after:
            try:
                self.widget.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None
        if self._tip:
            self._tip.destroy()
            self._tip = None


def tip(widget: tk.Widget, text: str) -> tk.Widget:
    Tooltip(widget, text)
    return widget


# ──────────────────────────────────────────────────────────────── ana UI
class Studio(tk.Frame):
    def __init__(self, master: tk.Tk):
        super().__init__(master, padx=10, pady=8)
        self.master: tk.Tk = master
        self.cfg = self._load_cfg()
        self.queue: queue.Queue = queue.Queue()
        self.busy = False
        self.slots = []
        self.bank_vars: dict[int, tk.BooleanVar] = {}
        self.f_cflash = tk.StringVar()
        self.f_dflash = tk.StringVar()
        self.f_uflash = tk.StringVar()
        self.v_out = tk.StringVar(value=self.cfg.get("out", str(APP_DIR / "cikti")))
        self.v_status = tk.StringVar(value="Hazır.")
        self.eng_vars: dict[str, tk.Variable] = {}

        self.pack(fill="both", expand=True)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self._build_header()
        self._build_tabs()
        self._build_footer()

        for _v in (self.v_out, self.v_vin, self.v_vcrn, self.v_fec):
            _v.trace_add("write", lambda *_: self._save_cfg())

        self.after(120, self._pump)
        self.after(200, self._startup_scan)

    # ── yapılandırma
    def _load_cfg(self) -> dict:
        try:
            return json.loads(CFG_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_cfg(self) -> None:
        data = {"out": self.v_out.get(), "vin": self.v_vin.get(),
                "vcrn": self.v_vcrn.get(), "fec_extra": self.v_fec.get()}
        try:
            CFG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError:
            pass

    # ── başlık
    def _build_header(self) -> None:
        head = ttk.Frame(self)
        head.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        head.columnconfigure(1, weight=1)
        self._logo = None
        logo_png = ASSET_DIR / "logo.png"
        if logo_png.is_file():
            try:
                self._logo = tk.PhotoImage(file=str(logo_png))
                ttk.Label(head, image=self._logo).grid(row=0, column=0, rowspan=2,
                                                      sticky="w", padx=(0, 10))
            except tk.TclError:
                self._logo = None
        ttk.Label(head, text=APP_TITLE, font=("Segoe UI", 13, "bold"),
                  foreground="#3f5c3f").grid(row=0, column=1, sticky="w")
        ttk.Label(head, text=APP_SUBTITLE, foreground="#6b6b6b").grid(row=1, column=1, sticky="w")
        about = ttk.Button(head, text="Hakkında / Kaynak", command=self._about)
        about.grid(row=0, column=2, rowspan=2, sticky="e")
        tip(about, "Program, kaynak atıfı, lisans ve uyarılar hakkında bilgi verir.\n"
                   "Yama motoru (mqb_contitool) exe içine gömülüdür; internet gerekmez.")

    # ── sekmeler
    def _build_tabs(self) -> None:
        nb = ttk.Notebook(self)
        nb.grid(row=1, column=0, sticky="nsew")
        self.nb = nb
        self.tab_inspect = ttk.Frame(nb, padding=8)
        self.tab_cp = ttk.Frame(nb, padding=8)
        self.tab_eng = ttk.Frame(nb, padding=8)
        self.tab_rsa = ttk.Frame(nb, padding=8)
        self.tab_ref = ttk.Frame(nb, padding=8)
        nb.add(self.tab_inspect, text=" 1 · Dump İncele ")
        nb.add(self.tab_cp, text=" 2 · CP Bağla ")
        nb.add(self.tab_eng, text=" 3 · Engineering Mode ")
        nb.add(self.tab_rsa, text=" 4 · RSA & SWaP ")
        nb.add(self.tab_ref, text=" 5 · Referans ")
        self._build_inspect()
        self._build_cp()
        self._build_eng()
        self._build_rsa()
        self._build_ref()

    # ── dosya seçim satırı
    def _file_row(self, parent, row: int, label: str, var: tk.StringVar,
                  hint: str, kind: str) -> None:
        ttk.Label(parent, text=label, width=14).grid(row=row, column=0, sticky="w", pady=2)
        e = ttk.Entry(parent, textvariable=var)
        e.grid(row=row, column=1, sticky="ew", padx=(4, 4), pady=2)
        tip(e, hint)
        b = ttk.Button(parent, text="Seç...", width=8,
                       command=lambda: self._pick(var, kind))
        b.grid(row=row, column=2, sticky="w", pady=2)
        tip(b, hint + "\n\nDosyayı elle seçmek için kullan.")

    def _pick(self, var: tk.StringVar, kind: str) -> None:
        patterns = {
            "cflash": [("CodeFlash dump", "*.bin *.raw *.BIN"), ("Tüm dosyalar", "*.*")],
            "dflash": [("DataFlash dump", "*.bin *.BIN"), ("Tüm dosyalar", "*.*")],
            "uflash": [("Uflash dump", "*.bin *.BIN"), ("Tüm dosyalar", "*.*")],
            "key": [("RSA anahtarı", "*.json *.pem *.bin"), ("Tüm dosyalar", "*.*")],
            "any": [("Tüm dosyalar", "*.*")],
        }[kind]
        p = filedialog.askopenfilename(title="Dosya seç", filetypes=patterns,
                                      initialdir=str(APP_DIR))
        if p:
            var.set(p)

    def _make_scrollable(self, parent: tk.Widget) -> ttk.Frame:
        """Uzun sekmeler için dikey kaydırmalı iç çerçeve döndürür."""
        canvas = tk.Canvas(parent, highlightthickness=0, borderwidth=0)
        vsb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        def _fit(event):
            canvas.itemconfigure(win, width=event.width)
            canvas.configure(scrollregion=canvas.bbox("all"))

        canvas.bind("<Configure>", _fit)
        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        state = {"on": False}
        canvas.bind("<Enter>", lambda _e: state.__setitem__("on", True), add="+")
        canvas.bind("<Leave>", lambda _e: state.__setitem__("on", False), add="+")

        def _wheel(event):
            if state["on"]:
                canvas.yview_scroll(int(-event.delta / 120), "units")

        canvas.bind_all("<MouseWheel>", _wheel, add="+")
        return inner

    # ══════════════════════════════ 1 · DUMP İNCELE
    def _build_inspect(self) -> None:
        f = self.tab_inspect
        f.columnconfigure(0, weight=1)
        f.rowconfigure(4, weight=1)

        box = ttk.LabelFrame(f, text=" Dump dosyaları ", padding=8)
        box.grid(row=0, column=0, sticky="ew")
        box.columnconfigure(1, weight=1)
        self._file_row(box, 0, "CodeFlash.bin", self.f_cflash,
                       "Gateway'in CodeFlash (1.5 MB) dump'ı. Uygulama kodu + RSA modulus + "
                       "CP kancaları burada. Bench programmer (voltage glitch) ile okunur.", "cflash")
        self._file_row(box, 1, "DataFlash.bin", self.f_dflash,
                       "Gateway'in DataFlash (64 KB) dump'ı. 12 CP bankası, master anahtar (GFA), "
                       "VCRN ve SWaP sertifika slotları burada.", "dflash")
        self._file_row(box, 2, "Uflash.bin", self.f_uflash,
                       "Uflash (32 KB) bootloader dump'ı. Engineering Mode (imzasız OBD yazma) için gerekir. "
                       "İsteğe bağlı.", "uflash")

        row = ttk.Frame(f)
        row.grid(row=1, column=0, sticky="ew", pady=(8, 4))
        for i in range(3):
            row.columnconfigure(i, weight=1)
        b_scan = ttk.Button(row, text="Otomatik tara", command=self._scan)
        b_scan.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        tip(b_scan, "Seçili çıktı klasöründe, program klasöründe ve Masaüstü'nde "
                    "CodeFlash/DataFlash/Uflash dump'larını isim ve boyuta göre arar.")
        b_ins = ttk.Button(row, text="İncele", command=self._do_inspect)
        b_ins.grid(row=0, column=1, sticky="ew", padx=4)
        tip(b_ins, "Dump'ları SALT OKUNUR analiz eder: CodeFlash (CRC, CP kancası, engineering gate, "
                   "RSA modulus), DataFlash (12 CP bankası, SWaP slotları, VCRN) ve Uflash (imza). "
                   "Hiçbir şey yazmaz, hiçbir dosyayı değiştirmez.")
        b_rep = ttk.Button(row, text="Ham rapor", command=self._do_report)
        b_rep.grid(row=0, column=2, sticky="ew", padx=(4, 0))
        tip(b_rep, "Motorun kendi ayrıntılı metin raporunu günlüğe basar "
                   "(teknik alan adlarıyla, ileri düzey inceleme için).")

        # CP banka tablosu
        cols = ("no", "ecu", "modul", "nvm", "off", "durum", "anahtar")
        self.tree = ttk.Treeview(f, columns=cols, show="headings", height=13)
        heads = {"no": ("#", 40), "ecu": ("ECU", 60), "modul": ("Modül", 300),
                 "nvm": ("NvM", 60), "off": ("DataFlash", 90),
                 "durum": ("Durum", 110), "anahtar": ("Anahtar (ilk 16 bayt)", 260)}
        for c in cols:
            t, w = heads[c]
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w")
        self.tree.grid(row=4, column=0, sticky="nsew", pady=(6, 0))
        tip(self.tree, "12 CP bankasının durumu: BOŞ = fabrika boş (FF..FF), "
                       "DOLU = içinde anahtar var (SHE şifreli veya düz IKA).")
        sb = ttk.Scrollbar(f, orient="vertical", command=self.tree.yview)
        sb.grid(row=4, column=1, sticky="ns", pady=(6, 0))
        self.tree.configure(yscrollcommand=sb.set)

        self.lbl_sum = ttk.Label(f, text="", foreground="#6b6b6b", justify="left")
        self.lbl_sum.grid(row=5, column=0, columnspan=2, sticky="w", pady=(6, 0))

    # ══════════════════════════════ 2 · CP BAĞLA
    def _build_cp(self) -> None:
        f = self.tab_cp
        f.columnconfigure(0, weight=1)

        info = ttk.Label(f, foreground="#6b6b6b", justify="left", wraplength=980,
                         text="Kullanılmış / sonradan takılan bir ECU'yu (MIB2 5F, gösterge 17, ACC 13, "
                              "kamera A5, amfi 47 …) gateway'e bağlar: CodeFlash'a hibrit KSCHUTZ kancası "
                              "kurulur, DataFlash'taki seçili bankaya 16 baytlık düz IKA anahtarı yazılır. "
                              "Fabrika ECU'ları SHE modunda çalışmaya devam eder.")
        info.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        box = ttk.LabelFrame(f, text=" Girdi / Çıktı (dump'lar 1. sekmeden alınır) ", padding=8)
        box.grid(row=1, column=0, sticky="ew")
        box.columnconfigure(1, weight=1)
        ttk.Label(box, text="CodeFlash", width=14).grid(row=0, column=0, sticky="w")
        e1 = ttk.Label(box, textvariable=self.f_cflash, foreground="#3f5c3f")
        e1.grid(row=0, column=1, sticky="w")
        ttk.Label(box, text="DataFlash", width=14).grid(row=1, column=0, sticky="w")
        e2 = ttk.Label(box, textvariable=self.f_dflash, foreground="#3f5c3f")
        e2.grid(row=1, column=1, sticky="w")
        ttk.Label(box, text="Çıktı klasörü", width=14).grid(row=2, column=0, sticky="w")
        o = ttk.Entry(box, textvariable=self.v_out)
        o.grid(row=2, column=1, sticky="ew", padx=(0, 4))
        tip(o, "Yamalı dosyaların yazılacağı klasör: CodeFlash.patched.bin + DataFlash.patched.bin")
        bo = ttk.Button(box, text="Seç", width=6,
                        command=lambda: self._pick_dir(self.v_out))
        bo.grid(row=2, column=2, sticky="w")

        banks = ttk.LabelFrame(f, text=" Hangi bankaya yazılacak? ", padding=8)
        banks.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        for i in range(4):
            banks.columnconfigure(i, weight=1)
        eng = get_engine()
        try:
            self.slots = [eng.parse_slot_selector(str(n)) for n in range(1, 13)] if eng else []
        except Exception:  # noqa: BLE001
            self.slots = []
        for idx, spec in enumerate(self.slots):
            n = spec.slot
            var = tk.BooleanVar(value=False)
            self.bank_vars[n] = var
            label = f"#{n} · {spec.ecu_addr} {spec.short_en}"
            cb = ttk.Checkbutton(banks, text=label, variable=var)
            cb.grid(row=idx // 3, column=idx % 3, sticky="w", pady=1)
            tip(cb, f"{spec.details_en}\n\n"
                    f"DataFlash offset: {spec.off1} (mirror {spec.off2}) · NvM {spec.nvm_id}\n"
                    f"UDS: {spec.uds_req}/{spec.uds_resp} · 95640 maske biti: {spec.mask_bit}")
        rowb = ttk.Frame(banks)
        rowb.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(6, 0))
        ba = ttk.Button(rowb, text="Tümünü seç", command=lambda: self._all_banks(True))
        ba.pack(side="left")
        tip(ba, "12 bankanın tamamını işaretler (dikkat: her bankaya aynı anahtar yazılır).")
        bn = ttk.Button(rowb, text="Temizle", command=lambda: self._all_banks(False))
        bn.pack(side="left", padx=4)
        tip(bn, "Banka seçimlerini kaldırır.")

        keybox = ttk.LabelFrame(f, text=" IKA anahtarı (16 bayt / 32 hex) ", padding=8)
        keybox.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        keybox.columnconfigure(1, weight=1)
        self.v_key = tk.StringVar()
        ke = ttk.Entry(keybox, textvariable=self.v_key, font=("Consolas", 10))
        ke.grid(row=0, column=0, columnspan=2, sticky="ew")
        tip(ke, "Hedef ECU'nun kendi dump'ından çıkarılan 16 baytlık düz IKA (K3) anahtarı — 32 hex karakter.\n"
                "Bu anahtar araç üzerinden (CAN/UDS) OKUNAMAZ; yalnız hedef modülün hafızasından alınır.")
        br = ttk.Button(keybox, text="Rastgele üret", command=self._rand_key)
        br.grid(row=0, column=2, sticky="w", padx=(6, 0))
        tip(br, "Kriptografik rastgele 16 bayt anahtar üretir. Yalnız hedef ECU'ya da aynı anahtarı "
                "yazabiliyorsan kullan (aksi halde CP açılmaz).")

        opt = ttk.Frame(f)
        opt.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        self.v_bypass = tk.BooleanVar(value=True)
        cb1 = ttk.Checkbutton(opt, text="95640 EEPROM maske atlaması (boş bankaya retrofit)",
                              variable=self.v_bypass)
        cb1.pack(side="left")
        tip(cb1, "Gateway kartındaki harici ST M95640 SPI EEPROM'da 'öğrenilmiş banka' bit maskesini "
                 "atlar. Daha önce hiç kullanılmamış (FF..FF) bir bankaya yeni modül bağlarken gerekir — "
                 "EEPROM'u sökmeden yapılır.")
        self.v_global = tk.BooleanVar(value=False)
        cb2 = ttk.Checkbutton(opt, text="Global plain modu (uzman)", variable=self.v_global)
        cb2.pack(side="left", padx=(14, 0))
        tip(cb2, "Tüm bankalar için SHE 0x40 yerine düz 0x10 modunu kullanır. Araçtaki fabrika ECU'lar "
                 "bu modda çalışmaz — sadece tamamen düz anahtar kullanan bench kurulumlarında kullan.")
        self.v_ignore = tk.BooleanVar(value=False)
        cb3 = ttk.Checkbutton(opt, text="Girdi CRC hatasını yok say", variable=self.v_ignore)
        cb3.pack(side="left", padx=(14, 0))
        tip(cb3, "CodeFlash'taki App CRC-16 (@0x0000C21C) uyuşmasa da devam eder. Sadece dump'ın "
                 "kısmen bozuk olduğunu biliyorsan kullan; sonuç gateway'i brick edebilir.")

        act = ttk.Frame(f)
        act.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        self.b_cp = ttk.Button(act, text="CP bağla (CodeFlash + DataFlash yamala)", command=self._do_cp)
        self.b_cp.pack(side="left")
        tip(self.b_cp, "İki dosya üretir: CodeFlash.patched.bin (hibrit KSCHUTZ kancası + CRC) ve "
                       "DataFlash.patched.bin (seçili bankalara düz IKA anahtarı).\n"
                       "Sonuç otomatik olarak yeniden analiz edilip doğrulanır. Cihaza yazmaz — dosyaları "
                       "bench programmer ile sen yazarsın.")
        bclr = ttk.Button(act, text="Seçili bankaları boşalt (fabrika FF)", command=self._do_clear)
        bclr.pack(side="left", padx=8)
        tip(bclr, "DataFlash.patched.bin içinde seçili bankaları fabrika boş durumuna (FF..FF) döndürür. "
                  "Modül söküldüğünde/CP kaydı temizlenirken kullanılır.")

    # ══════════════════════════════ 3 · ENGINEERING MODE
    def _build_eng(self) -> None:
        f = self.tab_eng
        f.columnconfigure(0, weight=1)
        info = ttk.Label(f, foreground="#6b6b6b", justify="left", wraplength=980,
                         text="Gateway'i 'Engineering Unit'e çevirir: Uflash bootloader'a RSA kontrolünü "
                              "atlayan yama yazılır (OBD'den imzasız .odx yüklenebilir), CodeFlash'ta "
                              "ASAM CCP erişimi ve CAN RAM-Loader kilidi açılır.")
        info.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        box = ttk.LabelFrame(f, text=" Girdi / Çıktı ", padding=8)
        box.grid(row=1, column=0, sticky="ew")
        box.columnconfigure(1, weight=1)
        ttk.Label(box, text="CodeFlash (girdi)").grid(row=0, column=0, sticky="w", pady=2)
        ttk.Label(box, textvariable=self.f_cflash, foreground="#3f5c3f").grid(row=0, column=1, sticky="w")
        ttk.Label(box, text="Uflash (girdi)").grid(row=1, column=0, sticky="w", pady=2)
        ttk.Label(box, textvariable=self.f_uflash, foreground="#3f5c3f").grid(row=1, column=1, sticky="w")
        ttk.Label(box, text="Çıktı klasörü").grid(row=2, column=0, sticky="w", pady=2)
        e = ttk.Entry(box, textvariable=self.v_out)
        e.grid(row=2, column=1, sticky="ew", padx=(0, 4))
        b = ttk.Button(box, text="Seç", width=6, command=lambda: self._pick_dir(self.v_out))
        b.grid(row=2, column=2, sticky="w")
        tip(e, "CodeFlash.eng.bin ve Uflash.eng.bin bu klasöre yazılır.")

        opt = ttk.Frame(f)
        opt.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        self.v_eng_restore = tk.BooleanVar(value=False)
        cb = ttk.Checkbutton(opt, text="Fabrika kilitlerini geri yükle (restore stock)",
                             variable=self.v_eng_restore)
        cb.pack(side="left")
        tip(cb, "Engineering yamalarını geri alır, fabrika üretim kilitlerini (RSA kontrolü, CCP "
                "blacklist, OTP kilidi) yeniden kurar. Aracı servise/orijinal haline döndürürken kullan.")
        self.v_eng_ignore = tk.BooleanVar(value=False)
        cb2 = ttk.Checkbutton(opt, text="Girdi CRC hatasını yok say", variable=self.v_eng_ignore)
        cb2.pack(side="left", padx=(14, 0))
        tip(cb2, "CodeFlash App CRC-16 uyuşmazsa bile devam eder.")

        act = ttk.Frame(f)
        act.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        self.b_eng = ttk.Button(act, text="Engineering Mode uygula", command=self._do_eng)
        self.b_eng.pack(side="left")
        tip(self.b_eng, "CodeFlash'a CCP erişim + RAM-Loader yamasını, Uflash'a RSA-free FBL yamasını "
                        "uygular. Uflash yoksa yalnız CodeFlash yamalanır. Cihaza yazmaz, dosya üretir.")

    # ══════════════════════════════ 4 · RSA & SWaP
    def _build_rsa(self) -> None:
        f = self._make_scrollable(self.tab_rsa)
        f.columnconfigure(0, weight=1)
        f.columnconfigure(1, weight=1)

        # paket public key — adım değil, sadece bilgi satırı
        kb = ttk.Frame(f)
        kb.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        kb.columnconfigure(1, weight=1)
        has_key = bundled_key() is not None
        ttk.Label(kb, text="Public key (pakette):", foreground="#6b6b6b").grid(row=0, column=0, sticky="w")
        self.lbl_key = ttk.Label(
            kb, font=("Consolas", 9), foreground="#1f8f3d" if has_key else "#b3261e",
            text=f"N = {bundled_modulus()} · e = 3" if has_key else "bulunamadı")
        self.lbl_key.grid(row=0, column=1, sticky="w", padx=(6, 6))
        bkc = ttk.Button(kb, text="Kopyala", width=8, command=self._copy_pubkey)
        bkc.grid(row=0, column=2, sticky="e")
        tip(bkc, "Gateway'e yazılan açık anahtarın (128 bayt modulus, e=3) tam hex değerini panoya kopyalar.\n"
                 "4.1'de bu anahtar firmware'e gömülür, 4.2'de sertifikalar bu anahtarın özel kısmıyla imzalanır.")

        # 4.1 modulus gömme
        m = ttk.LabelFrame(f, text=" 4.1 · Açık anahtarı gateway'e göm (SWaP / FBL modulus) ",
                           padding=8)
        m.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 0))
        m.columnconfigure(1, weight=1)
        row = ttk.Frame(m)
        row.grid(row=0, column=0, columnspan=3, sticky="ew")
        ttk.Label(row, text="Hedef:").pack(side="left")
        self.v_target = tk.StringVar(value="swap")
        for val, txt, hint in (
            ("swap", "SWaP", "SWaP/FeC sertifika doğrulamasında kullanılan açık anahtarı değiştirir "
                             "(CodeFlash + DataFlash NvM 0x7C önbelleği)."),
            ("fbl", "FBL", "Flash bootloader'ın firmware imza kontrolünde kullandığı açık anahtarı "
                           "değiştirir (.odx imzaları sende olur)."),
            ("both", "İkisi", "Hem SWaP hem FBL açık anahtarını değiştirir."),
        ):
            rb = ttk.Radiobutton(row, text=txt, value=val, variable=self.v_target)
            rb.pack(side="left", padx=(10, 0))
            tip(rb, hint)
        self.v_rsa_ignore = tk.BooleanVar(value=False)
        cb_rsa = ttk.Checkbutton(m, text="Girdi CRC hatasını yok say", variable=self.v_rsa_ignore)
        cb_rsa.grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))
        tip(cb_rsa, "CodeFlash'taki App CRC-16 (@0x0000C21C) uyuşmazsa bile devam eder ve CRC aralık "
                    "sayacını onarır. Dump kısmen bozuksa gerekebilir; sonucu cihaza yazmadan önce doğrula.")
        bm = ttk.Button(m, text="Modulus'u göm", command=self._do_setkey)
        bm.grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))
        tip(bm, "Açık anahtarı CodeFlash'a ve DataFlash SWaP önbelleğine yazar (CRC-32 yeniden hesaplanır, "
                "VCRN korunur). Çıktı: CodeFlash.swap.bin + DataFlash.swap.bin.")
        self.lbl_42 = ttk.Label(m, text="CodeFlash dump'ı yeterli · DataFlash da verilirse araçtaki FSC "
                                        "önbelleği de güncellenir",
                                foreground="#8b949e")
        self.lbl_42.grid(row=4, column=0, columnspan=3, sticky="w", pady=(4, 0))

        # 4.2 SWaP seçimi + FSC (şase + VCRN kullanıcıdan)
        s = ttk.LabelFrame(f, text=" 4.2 · SWaP seç ve FSC oluştur (şase + VCRN) ", padding=8)
        s.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(8, 0))
        s.columnconfigure(1, weight=1)

        ttk.Label(s, text="Şase (VIN)").grid(row=0, column=0, sticky="w")
        self.v_vin = tk.StringVar(value=str(self.cfg.get("vin", "")))
        ev = ttk.Entry(s, textvariable=self.v_vin, width=22)
        ev.grid(row=0, column=1, sticky="w", padx=4)
        tip(ev, "17 karakterlik şasi numarası (örn. VSSZZZ5FZGR239596). Sertifikaya gömülür; "
                "boş bırakılırsa 'joker' (VIN'siz) sertifika üretilir.")
        self.v_novin = tk.BooleanVar(value=False)
        cbv = ttk.Checkbutton(s, text="VIN'siz (joker)", variable=self.v_novin)
        cbv.grid(row=0, column=2, sticky="w")
        tip(cbv, "Sertifikadaki VIN alanını sıfırlar; sertifika VIN kontrolü olmadan geçerli olur.")

        ttk.Label(s, text="VCRN").grid(row=1, column=0, sticky="w")
        self.v_vcrn = tk.StringVar(value=str(self.cfg.get("vcrn", "")))
        evc = ttk.Entry(s, textvariable=self.v_vcrn, width=22)
        evc.grid(row=1, column=1, sticky="w", padx=4)
        tip(evc, "Gateway'in 5 baytlık VCRN'i = 10 hex karakter (örn. 0102030405).\n"
                 "DID 0x3C03 ile okunur; sertifika yalnız bu VCRN'e sahip araçta geçerli olur.")
        bv = ttk.Button(s, text="DataFlash'tan oku", command=self._read_vcrn)
        bv.grid(row=1, column=2, sticky="w")
        tip(bv, "DataFlash dump'ı seçiliyse VCRN'i SWaP önbelleğinden (0xDC0C) okur.")

        # --- SWaP (FeC) seçimi
        ttk.Label(s, text="SWaP seçimi", font=("Segoe UI", 9, "bold")).grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(8, 2))
        grid = ttk.Frame(s)
        grid.grid(row=3, column=0, columnspan=3, sticky="ew")
        self.fec_vars: dict[str, tk.BooleanVar] = {}
        eng0 = get_engine()
        table = getattr(eng0, "KNOWN_GATEWAY_FECS", {}) if eng0 else {}
        names_tr = {
            "10000100": "Sürüş profili seçimi (FPA)",
            "10000200": "Genişletilmiş FPA",
            "10000300": "Sürücü uyarı / yorgunluk (MKE)",
            "10001100": "Enerji yönetimi / rejenerasyon",
            "10001800": "Çoklu çarpışma freni (MKB)",
        }
        for i, code in enumerate(sorted(table)):
            hx = f"{code:08x}"
            var = tk.BooleanVar(value=False)
            self.fec_vars[hx] = var
            label = names_tr.get(hx, f"Gateway SWaP {hx[-4:].upper()}")
            cb = ttk.Checkbutton(grid, text=f"{hx} · {label}", variable=var)
            cb.grid(row=i // 3, column=i % 3, sticky="w", padx=(0, 14), pady=1)
            tip(cb, f"FeC 0x{code:08X} — {table[code][1]}\nİşaretlersen bu kod için ayrı .fsc dosyası üretilir.")
        # özel kod
        ttk.Label(s, text="Özel kod(lar)").grid(row=4, column=0, sticky="w", pady=(6, 0))
        self.v_fec = tk.StringVar(value=str(self.cfg.get("fec_extra", "")))
        ef = ttk.Entry(s, textvariable=self.v_fec, width=30)
        ef.grid(row=4, column=1, sticky="w", padx=4, pady=(6, 0))
        tip(ef, "Listede olmayan FeC kodları: 8 hex, virgül/boşlukla ayır (örn. 10001600, 10001700).\n"
                "Buraya yazılanlar işaretli kodlarla birlikte imzalanır.")

        bfs = ttk.Button(s, text="Seçilen SWaP'lar için FSC oluştur", command=self._do_fsc)
        bfs.grid(row=5, column=0, sticky="w", pady=(10, 0))
        bad = ttk.Button(s, text="Transfer SWaP değeri (adaptasyon)", command=self._show_adapt_values)
        bad.grid(row=5, column=1, columnspan=2, sticky="w", padx=(8, 0), pady=(10, 0))
        tip(bad, "Adaptasyon > 'Transfer SWaP function' alanına yapıştırılacak UZUN değeri üretir.\n"
                 "Her FeC için DEC (10'luk tamsayı), HEX ve Base64 biçimlerini gösterir + .txt yazar.\n"
                 "Alan decimal kabul etmiyorsa HEX'i dene.")
        tip(bfs, "İşaretlediğin her SWaP kodu için 171 baytlık SWaP/FeC sertifikası üretir "
                 "(RIPEMD-160 + RSA-1024 e=3, paket anahtarıyla).\n"
                 "Çıktı: fsc_<kod>.fsc — OBD'den 2E 3C 01 + 31 01 C0 01 ile yüklenir.")
        self.lbl_43 = ttk.Label(s, text="şase + VCRN + en az bir SWaP kodu seç",
                                foreground="#8b949e")
        self.lbl_43.grid(row=6, column=0, columnspan=3, sticky="w", pady=(4, 0))

        # 4.3 firmware imzası
        o = ttk.LabelFrame(f, text=" 4.3 · Firmware (.odx) imzala — <FW-SIGNATURE> ", padding=8)
        o.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        o.columnconfigure(1, weight=1)
        self.v_odxin = tk.StringVar()
        ttk.Label(o, text="Firmware").grid(row=0, column=0, sticky="w")
        eo = ttk.Entry(o, textvariable=self.v_odxin)
        eo.grid(row=0, column=1, sticky="ew", padx=4)
        tip(eo, "İmzalanacak CodeFlash.bin veya FD_0DATA (1.523.200 B) dosyası. 0. sekmedeki CodeFlash "
                "kullanılacaksa boş bırak.")
        bo = ttk.Button(o, text="Seç...", width=8, command=lambda: self._pick(self.v_odxin, "cflash"))
        bo.grid(row=0, column=2)
        bod = ttk.Button(o, text="İmzala", command=self._do_signodx)
        bod.grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))
        tip(bod, "SHA-1 + RSA-1024 (e=3) ile 128 baytlık imza üretir (FBL açık anahtarı senin anahtarın "
                 "olmalı). Çıktı: signature_<dosya>.bin")
        self.lbl_44 = ttk.Label(o, text="firmware gerekir (anahtar pakette gömülü)", foreground="#8b949e")
        self.lbl_44.grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))

    # ══════════════════════════════ 5 · REFERANS
    def _build_ref(self) -> None:
        f = self.tab_ref
        f.columnconfigure(0, weight=1)
        f.rowconfigure(1, weight=1)
        row = ttk.Frame(f)
        row.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        b1 = ttk.Button(row, text="12 CP bankası tablosu", command=lambda: self._ref("banks"))
        b1.pack(side="left")
        tip(b1, "Her bankanın VAG ECU adresi, modül adı, DataFlash offseti, NvM ID'si, UDS ve CAN ID'leri.")
        b2 = ttk.Button(row, text="Adım adım rehber", command=lambda: self._ref("guide"))
        b2.pack(side="left", padx=6)
        tip(b2, "Dump nereden okunur, IKA anahtarı nasıl bulunur, hangi sırayla yazılır — "
                "motorun kendi adım adım rehberi.")
        self.txt_ref = tk.Text(f, wrap="none", font=("Consolas", 9), background="#0d1117",
                               foreground="#c9d1d9", insertbackground="#c9d1d9")
        self.txt_ref.grid(row=1, column=0, sticky="nsew")
        for i, w in enumerate((5, 6, 46, 8, 16, 14, 26, 26)):
            self.txt_ref.columnconfigure(i, minsize=w * 7)
        sy = ttk.Scrollbar(f, orient="vertical", command=self.txt_ref.yview)
        sy.grid(row=1, column=1, sticky="ns")
        sx = ttk.Scrollbar(f, orient="horizontal", command=self.txt_ref.xview)
        sx.grid(row=2, column=0, sticky="ew")
        self.txt_ref.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)

    # ── alt panel (günlük + durum)
    def _build_footer(self) -> None:
        logf = ttk.LabelFrame(self, text=" Günlük ", padding=6)
        logf.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        logf.columnconfigure(0, weight=1)
        self.log = tk.Text(logf, height=7, wrap="word", font=("Consolas", 9),
                           background="#0d1117", foreground="#c9d1d9", insertbackground="#c9d1d9")
        self.log.grid(row=0, column=0, sticky="ew")
        sb = ttk.Scrollbar(logf, orient="vertical", command=self.log.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=sb.set)
        for tag, color in (("ok", "#3fb950"), ("err", "#f85149"), ("warn", "#d29922"),
                           ("info", "#79c0ff"), ("dim", "#8b949e"), ("head", "#c9a0ff")):
            self.log.tag_configure(tag, foreground=color)
        self.log.configure(state="disabled")

        foot = ttk.Frame(self)
        foot.grid(row=3, column=0, sticky="ew", pady=(4, 0))
        foot.columnconfigure(0, weight=1)
        ttk.Label(foot, textvariable=self.v_status, foreground="#6b6b6b").grid(
            row=0, column=0, sticky="w")
        ttk.Label(foot, text=CREDIT_LINE, foreground="#8b949e",
                  font=("Segoe UI", 8)).grid(row=0, column=1, sticky="e", padx=(12, 0))

    # ── günlük
    def _log(self, text: str, tag: str = "info") -> None:
        """Günlüğe yazar. Arka plan iş parçacığından çağrılırsa kuyruğa bırakır
        (Tk widget'larına yalnız ana iş parçacığından dokunulabilir)."""
        if threading.current_thread() is not threading.main_thread():
            self.queue.put(("log", (text, tag)))
            return
        self.log.configure(state="normal")
        self.log.insert("end", text.rstrip() + "\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _log_block(self, text: str, tag: str = "dim") -> None:
        for line in (text or "").splitlines():
            self._log(line, tag)

    def _set_sum(self, text: str) -> None:
        if threading.current_thread() is not threading.main_thread():
            self.queue.put(("sum", text))
            return
        self.lbl_sum.configure(text=text)

    def _set_lbl(self, name: str, text: str, ok: bool = True) -> None:
        """Sekme içi sonuç etiketi (4.1/4.2/4.3/4.4)."""
        if threading.current_thread() is not threading.main_thread():
            self.queue.put(("lbl", (name, text, ok)))
            return
        lbl = getattr(self, f"lbl_{name}", None)
        if lbl is not None:
            lbl.configure(text=text, foreground="#1f8f3d" if ok else "#b3261e")

    # ── iş kuyruğu
    def _pump(self) -> None:
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "log":
                    self._log(payload[0], payload[1])
                elif kind == "status":
                    self.v_status.set(payload)
                elif kind == "sum":
                    self.lbl_sum.configure(text=payload)
                elif kind == "lbl":
                    name, text, ok = payload
                    lbl = getattr(self, f"lbl_{name}", None)
                    if lbl is not None:
                        lbl.configure(text=text, foreground="#1f8f3d" if ok else "#b3261e")
                elif kind == "done":
                    self.busy = False
                    self._set_buttons(True)
                    self.v_status.set(payload or "Hazır.")
        except queue.Empty:
            pass
        self.after(120, self._pump)

    def _set_buttons(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for b in (getattr(self, "b_cp", None), getattr(self, "b_eng", None)):
            if b is not None:
                b.configure(state=state)

    def _run_bg(self, fn, label: str) -> None:
        if self.busy:
            messagebox.showinfo(APP_SHORT, "Başka bir işlem sürüyor, bitmesini bekle.")
            return
        self.busy = True
        self._set_buttons(False)
        self.v_status.set(label + " ...")

        def worker():
            try:
                fn()
            except Exception:  # noqa: BLE001
                self.queue.put(("log", ("✘ beklenmeyen hata:\n" + traceback.format_exc(limit=6), "err")))
            finally:
                self.queue.put(("done", "Hazır."))

        threading.Thread(target=worker, daemon=True).start()

    # ── yardımcılar
    def _pick_dir(self, var: tk.StringVar) -> None:
        p = filedialog.askdirectory(title="Klasör seç", initialdir=str(APP_DIR))
        if p:
            var.set(p)

    def _all_banks(self, on: bool) -> None:
        for v in self.bank_vars.values():
            v.set(on)

    def _selected_banks(self) -> list[int]:
        return [n for n, v in sorted(self.bank_vars.items()) if v.get()]

    def _rand_key(self) -> None:
        self.v_key.set(random_ika())

    def _copy_pubkey(self) -> None:
        """Paket public key'inin (modulus) tam hex'ini panoya kopyalar."""
        p = bundled_key()
        if p is None:
            messagebox.showerror(APP_SHORT, "Paket anahtarı bulunamadı.")
            return
        try:
            n = json.loads(p.read_text(encoding="utf-8")).get("n_hex", "")
        except (OSError, ValueError):
            n = ""
        if not n:
            messagebox.showerror(APP_SHORT, "Anahtar dosyası okunamadı.")
            return
        self.clipboard_clear()
        self.clipboard_append(n)
        self._log(f"  public key panoya kopyalandı ({len(n)} hex karakter) · N = {n[:24]}…", "ok")

    def _fec_codes(self) -> list[str]:
        """İşaretli SWaP kodları + özel alandaki kodlar (sıra korunur)."""
        codes: list[str] = [c for c, v in getattr(self, "fec_vars", {}).items() if v.get()]
        for m in re.findall(r"(?:0x)?([0-9a-fA-F]{8})", self.v_fec.get()):
            c = m.lower()
            if c not in codes:
                codes.append(c)
        return codes

    def _fsc_for(self, code: str) -> bytes | None:
        """Seçili kod için FSC'yi paket anahtarıyla üretir (bellekte)."""
        eng = get_engine()
        keyf = bundled_key()
        if eng is None or keyf is None:
            return None
        n_bytes, d_int = eng.load_rsa1024_key_material(str(keyf))
        if d_int is None:
            return None
        vcrn = re.sub(r"[\s:_-]", "", self.v_vcrn.get()).lower()
        df = self._path(self.f_dflash)
        if not vcrn and df:
            try:
                vcrn = (eng.analyze_dflash_swap(df.read_bytes()).vcrn or "").replace(" ", "")
            except Exception:  # noqa: BLE001
                vcrn = ""
        if len(vcrn) != 10:
            return None
        vin = "" if self.v_novin.get() else self.v_vin.get().strip().upper()
        if vin and len(vin) != 17:
            return None
        try:
            return eng.build_signed_fsc(int(code, 16), bytes.fromhex(vcrn), vin, n_bytes, d_int)
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _adapt_formats(fsc: bytes) -> dict[str, str]:
        """Adaptasyon alanına yapıştırılabilecek biçimler."""
        return {
            "DEC": str(int.from_bytes(fsc, "big")),
            "HEX": fsc.hex().upper(),
            "HEX_SPACED": " ".join(f"{b:02X}" for b in fsc),
            "0xHEX": "0x" + fsc.hex().upper(),
            "BASE64": base64.b64encode(fsc).decode("ascii"),
            "BYTES": ",".join(str(b) for b in fsc),
        }

    def _show_adapt_values(self) -> None:
        """Transfer SWaP (adaptasyon) için uzun değeri üretir: DEC / HEX / Base64."""
        codes = self._fec_codes()
        if not codes:
            messagebox.showwarning(APP_SHORT, "Önce en az bir SWaP kodu seç.")
            return
        win = tk.Toplevel(self)
        win.title("Transfer SWaP — adaptasyon değeri")
        win.transient(self.master)
        body = ttk.Frame(win, padding=10)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Adaptasyon > 'Transfer SWaP function' alanına bu değeri yapıştır.",
                  font=("Segoe UI", 9, "bold")).pack(anchor="w")
        ttk.Label(body, foreground="#6b6b6b", wraplength=760, justify="left",
                  text="Önce DEC (10'luk sayı) dene — ODIS/VCDS adaptasyon alanları ondalık bekler. "
                       "Kabul etmezse HEX'i, o da olmazsa Base64'ü dene.\n"
                       "Değer 171 baytlık FSC sertifikasının kendisidir; gateway bunu çözüp imzayı doğrular."
                  ).pack(anchor="w", pady=(2, 8))

        out_dir = Path(self.v_out.get().strip() or (APP_DIR / "cikti"))
        produced = 0
        for code in codes:
            fsc = self._fsc_for(code)
            if fsc is None:
                ttk.Label(body, text=f"{code}: ✘ üretilemedi (şase/VCRN/anahtar eksik)",
                          foreground="#b3261e").pack(anchor="w")
                continue
            fmts = self._adapt_formats(fsc)
            produced += 1
            row = ttk.LabelFrame(body, text=f" FeC {code} · {len(fsc)} bayt ", padding=6)
            row.pack(fill="x", pady=3)
            for i, key in enumerate(("DEC", "HEX", "BASE64")):
                val = fmts[key]
                ttk.Label(row, text=f"{key:6}", width=7).grid(row=i, column=0, sticky="w")
                ent = ttk.Entry(row, width=64)
                ent.insert(0, val)
                ent.configure(state="readonly")
                ent.grid(row=i, column=1, sticky="ew", padx=4, pady=1)
                b = ttk.Button(row, text="Kopyala", width=9,
                               command=lambda v=val: self._copy_text(v))
                b.grid(row=i, column=2, sticky="w")
            row.columnconfigure(1, weight=1)
            # dosyaya yaz
            try:
                out_dir.mkdir(parents=True, exist_ok=True)
                txt = out_dir / f"adapt_{code}.txt"
                payload = [
                    f"FeC {code} · 171 bayt FSC · Transfer SWaP (adaptasyon)", "",
                    "DEC:", fmts["DEC"], "",
                    "HEX:", fmts["HEX"], "",
                    "HEX (bosluklu):", fmts["HEX_SPACED"], "",
                    "0xHEX:", fmts["0xHEX"], "",
                    "BASE64:", fmts["BASE64"], "",
                    "BYTES:", fmts["BYTES"], "",
                ]
                txt.write_text(chr(10).join(payload), encoding="utf-8")
            except OSError:
                pass
        foot = ttk.Frame(body)
        foot.pack(fill="x", pady=(6, 0))
        ttk.Button(foot, text="Kapat", command=win.destroy).pack(side="right")
        ttk.Label(foot, foreground="#6b6b6b",
                  text=f"{produced} değer üretildi · .txt dosyaları: {out_dir}"
                  ).pack(side="left")
        if produced:
            self._log(f"  adaptasyon değerleri üretildi ({produced} kod) → {out_dir}", "ok")
        win.bind("<Escape>", lambda _e: win.destroy())

    def _copy_text(self, text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)
        self._log(f"  panoya kopyalandı ({len(text)} karakter)", "ok")

    def _read_vcrn(self) -> None:
        """VCRN'i DataFlash dump'ından okur (SWaP önbelleği 0xDC0C)."""
        df = self._path(self.f_dflash)
        if df is None:
            messagebox.showwarning(APP_SHORT, "Önce 1. sekmede DataFlash dump'ını seç.")
            return
        eng = get_engine()
        try:
            sw = eng.analyze_dflash_swap(df.read_bytes())
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(APP_SHORT, f"DataFlash okunamadı:\n{exc}")
            return
        vcrn = (sw.vcrn or "").replace(" ", "")
        if not vcrn:
            messagebox.showwarning(APP_SHORT, "Dump içinde VCRN bulunamadı (SWaP önbelleği boş olabilir).")
            return
        self.v_vcrn.set(vcrn)
        self._log(f"  VCRN DataFlash'tan okundu: {vcrn}", "ok")
        self._set_lbl("43", f"VCRN okundu: {vcrn}", True)

    def _path(self, var: tk.StringVar) -> Path | None:
        raw = var.get().strip().strip('"')
        if not raw:
            return None
        p = Path(raw)
        return p if p.is_file() else None

    def _need(self, *pairs) -> bool:
        """(değer, ad) çiftlerini doğrular; eksikse uyarı gösterir."""
        missing = [name for val, name in pairs if not val]
        if missing:
            messagebox.showwarning(APP_SHORT, "Şunlar gerekli:\n• " + "\n• ".join(missing))
            return False
        return True

    # ── otomatik tarama
    def _startup_scan(self) -> None:
        if not engine_ready():
            self._log("✘ Yama motoru yüklenemedi.", "err")
            self._log(f"  motor yolu: {ENGINE_BUNDLED}", "dim")
            for ln in (_ENGINE_ERROR or "bilinmeyen hata").strip().splitlines()[-6:]:
                self._log("  " + ln, "err")
            return
        self._log(f"✔ Yama motoru hazır: {engine_source()}", "dim")
        self._log("  Program internete bağlanmaz; tüm işlemler yerel dosyalarla yapılır.", "dim")
        self._scan(quiet=True)

    def _scan(self, quiet: bool = False) -> None:
        roots = [Path(self.v_out.get()) if self.v_out.get() else APP_DIR, APP_DIR,
                 Path.home() / "Desktop", Path.home() / "Downloads"]
        found = scan_dumps([r for r in roots if Path(r).exists()])
        hit = 0
        for key, var in (("cflash", self.f_cflash), ("dflash", self.f_dflash),
                         ("uflash", self.f_uflash)):
            if found.get(key):
                var.set(str(found[key]))
                hit += 1
                if not quiet:
                    self._log(f"  • {key}: {found[key].name}", "ok")
        if not quiet:
            if hit:
                self._log(f"✔ {hit} dump bulundu ve alanlara yerleştirildi.", "ok")
            else:
                self._log("⚠ Dump bulunamadı — 'Seç...' ile elle gösterebilirsin.", "warn")

    # ══════════════════════════════ işlemler
    def _do_inspect(self) -> None:
        cf, df, uf = (self._path(self.f_cflash), self._path(self.f_dflash),
                      self._path(self.f_uflash))
        if not (cf or df or uf):
            messagebox.showwarning(APP_SHORT, "En az bir dump dosyası seç (CodeFlash / DataFlash / Uflash).")
            return

        def job():
            self.queue.put(("log", ("══ inceleme ══", "head")))
            eng = get_engine()
            summary_bits = []
            for p in (cf, df, uf):
                if p:
                    self.queue.put(("log", (f"  {p.name}  ({fmt_size(p.stat().st_size)})", "dim")))
            # CodeFlash
            if cf:
                try:
                    raw = cf.read_bytes()
                    s = eng.analyze_cflash(raw)
                    crc = "OK" if s.crc_ok else "HATA"
                    mode = s.hook_mode or "yok"
                    self.queue.put(("log", (
                        f"CodeFlash: CRC={crc} ({s.crc_stored:#06x}/{s.crc_calc:#06x}) · "
                        f"CP kancası={mode} · 95640 maske={'atlanmış' if s.mask_bypassed else 'normal'} · "
                        f"CCP gate={'açık' if s.eng_gate_unlocked else 'kilitli'} · "
                        f"CCP blacklist={'atlanmış' if s.ccp_blacklist_bypassed else 'aktif'} · "
                        f"OTP A167={'atlanmış' if s.a167_branch_bypassed else 'kilitli'}", "info")))
                    summary_bits.append(f"CodeFlash: CP {mode}, CRC {'OK' if s.crc_ok else 'HATA'}")
                except Exception as exc:  # noqa: BLE001
                    self.queue.put(("log", (f"✘ CodeFlash okunamadı: {exc}", "err")))
            # DataFlash
            if df:
                try:
                    dfb = df.read_bytes()
                    states = eng.analyze_dflash(dfb)
                    self.tree.delete(*self.tree.get_children())
                    dolu = 0
                    for st in states:
                        spec = st.spec
                        if st.empty:
                            durum, key = "BOŞ", "—"
                        else:
                            dolu += 1
                            durum = f"DOLU ({st.kind})"
                            key = st.first16_hex or "—"
                        self.tree.insert("", "end", values=(
                            f"#{spec.slot}", spec.ecu_addr, spec.short_en, spec.nvm_id,
                            spec.off1, durum, key))
                    sw = eng.analyze_dflash_swap(dfb)
                    self.queue.put(("log", (
                        f"DataFlash: {dolu}/12 banka dolu · VCRN={sw.vcrn or '—'} · "
                        f"SWaP CRC={'OK' if sw.crc_ok else 'HATA'} · "
                        f"aktif FSC={len(sw.active_fscs)} · boş slot={sw.free_slots}", "info")))
                    summary_bits.append(f"DataFlash: {dolu}/12 banka dolu")
                except Exception as exc:  # noqa: BLE001
                    self.queue.put(("log", (f"✘ DataFlash okunamadı: {exc}", "err")))
            # Uflash
            if uf:
                try:
                    ub = uf.read_bytes()
                    us = eng.analyze_uflash(ub)
                    self.queue.put(("log", (
                        f"Uflash: imza={'var' if us.signature_found else 'yok'} · "
                        f"RSA yaması={'uygulanmış' if us.rsa_bypassed else 'yok'} · "
                        f"{us.raw_insn_hex or ''}", "info")))
                    summary_bits.append("Uflash: " + ("engineering" if us.rsa_bypassed else "stok"))
                except Exception as exc:  # noqa: BLE001
                    self.queue.put(("log", (f"✘ Uflash okunamadı: {exc}", "err")))
            self.queue.put(("status", "İnceleme bitti."))
            self._set_sum("  ·  ".join(summary_bits))
            self.queue.put(("log", ("✔ inceleme tamam (salt okuma, hiçbir dosya değişmedi)", "ok")))

        self._run_bg(job, "İnceleniyor")

    def _do_report(self) -> None:
        cf, df, uf = (self._path(self.f_cflash), self._path(self.f_dflash),
                      self._path(self.f_uflash))
        if not (cf or df or uf):
            messagebox.showwarning(APP_SHORT, "Önce dump dosyalarını seç.")
            return

        def job():
            tok = ["inspect"]
            if cf:
                tok += ["--cflash", str(cf)]
            if df:
                tok += ["--dflash", str(df)]
            if uf:
                tok += ["--uflash", str(uf)]
            rc, out = run_engine(tok)
            self._log_block(out, "dim")
            self.queue.put(("log", (f"{'✔' if rc == 0 else '✘'} ham rapor (rc={rc})",
                                    "ok" if rc == 0 else "err")))

        self._run_bg(job, "Rapor hazırlanıyor")

    def _do_cp(self) -> None:
        cf, df = self._path(self.f_cflash), self._path(self.f_dflash)
        banks = self._selected_banks()
        key = re.sub(r"[\s:_-]", "", self.v_key.get()).upper()
        if not self._need((cf, "CodeFlash dump"), (df, "DataFlash dump"),
                          (banks, "en az bir banka"), (key, "IKA anahtarı")):
            return
        if len(key) != 32 or not re.fullmatch(r"[0-9A-F]{32}", key):
            messagebox.showwarning(APP_SHORT, "IKA anahtarı 32 hex karakter olmalı (16 bayt).")
            return
        out = Path(self.v_out.get().strip() or (APP_DIR / "cikti"))
        out.mkdir(parents=True, exist_ok=True)
        cf_out = out / "CodeFlash.patched.bin"
        df_out = out / "DataFlash.patched.bin"
        # Tk değişkenleri yalnız ana iş parçacığında okunabilir → şimdi kopyala
        bypass, global_plain, ignore_crc = (self.v_bypass.get(), self.v_global.get(),
                                            self.v_ignore.get())

        def job():
            self._log("══ CP bağlama ══", "head")
            self._log(f"  bankalar: {', '.join('#' + str(b) for b in banks)}", "dim")
            tok = ["patch-cflash", "-i", str(cf), "-o", str(cf_out)]
            if bypass:
                tok.append("--bypass-eeprom-mask")
            if global_plain:
                tok.append("--global-plain")
            if ignore_crc:
                tok.append("--ignore-input-crc")
            rc, out1 = run_engine(tok)
            self._log_block(out1, "dim" if rc == 0 else "err")
            if rc != 0:
                self.queue.put(("log", (f"✘ CodeFlash yamalanamadı (rc={rc})", "err")))
                return
            self.queue.put(("log", (f"✔ CodeFlash: {cf_out.name}", "ok")))
            tok2 = ["set-cp-key", "-i", str(df), "-o", str(df_out)]
            for b in banks:
                tok2 += ["--set", f"{b}={key}"]
            rc, out2 = run_engine(tok2)
            self._log_block(out2, "dim" if rc == 0 else "err")
            if rc != 0:
                self.queue.put(("log", (f"✘ DataFlash anahtar yazımı başarısız (rc={rc})", "err")))
                return
            self.queue.put(("log", (f"✔ DataFlash: {df_out.name}", "ok")))
            # doğrulama
            eng = get_engine()
            try:
                cs = eng.analyze_cflash(cf_out.read_bytes())
                self.queue.put(("log", (
                    f"  doğrulama · CodeFlash: CP kancası={cs.hook_mode or 'yok'} · "
                    f"CRC={'OK' if cs.crc_ok else 'HATA'}", "ok" if cs.crc_ok else "warn")))
            except Exception as exc:  # noqa: BLE001
                self.queue.put(("log", (f"  ⚠ CodeFlash doğrulanamadı: {exc}", "warn")))
            try:
                states = {st.spec.slot: st for st in eng.analyze_dflash(df_out.read_bytes())}
                for b in banks:
                    st = states.get(b)
                    if st is None:
                        continue
                    self.queue.put(("log", (
                        f"  doğrulama · banka #{b}: {'BOŞ (yazılmadı!)' if st.empty else 'DOLU (' + str(st.kind) + ')'}"
                        f" · {st.first16_hex[:32]}", "warn" if st.empty else "ok")))
            except Exception as exc:  # noqa: BLE001
                self.queue.put(("log", (f"  ⚠ DataFlash doğrulanamadı: {exc}", "warn")))
            self.queue.put(("log", (f"✔ bitti → {out}", "ok")))
            self.queue.put(("status", "CP bağlama bitti."))

        self._run_bg(job, "CP bağlanıyor")

    def _do_clear(self) -> None:
        df = self._path(self.f_dflash)
        banks = self._selected_banks()
        if not self._need((df, "DataFlash dump"), (banks, "en az bir banka")):
            return
        out = Path(self.v_out.get().strip() or (APP_DIR / "cikti"))
        out.mkdir(parents=True, exist_ok=True)
        df_out = out / "DataFlash.cleared.bin"

        def job():
            self._log("══ banka boşaltma ══", "head")
            rc, out1 = run_engine(["clear-cp-key", "-i", str(df), "-o", str(df_out),
                                   "--bank", ",".join(str(b) for b in banks)])
            self._log_block(out1, "dim" if rc == 0 else "err")
            self.queue.put(("log", (f"{'✔' if rc == 0 else '✘'} {df_out.name}",
                                    "ok" if rc == 0 else "err")))

        self._run_bg(job, "Bankalar boşaltılıyor")

    def _do_eng(self) -> None:
        cf, uf = self._path(self.f_cflash), self._path(self.f_uflash)
        if not self._need((cf or uf, "CodeFlash veya Uflash dump")):
            return
        out = Path(self.v_out.get().strip() or (APP_DIR / "cikti"))
        out.mkdir(parents=True, exist_ok=True)
        cf_out = out / "CodeFlash.eng.bin"
        uf_out = out / "Uflash.eng.bin"
        # Tk değişkenlerini ana iş parçacığında oku
        restore, ignore_crc = self.v_eng_restore.get(), self.v_eng_ignore.get()

        def job():
            self._log("══ Engineering Mode ══", "head")
            tok = ["patch-engineering"]
            if cf:
                tok += ["--cflash-in", str(cf), "--cflash-out", str(cf_out)]
            if uf:
                tok += ["--uflash-in", str(uf), "--uflash-out", str(uf_out)]
            if restore:
                tok.append("--restore-stock")
            if ignore_crc:
                tok.append("--ignore-input-crc")
            rc, out1 = run_engine(tok)
            self._log_block(out1, "dim" if rc == 0 else "err")
            if rc != 0:
                self.queue.put(("log", (f"✘ Engineering yaması başarısız (rc={rc})", "err")))
                return
            eng = get_engine()
            if cf and cf_out.is_file():
                try:
                    cs = eng.analyze_cflash(cf_out.read_bytes())
                    self.queue.put(("log", (
                        f"  doğrulama · CCP gate={'açık' if cs.eng_gate_unlocked else 'kilitli'} · "
                        f"blacklist={'atlanmış' if cs.ccp_blacklist_bypassed else 'aktif'} · "
                        f"OTP={'atlanmış' if cs.a167_branch_bypassed else 'kilitli'} · "
                        f"CRC={'OK' if cs.crc_ok else 'HATA'}", "ok")))
                except Exception as exc:  # noqa: BLE001
                    self.queue.put(("log", (f"  ⚠ doğrulanamadı: {exc}", "warn")))
            if uf and uf_out.is_file():
                try:
                    us = eng.analyze_uflash(uf_out.read_bytes())
                    self.queue.put(("log", (
                        f"  doğrulama · Uflash RSA yaması={'uygulanmış' if us.rsa_bypassed else 'yok'}",
                        "ok" if us.rsa_bypassed else "warn")))
                except Exception as exc:  # noqa: BLE001
                    self.queue.put(("log", (f"  ⚠ Uflash doğrulanamadı: {exc}", "warn")))
            self.queue.put(("log", (f"✔ bitti → {out}", "ok")))
            self.queue.put(("status", "Engineering Mode bitti."))

        self._run_bg(job, "Engineering Mode uygulanıyor")

    def _do_setkey(self) -> None:
        keyf = bundled_key()
        cf, df = self._path(self.f_cflash), self._path(self.f_dflash)
        if keyf is None:
            messagebox.showerror(APP_SHORT, "Paket anahtarı bulunamadı (assets/anahtar/swap_rsa1024.json).")
            return
        if not self._need((cf or df, "CodeFlash (veya DataFlash) dump'ı")):
            return
        out = Path(self.v_out.get().strip() or (APP_DIR / "cikti"))
        out.mkdir(parents=True, exist_ok=True)
        cf_out = out / "CodeFlash.swap.bin"
        df_out = out / "DataFlash.swap.bin"
        target = self.v_target.get()
        rsa_ignore = self.v_rsa_ignore.get()

        def job():
            self._log(f"══ RSA modulus gömme (hedef: {target}) ══", "head")
            self._set_lbl("42", "işleniyor...", True)
            tok = ["set-rsa-key", "-k", str(keyf), "--target", target]
            if cf:
                tok += ["--cflash-in", str(cf), "--cflash-out", str(cf_out)]
            if df:
                tok += ["--dflash-in", str(df), "--dflash-out", str(df_out)]
            if rsa_ignore:
                tok.append("--ignore-input-crc")
            rc, out1 = run_engine(tok)
            self._log_block(out1, "dim" if rc == 0 else "err")
            if not df:
                self._log("⚠ DataFlash yazılmadı: araçta FSC doğrulaması önbellekteki modulus'u "
                          "(DataFlash NvM 0x7C) okur — araçta çalışması için DataFlash dump'ı da ver.",
                          "warn")
            if rc != 0:
                hint = (" · 'Girdi CRC hatasını yok say' seçeneğini dene"
                        if "ignore-input-crc" in out1 else "")
                self._log(f"✘ modulus gömülemedi (rc={rc})", "err")
                self._set_lbl("42", f"✘ gömülemedi (rc={rc}){hint}", False)
                return
            eng = get_engine()
            for label, path in (("CodeFlash", cf_out), ("DataFlash", df_out)):
                if not path.is_file():
                    continue
                try:
                    if label == "CodeFlash":
                        s = eng.analyze_cflash(path.read_bytes())
                        self._log(f"  doğrulama · {label}: SWaP modulus={s.swap_rsa_mod[:16].hex()}… · "
                                  f"CRC={'OK' if s.crc_ok else 'HATA'}", "ok")
                    else:
                        sw = eng.analyze_dflash_swap(path.read_bytes())
                        self._log(f"  doğrulama · {label}: modulus={sw.swap_rsa_mod[:16].hex()}… · "
                                  f"VCRN={sw.vcrn or '—'} · CRC={'OK' if sw.crc_ok else 'HATA'}", "ok")
                except Exception as exc:  # noqa: BLE001
                    self._log(f"  ⚠ {label} doğrulanamadı: {exc}", "warn")
            self._log(f"✔ bitti → {out}", "ok")
            files = " + ".join(p.name for p in (cf_out, df_out) if p.is_file())
            extra = "" if df else " · ⚠ DataFlash yazılmadı"
            self._set_lbl("42", f"✔ {files} · hedef {target}{extra}", not df)
            self.queue.put(("status", "Modulus gömüldü."))

        self._run_bg(job, "Modulus gömülüyor")

    def _do_fsc(self) -> None:
        keyf = bundled_key()
        df = self._path(self.f_dflash)
        codes = self._fec_codes()
        vcrn = re.sub(r"[\s:_-]", "", self.v_vcrn.get()).lower()
        if keyf is None:
            messagebox.showerror(APP_SHORT, "Paket anahtarı bulunamadı (assets/anahtar/swap_rsa1024.json).")
            return
        if not codes:
            messagebox.showwarning(APP_SHORT,
                                   "En az bir FeC kodu gir (8 hex, örn. 10000100).\n"
                                   "Birden fazla kod için virgülle ayır: 10000100, 10000300")
            return
        if vcrn and not re.fullmatch(r"[0-9a-f]{10}", vcrn):
            messagebox.showwarning(APP_SHORT,
                                   "VCRN 5 bayt = 10 hex karakter olmalı (örn. 0102030405).")
            return
        if not vcrn and df is None:
            messagebox.showwarning(APP_SHORT,
                                   "VCRN gerekli: ya 'VCRN' alanını doldur ya da DataFlash dump'ını seç\n"
                                   "(sertifika araca özel VCRN olmadan geçerli olmaz).")
            return
        out = Path(self.v_out.get().strip() or (APP_DIR / "cikti"))
        out.mkdir(parents=True, exist_ok=True)
        # Tk değişkenlerini ana iş parçacığında oku
        vin_val, no_vin = self.v_vin.get().strip().upper(), self.v_novin.get()

        def job():
            self._log(f"══ FSC imzalama · {len(codes)} kod: {', '.join(codes)} ══", "head")
            self._set_lbl("43", "işleniyor...", True)
            ok_list: list[str] = []
            bad_list: list[str] = []
            for code in codes:
                fsc_out = out / f"fsc_{code}.fsc"
                tok = ["sign-fsc", "-k", str(keyf), "--fec", code, "-o", str(fsc_out)]
                if vcrn:
                    tok += ["--vcrn", vcrn]
                elif df:
                    tok += ["--dflash", str(df)]
                if vin_val and len(vin_val) == 17:
                    tok += ["--vin", vin_val]
                elif no_vin or not vin_val:
                    tok.append("--no-vin")
                else:
                    self._log("⚠ VIN 17 karakter değil — joker (VIN'siz) üretiliyor.", "warn")
                    tok.append("--no-vin")
                rc, out1 = run_engine(tok)
                if rc == 0 and fsc_out.is_file():
                    ok_list.append(f"{code} ({fsc_out.stat().st_size} B)")
                    self._log(f"✔ {fsc_out.name}  ({fmt_size(fsc_out.stat().st_size)})", "ok")
                else:
                    bad_list.append(code)
                    self._log(f"✘ FeC {code}: üretilemedi (rc={rc})", "err")
                    self._log_block(out1, "err")
            if ok_list:
                self._set_lbl("43", f"✔ {len(ok_list)} sertifika: {', '.join(ok_list[:4])}"
                                    + (" …" if len(ok_list) > 4 else ""), not bad_list)
            else:
                self._set_lbl("43", "✘ hiçbir sertifika üretilemedi — günlüğe bak", False)
            if bad_list:
                self._log(f"⚠ başarısız FeC: {', '.join(bad_list)}", "warn")
            self._log(f"✔ bitti → {out}", "ok")
            self.queue.put(("status", f"{len(ok_list)}/{len(codes)} FSC hazır."))

        self._run_bg(job, "FSC imzalanıyor")

    def _do_signodx(self) -> None:
        keyf = bundled_key()
        src = self._path(self.v_odxin) or self._path(self.f_cflash)
        if keyf is None:
            messagebox.showerror(APP_SHORT, "Paket anahtarı bulunamadı (assets/anahtar/swap_rsa1024.json).")
            return
        if not self._need((src, "firmware (CodeFlash)")):
            return
        out = Path(self.v_out.get().strip() or (APP_DIR / "cikti"))
        out.mkdir(parents=True, exist_ok=True)
        sig_out = out / f"signature_{src.stem}.bin"

        def job():
            self._log("══ Firmware imzalama (<FW-SIGNATURE>) ══", "head")
            self._set_lbl("44", "imzalanıyor...", True)
            rc, out1 = run_engine(["sign-odx", "-i", str(src), "-k", str(keyf), "-o", str(sig_out)])
            self._log_block(out1, "dim" if rc == 0 else "err")
            if rc == 0 and sig_out.is_file():
                self._log(f"✔ {sig_out.name}  ({fmt_size(sig_out.stat().st_size)})", "ok")
                self._set_lbl("44", f"✔ {sig_out.name} · "
                                    f"{sig_out.stat().st_size} B", True)
            else:
                self._log(f"✘ imza üretilemedi (rc={rc})", "err")
                self._set_lbl("44", f"✘ imza üretilemedi (rc={rc}) — günlüğe bak", False)
            self.queue.put(("status", "İmza hazır."))

        self._run_bg(job, "İmzalanıyor")

    def _ref(self, what: str) -> None:
        def job():
            rc, out = run_engine([what])
            self.txt_ref.configure(state="normal")
            self.txt_ref.delete("1.0", "end")
            self.txt_ref.insert("1.0", out if out.strip() else f"(boş çıktı, rc={rc})")
            self.txt_ref.configure(state="disabled")
            self.queue.put(("status", "Referans yüklendi."))

        self._run_bg(job, "Referans hazırlanıyor")

    # ── hakkında
    def _about(self) -> None:
        messagebox.showinfo(
            "Hakkında / Kaynak",
            f"{APP_TITLE}\nSürüm {APP_VERSION}\n\n"
            "Continental VAG MQB J533 (3Q0 907 530) gateway için bileşen koruması (CP/KSCHUTZ) "
            "bağlama, Engineering Mode ve RSA-1024 / SWaP (FSC) imzalama aracı.\n\n"
            f"Kullanılan kaynak / yama motoru:\n{SOURCE_PROJECT}\n"
            "Yama motoru bu programın İÇİNE gömülüdür: harici .py dosyası, kurulum veya internet "
            "bağlantısı GEREKMEZ. Program internete bağlanmaz ve hiçbir şey indirmez; tüm işlemler "
            "bilgisayarında, yerel dosyalarla yapılır.\n\n"
            "Bu program hiçbir firmware veya OEM kodu içermez; tüm dump dosyaları kullanıcının kendi "
            "diskindedir.\n\n"
            "Lisans: non-commercial / Right-to-Repair — satış ve ücretli hizmet yasak.\n\n"
            "⚠ UYARI: Yanlış dump veya yanlış yazma gateway'i brick edebilir. Yazmadan önce her zaman "
            "CodeFlash (1.5 MB), DataFlash (64 KB), Uflash (32 KB) ve harici 95640 EEPROM'un tam "
            "yedeklerini al. Sorumluluk kullanıcıya aittir.")


def main() -> int:
    if "--selftest" in sys.argv:
        # motor gömülü mü + komut yolu çalışıyor mu (imza üretimi ile)
        idx = sys.argv.index("--selftest")
        out = Path(sys.argv[idx + 1]) if len(sys.argv) > idx + 1 else Path(".")
        out.mkdir(parents=True, exist_ok=True)
        keyf = bundled_key()
        lines = [f"motor: {engine_source()}", f"frozen: {FROZEN}",
                 f"anahtar: {keyf}", f"modulus: {bundled_modulus()}",
                 f"anahtar_var={keyf is not None}"]
        rc2, text2 = run_engine(["sign-fsc", "-k", str(keyf or ""), "--fec", "10000100",
                                 "--vcrn", "0102030405", "--vin", "VSSZZZ5FZGR239596",
                                 "-o", str(out / "t.fsc")])
        lines.append(f"sign-fsc rc={rc2}")
        lines.append(text2[-400:])
        fsc = out / "t.fsc"
        lines.append(f"fsc_boyut={fsc.stat().st_size if fsc.is_file() else -1}")
        if fsc.is_file():
            fb = fsc.read_bytes()
            lines.append(f"fsc_vin_var={b'VSSZZZ5FZGR239596' in fb}")
            lines.append(f"fsc_vcrn_var={bytes.fromhex('0102030405') in fb}")
            lines.append(f"fsc_fec_var={bytes.fromhex('10000100') in fb}")
        lines.append("dosyalar: " + ", ".join(sorted(p.name for p in out.glob("*"))))
        report = "\n".join(lines)
        (out / "selftest.txt").write_text(report, encoding="utf-8")
        try:
            if sys.stdout is not None:
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
                print(report)
        except (AttributeError, ValueError, OSError):
            pass
        return rc2

    root = tk.Tk()
    root.title(f"{APP_SHORT}  v{APP_VERSION}")
    root.geometry("1180x900")
    root.minsize(980, 700)
    for cand in ("assets/logo.ico", "logo.ico"):
        p = ASSET_DIR / Path(cand).name
        if p.is_file():
            try:
                root.iconbitmap(default=str(p))
            except tk.TclError:
                pass
            break
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    app = Studio(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
