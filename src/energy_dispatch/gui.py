from __future__ import annotations

import json
import threading
from datetime import datetime
from tkinter import BOTH, END, EW, LEFT, NW, RAISED, RIGHT, S, Scrollbar, Tk, W, Y
from tkinter import ttk
from tkinter.filedialog import asksaveasfilename
from tkinter.messagebox import showinfo
from tkinter.scrolledtext import ScrolledText
from tkinter.ttk import Button, Frame, Label, Notebook, Progressbar

import numpy as np

from .cli import run_pipeline
from .config import RunConfig


# CJK font setup for matplotlib (same as cli.py)
def _setup_matplotlib_fonts() -> None:
    try:
        import matplotlib
        import matplotlib.font_manager

        for _font in ("Microsoft YaHei", "SimHei", "STHeiti", "WenQuanYi Micro Hei"):
            if _font in [f.name for f in matplotlib.font_manager.fontManager.ttflist]:
                matplotlib.rcParams["font.family"] = _font
                break
        matplotlib.rcParams["axes.unicode_minus"] = False
    except Exception:
        pass


class ResultsViewer:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("多时间尺度能源调度 / Multi-Timescale Energy Dispatch")
        self.root.geometry("1280x760")
        self.results: dict | None = None

        # Style
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TabBar.TNotebook", background="#2c3e50")
        style.configure("TabBar.TNotebook.Tab", background="#34495e", foreground="white", padding=[12, 6])
        style.configure("TabBar.TNotebook.Tab.selected", background="#1abc9c", foreground="white")
        style.configure("Info.TLabel", foreground="#2c3e50")
        style.configure("Section.TLabel", font=("Segoe UI", 10, "bold"), foreground="#1a1a2e")

        self._build_layout()

    def _build_layout(self) -> None:
        # ── Top control bar ────────────────────────────────────────
        top = Frame(self.root, padding=(8, 6, 8, 4), relief=RAISED, borderwidth=1)
        top.pack(side="top", fill="x")
        self._build_controls(top)

        # ── Main tab area ─────────────────────────────────────────
        nb = Notebook(self.root)
        nb.pack(side="bottom", fill=BOTH, expand=True, padx=8, pady=(0, 8))
        nb.configure(style="TabBar.TNotebook")

        self.tab_main = Frame(nb)
        self.tab_plot1 = Frame(nb)
        self.tab_plot2 = Frame(nb)
        nb.add(self.tab_main, text="摘要与日志 (Summary & Log)")
        nb.add(self.tab_plot1, text="前沿与调度 (Pareto & Dispatch)")
        nb.add(self.tab_plot2, text="日内 (Intraday)")

        self._build_main_tab()
        self._build_plot_tabs()

    def _build_controls(self, parent: Frame) -> None:
        def row(label_text: str, var, width: int = 6, padx: int = 2) -> None:
            Label(parent, text=label_text).pack(side=LEFT, padx=(0, padx))
            ttk.Entry(parent, textvariable=var, width=width).pack(side=LEFT, padx=(0, 10))

        self.pop_var = ttk.StringVar(value="80")
        self.gen_var = ttk.StringVar(value="100")
        self.seed_var = ttk.StringVar(value="42")

        row("种群规模 (Pop):", self.pop_var)
        row("迭代次数 (Gen):", self.gen_var)
        row("随机种子 (Seed):", self.seed_var)

        self.btn_run = Button(parent, text="运行 (Run)", command=self._on_run)
        self.btn_run.pack(side=LEFT, padx=(0, 4))
        self.btn_save_res = Button(parent, text="保存结果 (Save Results)", command=self._on_save_results, state="disabled")
        self.btn_save_res.pack(side=LEFT, padx=(0, 4))
        self.btn_save_fig = Button(parent, text="保存图片 (Save Figures)", command=self._on_save_figures, state="disabled")
        self.btn_save_fig.pack(side=LEFT, padx=(0, 4))
        Button(parent, text="清除 (Clear)", command=self._on_clear).pack(side=LEFT)

        self.prog = Progressbar(parent, mode="indeterminate", length=100)
        self.prog.pack(side=LEFT, padx=(14, 0))
        self.status_lbl = Label(parent, text="就绪 (Ready)", foreground="#555")
        self.status_lbl.pack(side=LEFT, padx=(10, 0))

    def _build_main_tab(self) -> None:
        """Left = metrics panel, Right = live log."""
        main = Frame(self.tab_main)
        main.pack(fill=BOTH, expand=True)

        # Left: metrics
        left = Frame(main, padding=(8, 8, 4, 8))
        left.pack(side=LEFT, fill=BOTH, expand=True)

        # Right: log
        right = Frame(main, padding=(4, 8, 8, 8))
        right.pack(side=RIGHT, fill=BOTH, expand=True)
        Label(right, text="运行日志 (Run Log)", style="Section.TLabel").pack(anchor="w", pady=(0, 4))
        self.log_txt = ScrolledText(right, wrap="word", height=35, font=("Consolas", 10))
        self.log_txt.pack(fill=BOTH, expand=True)

        # ── Metrics inside left ──────────────────────────────────
        row_idx = [0]

        def section(title: str) -> None:
            Label(left, text=title, style="Section.TLabel").grid(
                row=row_idx[0], column=0, columnspan=3, sticky="w", pady=(8, 4)
            )
            row_idx[0] += 1

        def kv(label_text: str, key: str) -> None:
            Label(left, text=label_text, anchor="w").grid(
                row=row_idx[0], column=0, columnspan=2, sticky="w", pady=1
            )
            val = Label(left, text="—", anchor="w", foreground="#2980b9", font=("Segoe UI", 9, "bold"))
            val.grid(row=row_idx[0], column=2, sticky="w", pady=1)
            setattr(self, f"lbl_{key}", val)
            row_idx[0] += 1

        section("日前调度 (Day-ahead)")
        kv("总成本 (CNY):", "day_cost")
        kv("总碳排放 (tCO2):", "day_carbon")
        kv("弃电率 (%):", "day_curt")
        kv("最大功率平衡误差 (MW):", "day_balance")
        kv("最终SOC (MWh):", "day_soc")
        kv("产氢量 (kg):", "day_h2")
        kv("供氨量 (kg):", "day_nh3")

        section("日内调度 (Intraday)")
        kv("储能切换次数:", "id_switch")
        kv("充电RMS偏差 (MW):", "id_ch_rms")
        kv("放电RMS偏差 (MW):", "id_dis_rms")
        kv("SOC RMS偏差 (MWh):", "id_soc_rms")
        kv("SOC最大偏差 (MWh):", "id_soc_max")
        kv("日内净不平衡RMS (MW):", "id_net_rms")
        kv("若直接执行日前RMS (MW):", "id_net_da")
        kv("已用后备方案:", "id_fallback")

        section("Pareto 解集 (Pareto Solutions)")
        kv("Pareto解数量:", "pareto_size")

        # Pareto table with row numbers and horizontal scroll
        table_frame = Frame(left)
        table_frame.grid(row=row_idx[0], column=0, columnspan=3, sticky="nsew", pady=(4, 0))
        left.grid_rowconfigure(row_idx[0], weight=1)

        h_scroll = Scrollbar(table_frame, orient="horizontal")
        h_scroll.pack(side=BOTTOM, fill="x")

        cols = ("idx", "cost", "carbon", "curtailment")
        self.pareto_table = ttk.Treeview(table_frame, columns=cols, show="headings", height=10, xscrollcommand=h_scroll.set)
        h_scroll.configure(command=self.pareto_table.xview)

        self.pareto_table.heading("idx", text="序号 (#)")
        self.pareto_table.heading("cost", text="成本 (CNY)")
        self.pareto_table.heading("carbon", text="碳排放 (tCO2)")
        self.pareto_table.heading("curtailment", text="弃电率 (%)")

        self.pareto_table.column("idx", width=50, anchor="center")
        self.pareto_table.column("cost", width=170)
        self.pareto_table.column("carbon", width=150)
        self.pareto_table.column("curtailment", width=120)

        self.pareto_table.pack(side=LEFT, fill=BOTH, expand=True)

        # Style table
        style = ttk.Style(self.pareto_table)
        style.configure("Treeview", rowheight=22)
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

    def _build_plot_tabs(self) -> None:
        _setup_matplotlib_fonts()
        try:
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            from matplotlib.figure import Figure
        except Exception as exc:
            for tab in (self.tab_plot1, self.tab_plot2):
                Label(tab, text=f"需要 matplotlib: {exc}").pack()
            self._canvas1 = self._canvas2 = None
            self._fig1 = self._fig2 = None
            return

        # Tab 1: Pareto + dispatch
        fig1 = Figure(figsize=(12, 7), dpi=100)
        fig1.subplots_adjust(left=0.07, right=0.97, top=0.93, bottom=0.10, wspace=0.35, hspace=0.40)
        axs1 = [fig1.add_subplot(2, 2, i + 1) for i in range(4)]
        self._fig1 = fig1
        self._axs1 = axs1
        self._canvas1 = FigureCanvasTkAgg(fig1, master=self.tab_plot1)
        self._canvas1.get_tk_widget().pack(fill=BOTH, expand=True)

        # Tab 2: intraday
        fig2 = Figure(figsize=(12, 4.5), dpi=100)
        fig2.subplots_adjust(left=0.05, right=0.98, top=0.85, bottom=0.15, wspace=0.30)
        axs2 = [fig2.add_subplot(1, 3, i + 1) for i in range(3)]
        self._fig2 = fig2
        self._axs2 = axs2
        self._canvas2 = FigureCanvasTkAgg(fig2, master=self.tab_plot2)
        self._canvas2.get_tk_widget().pack(fill=BOTH, expand=True)

    def _on_run(self) -> None:
        self.btn_run.configure(state="disabled")
        self.prog.start(8)
        self.status_lbl.configure(text="运行中... (Running...)")
        threading.Thread(target=self._run_worker, daemon=True).start()

    def _run_worker(self) -> None:
        try:
            pop = int(self.pop_var.get())
            gen = int(self.gen_var.get())
            seed = int(self.seed_var.get())
        except ValueError:
            self._log("错误：种群/代数/种子必须是整数\n")
            self._finish(None)
            return

        self._log(f"=== 开始运行 (Run started) ===\n")
        self._log(f"种群 (Pop)={pop}  代数 (Gen)={gen}  种子 (Seed)={seed}\n")
        self._log("-" * 36 + "\n")

        config = RunConfig(seed=seed, pop_size=pop, max_gen=gen, verbose=False, enable_plots=False)
        results = run_pipeline(config)

        self._log("=== 运行结束 (Run finished) ===\n")
        self._update_summary(results)
        self._update_plots(results)
        self._finish(results)

    def _finish(self, results: dict | None) -> None:
        self.root.after(0, self._do_finish, results)

    def _do_finish(self, results: dict | None) -> None:
        self.prog.stop()
        self.btn_run.configure(state="normal")
        self.status_lbl.configure(text="完成 (Done)" if results else "错误 (Error)")
        self.btn_save_res.configure(state="normal" if results else "disabled")
        self.btn_save_fig.configure(state="normal" if results else "disabled")
        self.results = results

    def _log(self, msg: str) -> None:
        self.root.after(0, lambda m=msg: (self.log_txt.insert(END, m), self.log_txt.see(END)))

    def _update_summary(self, r: dict) -> None:
        m = r["dayahead"]
        id_ = r["intraday"]
        po = r["pareto_objectives"]

        def s(key, val):
            getattr(self, f"lbl_{key}").configure(text=val)

        s("day_cost", f"{m.total_cost:,.2f}")
        s("day_carbon", f"{m.total_carbon:,.2f}")
        s("day_curt", f"{100*m.curtailment_ratio:.4f}")
        s("day_balance", f"{np.max(np.abs(m.power_balance)):.4f}")
        s("day_soc", f"{m.SOC[-1]:.2f}")
        s("day_h2", f"{np.sum(m.H2_prod):,.2f}")
        s("day_nh3", f"{np.sum(m.NH3_supply):,.2f}")
        s("id_switch", f"{id_['switch_count']}")
        s("id_ch_rms", f"{id_['charge_rms_dev']:.4f}")
        s("id_dis_rms", f"{id_['discharge_rms_dev']:.4f}")
        s("id_soc_rms", f"{id_['soc_rms_dev']:.4f}")
        s("id_soc_max", f"{id_['soc_max_dev']:.4f}")
        s("id_net_rms", f"{id_['net_rms_intraday']:.4f}")
        s("id_net_da", f"{id_['net_rms_if_day_ahead']:.4f}")
        s("id_fallback", "是 (Yes)" if id_["fallback_used"] else "否 (No)")
        s("pareto_size", f"{po.shape[0]}")

        for row in self.pareto_table.get_children():
            self.pareto_table.delete(row)
        for i in range(po.shape[0]):
            self.pareto_table.insert("", END, values=(
                i + 1,
                f"{po[i,0]:,.2f}",
                f"{po[i,1]:,.2f}",
                f"{po[i,2]*100:.4f}",
            ))

        self._log(f"  成本={m.total_cost:,.2f}  碳排={m.total_carbon:,.2f}  "
                  f"弃电率={100*m.curtailment_ratio:.4f}%\n")
        self._log(f"  Pareto解数量={po.shape[0]}\n")
        self._log(f"  日内回退={'是 (YES)' if id_['fallback_used'] else '否 (NO)'}\n")

    def _update_plots(self, r: dict) -> None:
        if r is None:
            return
        m = r["dayahead"]
        id_ = r["intraday"]
        po = r["pareto_objectives"]
        fo = r["final_population_objectives"]

        # ── Tab 1: Pareto + dispatch ─────────────────────────────
        for ax in self._axs1:
            ax.cla()
        ax1, ax2, ax3, ax4 = self._axs1

        ax1.scatter(fo[:, 0], fo[:, 1], s=12, c="#3498db", label="种群 (Population)")
        ax1.scatter(po[:, 0], po[:, 1], s=30, c="#e74c3c", label="Pareto前沿 (Pareto)")
        ax1.scatter([m.total_cost], [m.total_carbon], s=90, c="#27ae60", marker="s", label="选中解 (Selected)")
        ax1.set_xlabel("成本 (Cost)", fontsize=9)
        ax1.set_ylabel("碳排放 (Carbon)", fontsize=9)
        ax1.set_title("Pareto前沿 (Pareto Front)", fontsize=10, fontweight="bold")
        ax1.legend(fontsize=8)
        ax1.grid(True, alpha=0.3)

        ax2.plot(m.P_wind_actual, label="风电 (Wind)", linewidth=1.5)
        ax2.plot(m.P_solar_actual, label="光伏 (Solar)", linewidth=1.5)
        ax2.plot(m.P_thermal_total, label="火电 (Thermal)", linewidth=1.5)
        ax2.set_title("日前出力 (Day-ahead Output)", fontsize=10, fontweight="bold")
        ax2.legend(fontsize=8)
        ax2.set_xlabel("时段 (Hour)")
        ax2.set_ylabel("功率/MW (Power/MW)")
        ax2.grid(True, alpha=0.3)

        ax3.plot(m.P_charge, label="充电 (Charge)", linewidth=1.5)
        ax3.plot(m.P_discharge, label="放电 (Discharge)", linewidth=1.5)
        ax3.plot(m.P_P2G, label="电转气 (P2G)", linewidth=1.5)
        ax3.plot(m.P_P2A, label="电转氨 (P2A)", linewidth=1.5)
        ax3.plot(m.P_wind_curt, label="弃风 (Wind Curt.)", linewidth=1.0, linestyle="--", alpha=0.7)
        ax3.plot(m.P_solar_curt, label="弃光 (Solar Curt.)", linewidth=1.0, linestyle="--", alpha=0.7)
        ax3.set_title("灵活资源 (Flexible Resources)", fontsize=10, fontweight="bold")
        ax3.legend(fontsize=7, ncol=2)
        ax3.set_xlabel("时段 (Hour)")
        ax3.set_ylabel("功率/MW (Power/MW)")
        ax3.grid(True, alpha=0.3)

        ax4.plot(m.SOC[1:], label="SOC轨迹 (SOC)", linewidth=1.5, color="#8e44ad")
        ax4.axhline(m.SOC[0], color="gray", linestyle="--", linewidth=0.8, label="初始SOC (Initial)")
        ax4.set_title("储能SOC轨迹 (Battery SOC)", fontsize=10, fontweight="bold")
        ax4.legend(fontsize=8)
        ax4.set_xlabel("时段 (Hour)")
        ax4.set_ylabel("MWh")
        ax4.grid(True, alpha=0.3)

        self._fig1.suptitle("日前调度结果 (Day-ahead Dispatch Results)", fontweight="bold", fontsize=12)
        self._canvas1.draw()

        # ── Tab 2: Intraday ─────────────────────────────────────
        for ax in self._axs2:
            ax.cla()
        ax5, ax6, ax7 = self._axs2

        ax5.plot(id_["P_ch_day_ahead"], label="日前充电 (DA Charge)", linewidth=1.3)
        ax5.plot(id_["P_ch_intraday"], label="日内充电 (ID Charge)", linewidth=1.3, linestyle="--")
        ax5.plot(id_["P_dis_day_ahead"], label="日前放电 (DA Discharge)", linewidth=1.3)
        ax5.plot(id_["P_dis_intraday"], label="日内放电 (ID Discharge)", linewidth=1.3, linestyle="--")
        ax5.set_title("储能调度 (Storage Dispatch)", fontsize=10, fontweight="bold")
        ax5.legend(fontsize=8)
        ax5.set_xlabel("15分钟时段 (15-min)")
        ax5.set_ylabel("MW")
        ax5.grid(True, alpha=0.3)

        ax6.plot(id_["P_net_day_ahead"], label="日前基准 (DA)", linewidth=1.5)
        ax6.plot(id_["P_net_intraday"], label="日内校正 (ID)", linewidth=1.5, linestyle="--")
        ax6.set_title("净功率不平衡 (Net Imbalance)", fontsize=10, fontweight="bold")
        ax6.legend(fontsize=8)
        ax6.set_xlabel("15分钟时段 (15-min)")
        ax6.set_ylabel("MW")
        ax6.grid(True, alpha=0.3)

        t = np.arange(96) / 4
        ax7.plot(t, id_["P_wind_day_ahead"], label="日前风电 (DA Wind)", linewidth=1.2)
        ax7.plot(t, id_["P_wind_intraday_forecast"], label="日内风电 (ID Wind)", linewidth=1.0, alpha=0.7)
        ax7.plot(t, id_["P_solar_day_ahead"], label="日前光伏 (DA Solar)", linewidth=1.2)
        ax7.plot(t, id_["P_solar_intraday_forecast"], label="日内光伏 (ID Solar)", linewidth=1.0, alpha=0.7)
        ax7.plot(t, id_["P_load_day_ahead"], label="日前负荷 (DA Load)", linewidth=1.2)
        ax7.plot(t, id_["P_load_intraday_forecast"], label="日内负荷 (ID Load)", linewidth=1.0, alpha=0.7)
        ax7.set_title("预测对比 (Forecast Comparison)", fontsize=10, fontweight="bold")
        ax7.legend(fontsize=7, ncol=2)
        ax7.set_xlabel("小时 (Hour)")
        ax7.set_ylabel("MW")
        ax7.grid(True, alpha=0.3)

        self._fig2.suptitle("日内校正结果 (Intraday Adjustment Results)", fontweight="bold", fontsize=12)
        self._canvas2.draw()

    def _on_save_results(self) -> None:
        if self.results is None:
            return
        path = asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            initialfile=f"dispatch_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        )
        if not path:
            return
        from .cli import _to_serializable
        with open(path, "w", encoding="utf-8") as f:
            json.dump(_to_serializable(self.results), f, indent=2, ensure_ascii=False)
        showinfo("已保存 (Saved)", f"Results saved to:\n{path}")

    def _on_save_figures(self) -> None:
        if self.results is None:
            return
        path = asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf"), ("PNG", "*.png")],
            initialfile=f"dispatch_figures_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        )
        if not path:
            return
        if path.endswith(".pdf"):
            try:
                from matplotlib.backends.backend_pdf import PdfPages
                with PdfPages(path) as pdf:
                    pdf.savefig(self._fig1, dpi=150, bbox_inches="tight")
                    pdf.savefig(self._fig2, dpi=150, bbox_inches="tight")
            except Exception:
                self._save_png(path)
        else:
            self._save_png(path)
        showinfo("已保存 (Saved)", f"Figures saved to:\n{path}")

    def _save_png(self, base: str) -> None:
        p2 = base.replace(".png", "") + "_intraday.png"
        self._fig1.savefig(base, dpi=150, bbox_inches="tight")
        self._fig2.savefig(p2, dpi=150, bbox_inches="tight")

    def _on_clear(self) -> None:
        self.log_txt.delete("1.0", END)
        self.results = None
        self.status_lbl.configure(text="就绪 (Ready)")
        self.btn_save_res.configure(state="disabled")
        self.btn_save_fig.configure(state="disabled")
        for key in [
            "day_cost", "day_carbon", "day_curt", "day_balance", "day_soc",
            "day_h2", "day_nh3", "id_switch", "id_ch_rms", "id_dis_rms",
            "id_soc_rms", "id_soc_max", "id_net_rms", "id_net_da",
            "id_fallback", "pareto_size",
        ]:
            getattr(self, f"lbl_{key}").configure(text="—")
        for row in self.pareto_table.get_children():
            self.pareto_table.delete(row)
        if hasattr(self, "_fig1") and self._fig1:
            for ax in self._axs1:
                ax.cla()
            self._canvas1.draw()
        if hasattr(self, "_fig2") and self._fig2:
            for ax in self._axs2:
                ax.cla()
            self._canvas2.draw()


def launch_gui() -> None:
    root = Tk()
    ResultsViewer(root)
    root.mainloop()


if __name__ == "__main__":
    launch_gui()
