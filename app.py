"""
app.py  —  DBF Splitter Desktop Application
Requires only Python standard library (tkinter included).
Run:  python app.py
"""

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from dbf_engine import read_dbf_header, split_cams, split_karvy, create_cams_zips, create_karvy_zips


# ──────────────────────────────────────────────────────────────
#  Colour palette
# ──────────────────────────────────────────────────────────────
C = {
    "bg":           "#F7F6F3",
    "surface":      "#FFFFFF",
    "surface2":     "#F0EEE9",
    "border":       "#E0DDD6",
    "accent":       "#2563EB",
    "accent_hover": "#1D4ED8",
    "accent_light": "#EFF6FF",
    "success":      "#16A34A",
    "success_bg":   "#F0FDF4",
    "error":        "#DC2626",
    "error_bg":     "#FEF2F2",
    "warn":         "#D97706",
    "text":         "#1C1917",
    "text2":        "#57534E",
    "text3":        "#A8A29E",
    "cams":         "#7C3AED",
    "cams_light":   "#F5F3FF",
    "karvy":        "#0F766E",
    "karvy_light":  "#F0FDFA",
}

FONT_BODY  = ("Segoe UI", 10)
FONT_BOLD  = ("Segoe UI", 10, "bold")
FONT_SMALL = ("Segoe UI", 9)
FONT_HEAD  = ("Segoe UI", 13, "bold")
FONT_MONO  = ("Consolas", 9)


class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, _=None):
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        lbl = tk.Label(tw, text=self.text, background="#FFFBEB",
                       relief="flat", font=FONT_SMALL, padx=8, pady=4,
                       foreground=C["text"], wraplength=280)
        lbl.pack()

    def hide(self, _=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class SectionFrame(tk.Frame):
    """Labelled card section."""
    def __init__(self, parent, title, accent=C["accent"], **kw):
        super().__init__(parent, bg=C["surface"],
                         highlightbackground=C["border"],
                         highlightthickness=1, **kw)
        hdr = tk.Frame(self, bg=accent, height=3)
        hdr.pack(fill="x")
        tk.Label(self, text=title, font=FONT_BOLD,
                 bg=C["surface"], fg=C["text"],
                 pady=6, padx=12, anchor="w").pack(fill="x")
        sep = tk.Frame(self, bg=C["border"], height=1)
        sep.pack(fill="x")
        self.body = tk.Frame(self, bg=C["surface"], padx=12, pady=10)
        self.body.pack(fill="both", expand=True)


class LogBox(tk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=C["surface"],
                         highlightbackground=C["border"],
                         highlightthickness=1, **kw)
        header = tk.Frame(self, bg=C["surface2"], pady=6, padx=10)
        header.pack(fill="x")
        tk.Label(header, text="Activity log", font=FONT_BOLD,
                 bg=C["surface2"], fg=C["text"]).pack(side="left")
        self._clear_btn = tk.Button(
            header, text="Clear", font=FONT_SMALL,
            bg=C["surface2"], fg=C["text2"], relief="flat",
            cursor="hand2", command=self.clear, bd=0, padx=6)
        self._clear_btn.pack(side="right")

        self.text = tk.Text(
            self, font=FONT_MONO, bg=C["surface"], fg=C["text"],
            relief="flat", wrap="none", state="disabled",
            height=14, padx=8, pady=6,
            selectbackground=C["accent_light"],
        )
        sb = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.text.pack(fill="both", expand=True)

        self.text.tag_config("ok",    foreground=C["success"])
        self.text.tag_config("err",   foreground=C["error"])
        self.text.tag_config("info",  foreground=C["accent"])
        self.text.tag_config("warn",  foreground=C["warn"])
        self.text.tag_config("head",  foreground=C["text"], font=FONT_BOLD)

    def append(self, line: str, tag=""):
        self.text.configure(state="normal")
        self.text.insert("end", line + "\n", tag)
        self.text.see("end")
        self.text.configure(state="disabled")

    def clear(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")


class DBFSplitterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DBF Splitter")
        self.configure(bg=C["bg"])
        self.resizable(True, True)
        self.minsize(700, 640)

        self._mode = tk.StringVar(value="cams")
        self._input_path = tk.StringVar()
        self._output_dir = tk.StringVar()
        self._field_num = tk.IntVar(value=77)
        self._tiff_path = tk.StringVar()
        self._create_zips = tk.BooleanVar(value=False)
        self._karvy_tiff_path = tk.StringVar()
        self._karvy_split_results = []   # stored after karvy split completes
        self._karvy_out_dir = ""
        self._running = False
        self._header_cache = None

        self._build_ui()
        self.geometry("780x720")

    # ─── UI construction ──────────────────────────────────────

    def _build_ui(self):
        # Top bar
        top = tk.Frame(self, bg=C["text"], pady=12, padx=16)
        top.pack(fill="x")
        tk.Label(top, text="DBF Splitter",
                 font=("Segoe UI", 14, "bold"),
                 bg=C["text"], fg="white").pack(side="left")
        tk.Label(top, text="CAMS & Karvy",
                 font=FONT_SMALL, bg=C["text"], fg=C["text3"]).pack(side="left", padx=10)

        # Scrollable main area
        canvas = tk.Canvas(self, bg=C["bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self._main = tk.Frame(canvas, bg=C["bg"], padx=16, pady=14)
        self._win_id = canvas.create_window((0, 0), window=self._main, anchor="nw")

        self._main.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
            lambda e: canvas.itemconfig(self._win_id, width=e.width))
        canvas.bind_all("<MouseWheel>",
            lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        self._build_mode_selector()
        self._build_file_section()
        self._build_cams_section()
        self._build_karvy_section()
        self._build_karvy_zip_section()
        self._build_preview_section()
        self._build_run_section()
        self._build_log()

        self._mode.trace_add("write", self._on_mode_change)
        self._on_mode_change()

    def _build_mode_selector(self):
        f = tk.Frame(self._main, bg=C["bg"])
        f.pack(fill="x", pady=(0, 10))
        tk.Label(f, text="Splitting mode", font=FONT_BOLD,
                 bg=C["bg"], fg=C["text"]).pack(anchor="w", pady=(0, 6))

        btn_frame = tk.Frame(f, bg=C["bg"])
        btn_frame.pack(fill="x")

        self._cams_btn = self._mode_btn(
            btn_frame, "CAMS", "cams",
            "Names each output file using the value\nfrom a specified field in that row.",
            C["cams"], C["cams_light"],
        )
        self._cams_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self._karvy_btn = self._mode_btn(
            btn_frame, "Karvy", "karvy",
            "Names output files sequentially:\n1.dbf, 2.dbf, 3.dbf ...",
            C["karvy"], C["karvy_light"],
        )
        self._karvy_btn.pack(side="left", fill="x", expand=True)

    def _mode_btn(self, parent, label, value, desc, accent, light):
        f = tk.Frame(parent, bg=C["surface"],
                     highlightbackground=C["border"],
                     highlightthickness=1, cursor="hand2", padx=14, pady=10)
        f.bind("<Button-1>", lambda _: self._mode.set(value))

        top_row = tk.Frame(f, bg=C["surface"])
        top_row.pack(fill="x")

        rb = tk.Radiobutton(
            top_row, variable=self._mode, value=value,
            bg=C["surface"], activebackground=C["surface"],
            highlightthickness=0,
        )
        rb.pack(side="left")
        tk.Label(top_row, text=label, font=FONT_BOLD,
                 bg=C["surface"], fg=C["text"]).pack(side="left")

        tk.Label(f, text=desc, font=FONT_SMALL, bg=C["surface"],
                 fg=C["text2"], justify="left", wraplength=240).pack(anchor="w", pady=(4, 0))

        f._accent = accent
        f._light  = light
        f._value  = value
        f._rb     = rb
        return f

    def _build_file_section(self):
        sec = SectionFrame(self._main, "File selection")
        sec.pack(fill="x", pady=(0, 10))
        b = sec.body

        # Input file
        tk.Label(b, text="Input DBF file", font=FONT_SMALL,
                 bg=C["surface"], fg=C["text2"]).grid(row=0, column=0, sticky="w")
        inp = tk.Frame(b, bg=C["surface"])
        inp.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 8))
        self._inp_entry = tk.Entry(
            inp, textvariable=self._input_path, font=FONT_BODY,
            bg=C["surface2"], fg=C["text"], relief="flat",
            highlightbackground=C["border"], highlightthickness=1,
        )
        self._inp_entry.pack(side="left", fill="x", expand=True, ipady=5, padx=(0, 6))
        tk.Button(inp, text="Browse...", font=FONT_SMALL,
                  bg=C["accent"], fg="white", relief="flat",
                  activebackground=C["accent_hover"], activeforeground="white",
                  cursor="hand2", padx=10, pady=5,
                  command=self._browse_input).pack(side="right")

        # Output folder
        tk.Label(b, text="Output folder", font=FONT_SMALL,
                 bg=C["surface"], fg=C["text2"]).grid(row=2, column=0, sticky="w")
        out = tk.Frame(b, bg=C["surface"])
        out.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(2, 0))
        self._out_entry = tk.Entry(
            out, textvariable=self._output_dir, font=FONT_BODY,
            bg=C["surface2"], fg=C["text"], relief="flat",
            highlightbackground=C["border"], highlightthickness=1,
        )
        self._out_entry.pack(side="left", fill="x", expand=True, ipady=5, padx=(0, 6))
        tk.Button(out, text="Browse...", font=FONT_SMALL,
                  bg=C["surface2"], fg=C["text"], relief="flat",
                  cursor="hand2", padx=10, pady=5,
                  command=self._browse_output).pack(side="right")
        b.columnconfigure(0, weight=1)

    def _build_cams_section(self):
        self._cams_sec = SectionFrame(self._main, "CAMS options", accent=C["cams"])
        self._cams_sec.pack(fill="x", pady=(0, 10))
        b = self._cams_sec.body

        tk.Label(b, text="Field number to use as output filename",
                 font=FONT_SMALL, bg=C["surface"], fg=C["text2"]).grid(
                     row=0, column=0, sticky="w")

        spin_frame = tk.Frame(b, bg=C["surface"])
        spin_frame.grid(row=1, column=0, sticky="w", pady=(2, 8))
        self._field_spin = tk.Spinbox(
            spin_frame, from_=1, to=9999, textvariable=self._field_num,
            width=8, font=FONT_BODY, relief="flat",
            highlightbackground=C["border"], highlightthickness=1,
            bg=C["surface2"], fg=C["text"],
        )
        self._field_spin.pack(side="left", ipady=4)

        self._preview_btn = tk.Button(
            spin_frame, text="Preview fields >", font=FONT_SMALL,
            bg=C["cams_light"], fg=C["cams"], relief="flat",
            cursor="hand2", padx=8, pady=4,
            command=self._load_field_preview,
        )
        self._preview_btn.pack(side="left", padx=(8, 0))

        tk.Label(b, text="The tool auto-detects the total field count from the file.",
                 font=FONT_SMALL, bg=C["surface"], fg=C["text3"]).grid(
                     row=2, column=0, sticky="w", pady=(0, 10))

        # Separator
        tk.Frame(b, bg=C["border"], height=1).grid(
            row=3, column=0, sticky="ew", pady=(0, 10))

        # ZIP creation toggle
        zip_row = tk.Frame(b, bg=C["surface"])
        zip_row.grid(row=4, column=0, sticky="w", pady=(0, 8))
        self._zip_chk = tk.Checkbutton(
            zip_row, text="Create ZIP files after splitting",
            variable=self._create_zips,
            font=FONT_BOLD, bg=C["surface"], fg=C["cams"],
            activebackground=C["surface"], selectcolor=C["surface"],
            cursor="hand2", command=self._on_zip_toggle,
        )
        self._zip_chk.pack(side="left")

        # TIFF selection (shown only when zip is enabled)
        self._tiff_frame = tk.Frame(b, bg=C["surface"])
        self._tiff_frame.grid(row=5, column=0, sticky="ew", pady=(0, 4))

        tk.Label(self._tiff_frame, text="Master TIFF file  (copied into every ZIP)",
                 font=FONT_SMALL, bg=C["surface"], fg=C["text2"]).pack(anchor="w")
        tiff_row = tk.Frame(self._tiff_frame, bg=C["surface"])
        tiff_row.pack(fill="x", pady=(3, 0))
        self._tiff_entry = tk.Entry(
            tiff_row, textvariable=self._tiff_path, font=FONT_BODY,
            bg=C["surface2"], fg=C["text"], relief="flat",
            highlightbackground=C["border"], highlightthickness=1,
        )
        self._tiff_entry.pack(side="left", fill="x", expand=True, ipady=5, padx=(0, 6))
        tk.Button(tiff_row, text="Browse...", font=FONT_SMALL,
                  bg=C["cams_light"], fg=C["cams"], relief="flat",
                  cursor="hand2", padx=10, pady=5,
                  command=self._browse_tiff).pack(side="right")

        tk.Label(self._tiff_frame,
                 text="The TIFF will be renamed to match each output file and placed inside its ZIP folder.",
                 font=FONT_SMALL, bg=C["surface"], fg=C["text3"],
                 wraplength=500, justify="left").pack(anchor="w", pady=(4, 0))

        b.columnconfigure(0, weight=1)

        # Hide tiff frame initially
        self._tiff_frame.grid_remove()

    def _on_zip_toggle(self):
        if self._create_zips.get():
            self._tiff_frame.grid()
        else:
            self._tiff_frame.grid_remove()

    def _browse_tiff(self):
        path = filedialog.askopenfilename(
            title="Select master TIFF file",
            filetypes=[("TIFF files", "*.tiff *.tif"), ("All files", "*.*")],
        )
        if path:
            self._tiff_path.set(path)

    def _build_karvy_zip_section(self):
        self._karvy_zip_sec = SectionFrame(
            self._main, "Karvy — Step 2: Create ZIPs", accent=C["karvy"])
        self._karvy_zip_sec.pack(fill="x", pady=(0, 10))
        b = self._karvy_zip_sec.body

        # Status label shown before split is done
        self._karvy_zip_status = tk.Label(
            b, text="Complete Step 1 (split DBF) first, then create ZIPs here.",
            font=FONT_SMALL, bg=C["surface"], fg=C["text3"])
        self._karvy_zip_status.pack(anchor="w", pady=(0, 6))

        # Inner frame — locked until split done
        self._karvy_zip_inner = tk.Frame(b, bg=C["surface"])
        self._karvy_zip_inner.pack(fill="x")

        # Ref numbers + Folio numbers side by side
        cols = tk.Frame(self._karvy_zip_inner, bg=C["surface"])
        cols.pack(fill="x", pady=(0, 10))

        # Ref numbers
        lf = tk.Frame(cols, bg=C["surface"])
        lf.pack(side="left", fill="both", expand=True, padx=(0, 8))
        tk.Label(lf, text="Reference numbers  (one per line)",
                 font=FONT_SMALL, bg=C["surface"], fg=C["text2"]).pack(anchor="w")
        tk.Label(lf, text="Used as ZIP name and folder name",
                 font=FONT_SMALL, bg=C["surface"], fg=C["text3"]).pack(anchor="w")
        self._ref_text = tk.Text(
            lf, font=FONT_MONO, height=8, width=22,
            bg=C["surface2"], fg=C["text"], relief="flat",
            highlightbackground=C["border"], highlightthickness=1,
            padx=6, pady=6,
        )
        self._ref_text.pack(fill="both", expand=True, pady=(4, 0))

        # Folio numbers
        rf = tk.Frame(cols, bg=C["surface"])
        rf.pack(side="left", fill="both", expand=True)
        tk.Label(rf, text="Folio numbers  (one per line)",
                 font=FONT_SMALL, bg=C["surface"], fg=C["text2"]).pack(anchor="w")
        tk.Label(rf, text="Used as TIFF filename inside folder",
                 font=FONT_SMALL, bg=C["surface"], fg=C["text3"]).pack(anchor="w")
        self._folio_text = tk.Text(
            rf, font=FONT_MONO, height=8, width=22,
            bg=C["surface2"], fg=C["text"], relief="flat",
            highlightbackground=C["border"], highlightthickness=1,
            padx=6, pady=6,
        )
        self._folio_text.pack(fill="both", expand=True, pady=(4, 0))

        # TIFF selection
        tk.Label(self._karvy_zip_inner, text="Master TIFF file",
                 font=FONT_SMALL, bg=C["surface"], fg=C["text2"]).pack(anchor="w")
        tiff_row = tk.Frame(self._karvy_zip_inner, bg=C["surface"])
        tiff_row.pack(fill="x", pady=(3, 10))
        self._karvy_tiff_entry = tk.Entry(
            tiff_row, textvariable=self._karvy_tiff_path, font=FONT_BODY,
            bg=C["surface2"], fg=C["text"], relief="flat",
            highlightbackground=C["border"], highlightthickness=1,
        )
        self._karvy_tiff_entry.pack(side="left", fill="x", expand=True, ipady=5, padx=(0, 6))
        tk.Button(tiff_row, text="Browse...", font=FONT_SMALL,
                  bg=C["karvy_light"], fg=C["karvy"], relief="flat",
                  cursor="hand2", padx=10, pady=5,
                  command=self._browse_karvy_tiff).pack(side="right")

        # Create ZIPs button
        self._karvy_zip_btn = tk.Button(
            self._karvy_zip_inner,
            text="Create ZIPs",
            font=("Segoe UI", 11, "bold"),
            bg=C["karvy"], fg="white", relief="flat",
            activebackground="#0D5C52", activeforeground="white",
            cursor="hand2", padx=20, pady=10,
            command=self._start_karvy_zips,
        )
        self._karvy_zip_btn.pack(anchor="w")

        # Lock inner frame initially
        self._set_karvy_zip_locked(True)

    def _set_karvy_zip_locked(self, locked: bool):
        state = "disabled" if locked else "normal"
        for widget in self._iter_widgets(self._karvy_zip_inner):
            try:
                widget.configure(state=state)
            except Exception:
                pass
        if locked:
            self._karvy_zip_status.configure(
                text="Complete Step 1 (split DBF) first, then create ZIPs here.",
                fg=C["text3"])
        else:
            count = len(self._karvy_split_results)
            self._karvy_zip_status.configure(
                text=f"Step 1 done — {count} DBF(s) split. Now fill in ref/folio numbers and create ZIPs.",
                fg=C["success"])

    def _iter_widgets(self, parent):
        """Recursively yield all child widgets."""
        for child in parent.winfo_children():
            yield child
            yield from self._iter_widgets(child)

    def _browse_karvy_tiff(self):
        path = filedialog.askopenfilename(
            title="Select master TIFF file",
            filetypes=[("TIFF files", "*.tiff *.tif"), ("All files", "*.*")],
        )
        if path:
            self._karvy_tiff_path.set(path)

    def _start_karvy_zips(self):
        if self._running:
            return

        tiff = self._karvy_tiff_path.get()
        if not tiff:
            messagebox.showerror("Missing TIFF", "Please select a master TIFF file.")
            return
        if not os.path.exists(tiff):
            messagebox.showerror("TIFF not found", f"Cannot find:\n{tiff}")
            return

        # Parse ref and folio numbers
        ref_numbers = [l.strip() for l in self._ref_text.get("1.0", "end").splitlines()
                       if l.strip()]
        folio_numbers = [l.strip() for l in self._folio_text.get("1.0", "end").splitlines()
                         if l.strip()]

        n = len(self._karvy_split_results)

        if len(ref_numbers) == 0:
            messagebox.showerror("Missing data", "Please enter reference numbers.")
            return
        if len(folio_numbers) == 0:
            messagebox.showerror("Missing data", "Please enter folio numbers.")
            return
        if len(ref_numbers) != n:
            messagebox.showerror(
                "Count mismatch",
                f"Reference numbers: {len(ref_numbers)}\n"
                f"Split DBFs: {n}\n\n"
                f"These must match exactly.")
            return
        if len(folio_numbers) != n:
            messagebox.showerror(
                "Count mismatch",
                f"Folio numbers: {len(folio_numbers)}\n"
                f"Split DBFs: {n}\n\n"
                f"These must match exactly.")
            return

        self._running = True
        self._karvy_zip_btn.configure(state="disabled", text="Creating ZIPs...")
        self._progress["value"] = 0
        self._log.append("-" * 60, "head")
        self._log.append(f"  Karvy ZIP creation — {n} ZIPs to create", "info")

        threading.Thread(
            target=self._run_karvy_zips,
            args=(ref_numbers, folio_numbers, tiff, self._karvy_out_dir),
            daemon=True,
        ).start()

    def _run_karvy_zips(self, ref_numbers, folio_numbers, tiff, out_dir):
        ok = err = 0
        try:
            def progress(done, total_):
                pct = min(100, int(done / max(total_, 1) * 100))
                self.after(0, self._set_progress, pct, done, total_)

            for zresult in create_karvy_zips(
                self._karvy_split_results, ref_numbers, folio_numbers,
                tiff, out_dir, progress
            ):
                if zresult.success:
                    ok += 1
                    self.after(0, self._log.append,
                               f"  ZIP  {zresult.name}.zip", "ok")
                else:
                    err += 1
                    self.after(0, self._log.append,
                               f"  ERR  {zresult.name}: {zresult.error}", "err")

        except ValueError as ve:
            self.after(0, self._log.append, f"x  {ve}", "err")
            self.after(0, self._finish_karvy_zips, 0, 1)
            return
        except Exception as e:
            self.after(0, self._log.append, f"x  Fatal error: {e}", "err")
            err += 1

        self.after(0, self._finish_karvy_zips, ok, err)

    def _finish_karvy_zips(self, ok, err):
        self._running = False
        self._karvy_zip_btn.configure(state="normal", text="Create ZIPs")
        self._progress["value"] = 100
        tag = "ok" if err == 0 else "warn"
        self._log.append("-" * 60, "head")
        self._log.append(f"  ZIPs done.  {ok} created.  {err} error(s).", tag)
        self._status_lbl.configure(text=f"ZIPs done - {ok} created, {err} errors")


        self._karvy_sec = SectionFrame(self._main, "Karvy options", accent=C["karvy"])
        self._karvy_sec.pack(fill="x", pady=(0, 10))
        b = self._karvy_sec.body

        tk.Label(b, text="Output files are named using the AMC code from column 1 of each row.",
                 font=FONT_SMALL, bg=C["surface"], fg=C["text2"]).pack(anchor="w")
        tk.Label(b,
                 text="If multiple rows share the same AMC code, suffixes _2, _3 ... are added automatically.",
                 font=FONT_SMALL, bg=C["surface"], fg=C["text3"]).pack(anchor="w", pady=(4, 0))
        tk.Label(b, text='Example: HDFC.dbf, ICICI.dbf, HDFC_2.dbf, HDFC_3.dbf ...',
                 font=FONT_SMALL, bg=C["surface"], fg=C["text3"]).pack(anchor="w", pady=(4, 0))

    def _build_preview_section(self):
        self._prev_sec = SectionFrame(self._main, "Field preview")
        self._prev_sec.pack(fill="x", pady=(0, 10))
        b = self._prev_sec.body

        self._prev_table = tk.Frame(b, bg=C["surface"])
        self._prev_table.pack(fill="x")

        tk.Label(b, text="Load a file and click 'Preview fields' to see field definitions.",
                 font=FONT_SMALL, fg=C["text3"], bg=C["surface"]).pack(anchor="w", pady=4)

    def _build_run_section(self):
        f = tk.Frame(self._main, bg=C["bg"], pady=4)
        f.pack(fill="x", pady=(0, 10))

        self._run_btn = tk.Button(
            f, text="  Start splitting",
            font=("Segoe UI", 11, "bold"),
            bg=C["accent"], fg="white", relief="flat",
            activebackground=C["accent_hover"], activeforeground="white",
            cursor="hand2", padx=20, pady=10,
            command=self._start_split,
        )
        self._run_btn.pack(side="left")

        self._status_lbl = tk.Label(
            f, text="", font=FONT_SMALL, bg=C["bg"], fg=C["text2"])
        self._status_lbl.pack(side="left", padx=14)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("Custom.Horizontal.TProgressbar",
                         troughcolor=C["surface2"],
                         background=C["accent"],
                         thickness=6)
        self._progress = ttk.Progressbar(
            self._main, orient="horizontal",
            mode="determinate", style="Custom.Horizontal.TProgressbar",
        )
        self._progress.pack(fill="x", pady=(0, 8))

    def _build_log(self):
        self._log = LogBox(self._main)
        self._log.pack(fill="both", expand=True, pady=(0, 10))

    # ─── Mode switching ───────────────────────────────────────

    def _on_mode_change(self, *_):
        mode = self._mode.get()
        for btn in (self._cams_btn, self._karvy_btn):
            active = btn._value == mode
            btn.configure(
                bg=btn._light if active else C["surface"],
                highlightbackground=btn._accent if active else C["border"],
                highlightthickness=2 if active else 1,
            )
            for child in btn.winfo_children():
                child.configure(bg=btn._light if active else C["surface"])

        if mode == "cams":
            self._cams_sec.pack(fill="x", pady=(0, 10), before=self._prev_sec)
            self._karvy_sec.pack_forget()
            self._karvy_zip_sec.pack_forget()
        else:
            self._karvy_sec.pack(fill="x", pady=(0, 10), before=self._prev_sec)
            self._karvy_zip_sec.pack(fill="x", pady=(0, 10), before=self._prev_sec)
            self._cams_sec.pack_forget()

    # ─── File browsing ────────────────────────────────────────

    def _browse_input(self):
        path = filedialog.askopenfilename(
            title="Select DBF file",
            filetypes=[("DBF files", "*.dbf"), ("All files", "*.*")],
        )
        if path:
            self._input_path.set(path)
            if not self._output_dir.get():
                self._output_dir.set(os.path.dirname(path))
            self._load_field_preview()

    def _browse_output(self):
        path = filedialog.askdirectory(title="Select output folder")
        if path:
            self._output_dir.set(path)

    # ─── Field preview ────────────────────────────────────────

    def _load_field_preview(self):
        path = self._input_path.get()
        if not path or not os.path.exists(path):
            self._log.append("  Please select a valid DBF file first.", "warn")
            return
        try:
            hdr = read_dbf_header(path)
            self._header_cache = hdr
            self._render_preview(hdr)
            self._log.append(
                f"i  Loaded: {os.path.basename(path)}  |  "
                f"{len(hdr.fields)} fields  |  {hdr.num_records} records",
                "info",
            )
        except Exception as e:
            self._log.append(f"x  Could not read header: {e}", "err")

    def _render_preview(self, hdr):
        for w in self._prev_table.winfo_children():
            w.destroy()

        headers = ["#", "Field name", "Type", "Length", "Decimal"]
        widths   = [4,   20,           6,      7,         8]
        for col, (h, w) in enumerate(zip(headers, widths)):
            tk.Label(self._prev_table, text=h, font=FONT_BOLD,
                     bg=C["surface2"], fg=C["text2"],
                     width=w, anchor="w", padx=4, pady=3,
                     relief="flat").grid(row=0, column=col, sticky="ew", padx=1, pady=(0, 1))

        selected_num = self._field_num.get()
        for i, (name, ftype, flen, fdec) in enumerate(hdr.fields[:80]):
            num = i + 1
            is_sel = (num == selected_num) and self._mode.get() == "cams"
            bg = C["cams_light"] if is_sel else (C["surface"] if i % 2 == 0 else C["surface2"])
            fg = C["cams"]       if is_sel else C["text"]
            vals = [str(num), name, ftype, str(flen), str(fdec)]
            for col, (v, w) in enumerate(zip(vals, widths)):
                lbl = tk.Label(self._prev_table, text=v,
                               font=FONT_SMALL if col > 0 else FONT_BOLD,
                               bg=bg, fg=fg, width=w, anchor="w", padx=4, pady=2)
                lbl.grid(row=i + 1, column=col, sticky="ew", padx=1, pady=0)

        if len(hdr.fields) > 80:
            tk.Label(self._prev_table,
                     text=f"... {len(hdr.fields) - 80} more fields not shown",
                     font=FONT_SMALL, bg=C["surface"], fg=C["text3"],
                     anchor="w", padx=4, pady=3,
                     ).grid(row=82, column=0, columnspan=5, sticky="ew")

    # ─── Splitting ────────────────────────────────────────────

    def _start_split(self):
        if self._running:
            return

        path = self._input_path.get()
        out_dir = self._output_dir.get() or os.path.dirname(path)

        if not path:
            messagebox.showerror("Missing input", "Please select a DBF file.")
            return
        if not os.path.exists(path):
            messagebox.showerror("File not found", f"Cannot find:\n{path}")
            return

        # Validate TIFF if zip creation is enabled (CAMS only)
        if self._mode.get() == "cams" and self._create_zips.get():
            tiff = self._tiff_path.get()
            if not tiff:
                messagebox.showerror("Missing TIFF", "Please select a master TIFF file for ZIP creation.")
                return
            if not os.path.exists(tiff):
                messagebox.showerror("TIFF not found", f"Cannot find:\n{tiff}")
                return

        self._running = True
        self._run_btn.configure(state="disabled", text="Processing...")
        self._progress["value"] = 0
        self._log.append("-" * 60, "head")
        self._log.append(f"  Starting split  ({self._mode.get().upper()} mode)", "info")
        self._log.append(f"   Input : {path}", "")
        self._log.append(f"   Output: {out_dir}", "")

        mode = self._mode.get()
        threading.Thread(
            target=self._run_split,
            args=(path, out_dir, mode),
            daemon=True,
        ).start()

    def _run_split(self, path, out_dir, mode):
        ok = err = 0
        split_results = []
        try:
            hdr = read_dbf_header(path)
            total = hdr.num_records or 1

            def progress(done, total_):
                pct = min(100, int(done / max(total_, 1) * 100))
                self.after(0, self._set_progress, pct, done, total_)

            if mode == "cams":
                field_num = self._field_num.get()
                if field_num < 1 or field_num > len(hdr.fields):
                    self.after(0, self._log.append,
                               f"x  Field {field_num} does not exist "
                               f"(file has {len(hdr.fields)} fields).", "err")
                    self.after(0, self._finish_split, 0, 1, mode, [])
                    return
                gen = split_cams(path, field_num, out_dir, progress)
            else:
                gen = split_karvy(
                    path, out_dir,
                    progress_callback=progress,
                )

            for result in gen:
                if result.success:
                    ok += 1
                    split_results.append(result)
                    fname = os.path.basename(result.output_file)
                    self.after(0, self._log.append,
                               f"  OK  Row {result.row_index + 1:>5}  ->  {fname}", "ok")
                else:
                    err += 1
                    self.after(0, self._log.append,
                               f"  ERR Row {result.row_index + 1}: {result.error}", "err")

            # CAMS ZIP creation (automatic, if enabled)
            if mode == "cams" and self._create_zips.get() and split_results:
                tiff = self._tiff_path.get()
                self.after(0, self._log.append, "-" * 60, "head")
                self.after(0, self._log.append,
                           f"  Creating {len(split_results)} ZIP file(s)...", "info")
                self.after(0, self._set_progress, 0, 0, len(split_results))

                zip_ok = zip_err = 0

                def zip_progress(done, total_):
                    pct = min(100, int(done / max(total_, 1) * 100))
                    self.after(0, self._set_progress, pct, done, total_)

                for zresult in create_cams_zips(split_results, tiff, out_dir, zip_progress):
                    if zresult.success:
                        zip_ok += 1
                        self.after(0, self._log.append,
                                   f"  ZIP  {zresult.name}.zip", "ok")
                    else:
                        zip_err += 1
                        self.after(0, self._log.append,
                                   f"  ERR  {zresult.name}: {zresult.error}", "err")

                self.after(0, self._log.append,
                           f"  ZIPs done.  {zip_ok} created.  {zip_err} error(s).",
                           "ok" if zip_err == 0 else "warn")

        except Exception as e:
            self.after(0, self._log.append, f"x  Fatal error: {e}", "err")
            err += 1

        self.after(0, self._finish_split, ok, err, mode, split_results)

    def _set_progress(self, pct, done, total):
        self._progress["value"] = pct
        self._status_lbl.configure(
            text=f"{done} / {total} rows  ({pct}%)")

    def _finish_split(self, ok, err, mode="", split_results=None):
        self._running = False
        self._run_btn.configure(state="normal", text="  Start splitting")
        self._progress["value"] = 100
        tag = "ok" if err == 0 else "warn"
        self._log.append("-" * 60, "head")
        self._log.append(
            f"  Done.  {ok} file(s) created.  {err} error(s).", tag)
        self._status_lbl.configure(
            text=f"Done - {ok} created, {err} errors")

        # Unlock Karvy ZIP section if karvy split succeeded
        if mode == "karvy" and split_results:
            self._karvy_split_results = split_results
            self._karvy_out_dir = self._output_dir.get() or os.path.dirname(
                self._input_path.get())
            self._set_karvy_zip_locked(False)


if __name__ == "__main__":
    app = DBFSplitterApp()
    app.mainloop()
