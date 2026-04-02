from __future__ import annotations

import io
import json
import sys
import threading
from datetime import datetime
from pathlib import Path
from tkinter import BOTH, END, NW, RAISED, Text, Tk, Y
from tkinter import font as tkfont
from tkinter import ttk, StringVar
from tkinter.filedialog import asksaveasfilename
from tkinter.messagebox import showinfo
from tkinter.scrolledtext import ScrolledText
from tkinter.ttk import Button, Frame, Label, Notebook, Progressbar

import numpy as np

from .cli import run_pipeline
from .config import RunConfig


class ResultsViewer:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("Multi-Timescale Energy Dispatch / 多时间尺度能源调度")
        self.root.geometry("1100x740")
        self.results: dict | None = None
        self._build_layout()

    def _build_layout(self) -> None:
        top = Frame(self.root)
        top.pack(side="top", fill="x", padx=8, pady=6)
        self._build_controls(top)

        nb = Notebook(self.root)
        nb.pack(side="bottom", fill=BOTH, expand=True, padx=8, pady=(0, 8))

        self.tab_summary = Frame(nb)
        self.tab_log = Frame(nb)
        self.tab_plot1 = Frame(nb)
        self.tab_plot2 = Frame(nb)
        nb.add(self.tab_summary, text="Summary / 摘要")
        nb.add(self.tab_log, text="Log / 日志")
        nb.add(self.tab_plot1, text="Pareto & Dispatch / 前沿与调度")
        nb.add(self.tab_plot2, text="Intraday / 日内")

        self._build_summary_tab()
        self._build_log_tab()
        self._build_plot_tabs()

    def _build_controls(self, parent: Frame) -> None:
        Label(parent, text="Pop:").pack(side="left")
        self.pop_var = StringVar(value="80")
        ttk.Entry(parent, textvariable=self.pop_var, width=6).pack(side="left", padx=(2, 8))

        Label(parent, text="Gen:").pack(side="left")
        self.gen_var = StringVar(value="100")
        ttk.Entry(parent, textvariable=self.gen_var, width=6).pack(side="left", padx=(2, 8))

        Label(parent, text="Seed:").pack(side="left")
        self.seed_var = StringVar(value="42")
        ttk.Entry(parent, textvariable=self.seed_var, width=6).pack(side="left", padx=(2, 12))

        self.btn_run = Button(parent, text="Run / 运行", command=self._on_run)
        self.btn_run.pack(side="left", padx=(0, 4))
        self.btn_save_res = Button(parent, text="Save Results / 保存结果", command=self._on_save_results, state="disabled")
        self.btn_save_res.pack(side="left", padx=(0, 4))
        self.btn_save_fig = Button(parent, text="Save Figures / 保存图片", command=self._on_save_figures, state="disabled")
        self.btn_save_fig.pack(side="left", padx=(0, 4))
        Button(parent, text="Clear / 清除", command=self._on_clear).pack(side="left")

        self.prog = Progressbar(parent, mode="indeterminate", length=120)
        self.prog.pack(side="left", padx=(12, 0))

        self.status_lbl = Label(parent, text="Ready / 就绪")
        self.status_lbl.pack(side="left", padx=(12, 0))

    def _build_summary_tab(self) -> None:
        container = Frame(self.tab_summary)
        container.pack(fill=BOTH, expand=True, padx=10, pady=10)

        row = 0

        Label(container, text="Day-ahead / 日前调度", font=("Segoe UI", 11, "bold")
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 6)); row += 1

        self._kv("Total Cost / 总成本 (CNY):", "day_cost", row, container); row += 1
        self._kv("Total Carbon / 总碳排放 (tCO2):", "day_carbon", row, container); row += 1
        self._kv("Curtailment / 弃电率:", "day_curt", row, container); row += 1
        self._kv("Max Balance Error / 最大平衡误差 (MW):", "day_balance", row, container); row += 1
        self._kv("Final SOC / 最终SOC (MWh):", "day_soc", row, container); row += 1
        self._kv("H2 Production / 产氢量 (kg):", "day_h2", row, container); row += 1
        self._kv("NH3 Supply / 供氨量 (kg):", "day_nh3", row, container); row += 1

        row += 1
        Label(container, text="Intraday / 日内调度", font=("Segoe UI", 11, "bold")
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 6)); row += 1

        self._kv("Switch Count / 储能切换次数:", "id_switch", row, container); row += 1
        self._kv("Charge RMS Dev / 充电RMS偏差 (MW):", "id_ch_rms", row, container); row += 1
        self._kv("Discharge RMS Dev / 放电RMS偏差 (MW):", "id_dis_rms", row, container); row += 1
        self._kv("SOC RMS Dev / SOC RMS偏差 (MWh):", "id_soc_rms", row, container); row += 1
        self._kv("SOC Max Dev / SOC最大偏差 (MWh):", "id_soc_max", row, container); row += 1
        self._kv("Net RMS Intraday / 日内净不平衡RMS (MW):", "id_net_rms", row, container); row += 1
        self._kv("Net RMS Day-ahead / 若直接执行日前 (MW):", "id_net_da", row, container); row += 1
        self._kv("Fallback Used / 已用后备方案:", "id_fallback", row, container); row += 1

        row += 1
        Label(container, text="Pareto / Pareto解集", font=("Segoe UI", 11, "bold")
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 6)); row += 1

        self._kv("Pareto Size / Pareto解数量:", "pareto_size", row, container); row += 1

        self.pareto_table = ttk.Treeview(
            container,
            columns=("cost", "carbon", "curtailment"),
            show="headings",
            height=12,
        )
        self.pareto_table.heading("cost", text="Cost / 成本 (CNY)")
        self.pareto_table.heading("carbon", text="Carbon / 碳排 (tCO2)")
        self.pareto_table.heading("curtailment", text="Curtailment / 弃电率")
        self.pareto_table.column("cost", width=170)
        self.pareto_table.column("carbon", width=150)
        self.pareto_table.column("curtailment", width=140)
        self.pareto_table.grid(row=row, column=0, columnspan=2, sticky="nsew", pady=(4, 0))
        container.grid_rowconfigure(row, weight=1)
        container.grid_columnconfigure(1, weight=1)

    def _kv(self, label_text: str, key: str, row: int, parent: Frame) -> None:
        Label(parent, text=label_text, anchor="w").grid(row=row, column=0, sticky="w", pady=2)
        val = Label(parent, text="—", anchor="w", foreground="#555")
        val.grid(row=row, column=1, sticky="w", pady=2)
        setattr(self, f"lbl_{key}", val)

    def _build_log_tab(self) -> None:
        txt = ScrolledText(self.tab_log, wrap="word", height=30, font=("Consolas", 10))
        txt.pack(fill=BOTH, expand=True, padx=6, pady=6)
        self.log_txt = txt

    def _build_plot_tabs(self) -> None:
        try:
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            from matplotlib.figure import Figure
        except Exception as exc:
            Label(self.tab_plot1, text=f"matplotlib required: {exc}").pack()
            Label(self.tab_plot2, text=f"matplotlib required: {exc}").pack()
            self._canvas1 = self._canvas2 = None
            self._fig1 = self._fig2 = None
            return

        fig1 = Figure(figsize=(10, 6), dpi=100)
        fig1.subplots_adjust(left=0.08, right=0.95, top=0.90, bottom=0.12)
        axs1 = [fig1.add_subplot(2, 2, i + 1) for i in range(4)]
        self._fig1 = fig1
        self._axs1 = axs1
        self._canvas1 = FigureCanvasTkAgg(fig1, master=self.tab_plot1)
        self._canvas1.get_tk_widget().pack(fill=BOTH, expand=True)

        fig2 = Figure(figsize=(10, 4), dpi=100)
        fig2.subplots_adjust(left=0.07, right=0.96, top=0.86, bottom=0.14)
        axs2 = [fig2.add_subplot(1, 3, i + 1) for i in range(3)]
        self._fig2 = fig2
        self._axs2 = axs2
        self._canvas2 = FigureCanvasTkAgg(fig2, master=self.tab_plot2)
        self._canvas2.get_tk_widget().pack(fill=BOTH, expand=True)

    def _on_run(self) -> None:
        self.btn_run.configure(state="disabled")
        self.prog.start(8)
        self.status_lbl.configure(text="Running... / 运行中...")
        threading.Thread(target=self._run_worker, daemon=True).start()

    def _run_worker(self) -> None:
        try:
            pop = int(self.pop_var.get())
            gen = int(self.gen_var.get())
            seed = int(self.seed_var.get())
        except ValueError:
            self._log("Error: pop/gen/seed must be integers\n")
            self._finish(None)
            return

        self._log("=== Run started  / 开始运行 ===\n")
        self._log(f"Pop={pop}  Gen={gen}  Seed={seed}\n")
        self._log("-" * 42 + "\n")

        config = RunConfig(seed=seed, pop_size=pop, max_gen=gen, verbose=False, enable_plots=False)
        results = run_pipeline(config)

        self._log("=== Run finished / 运行结束 ===\n")
        self._update_summary(results)
        self._update_plots(results)
        self._finish(results)

    def _finish(self, results: dict | None) -> None:
        self.root.after(0, self._do_finish, results)

    def _do_finish(self, results: dict | None) -> None:
        self.prog.stop()
        self.btn_run.configure(state="normal")
        self.status_lbl.configure(text="Done / 完成" if results else "Error / 错误")
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
        s("day_curt", f"{100*m.curtailment_ratio:.4f}%")
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
        s("id_fallback", "Yes / 是" if id_["fallback_used"] else "No / 否")
        s("pareto_size", f"{po.shape[0]}")

        for row in self.pareto_table.get_children():
            self.pareto_table.delete(row)
        for i in range(po.shape[0]):
            self.pareto_table.insert("", END, values=(
                f"{po[i,0]:,.2f}",
                f"{po[i,1]:,.2f}",
                f"{po[i,2]*100:.4f}%",
            ))

        self._log(f"  Cost={m.total_cost:,.2f}  Carbon={m.total_carbon:,.2f}  "
                  f"Curtail={100*m.curtailment_ratio:.4f}%\n")
        self._log(f"  Pareto size={po.shape[0]}\n")
        self._log(f"  Intraday fallback={'YES' if id_['fallback_used'] else 'NO'}\n")

    def _update_plots(self, r: dict) -> None:
        if r is None:
            return
        m = r["dayahead"]
        id_ = r["intraday"]
        po = r["pareto_objectives"]
        fo = r["final_population_objectives"]

        # Tab 1: Pareto + dispatch
        for ax in self._axs1:
            ax.cla()
        ax1, ax2, ax3, ax4 = self._axs1

        ax1.scatter(fo[:, 0], fo[:, 1], s=12, c="tab:blue", label="Population")
        ax1.scatter(po[:, 0], po[:, 1], s=30, c="tab:red", label="Pareto")
        ax1.scatter([m.total_cost], [m.total_carbon], s=80, c="tab:green", marker="s", label="Selected")
        ax1.set_xlabel("Cost"); ax1.set_ylabel("Carbon")
        ax1.set_title("Pareto Front / Pareto前沿"); ax1.legend(fontsize=8)

        ax2.plot(m.P_wind_actual, label="Wind")
        ax2.plot(m.P_solar_actual, label="Solar")
        ax2.plot(m.P_thermal_total, label="Thermal")
        ax2.set_title("Day-ahead Output / 日前出力"); ax2.legend(fontsize=8)
        ax2.set_xlabel("Hour"); ax2.set_ylabel("MW")

        ax3.plot(m.P_charge, label="Charge")
        ax3.plot(m.P_discharge, label="Discharge")
        ax3.plot(m.P_P2G, label="P2G")
        ax3.plot(m.P_P2A, label="P2A")
        ax3.set_title("Flexible Resources / 灵活资源"); ax3.legend(fontsize=8)
        ax3.set_xlabel("Hour"); ax3.set_ylabel("MW")

        ax4.plot(id_["SOC_day_ahead"], label="DA SOC")
        ax4.plot(id_["SOC_intraday"], label="ID SOC")
        ax4.set_title("SOC Tracking / SOC跟踪"); ax4.legend(fontsize=8)
        ax4.set_xlabel("15-min"); ax4.set_ylabel("MWh")

        self._fig1.suptitle("Day-ahead Dispatch / 日前调度", fontweight="bold")
        self._canvas1.draw()

        # Tab 2: intraday
        for ax in self._axs2:
            ax.cla()
        ax5, ax6, ax7 = self._axs2

        ax5.plot(id_["P_ch_day_ahead"], label="DA Charge")
        ax5.plot(id_["P_ch_intraday"], label="ID Charge")
        ax5.plot(id_["P_dis_day_ahead"], label="DA Discharge")
        ax5.plot(id_["P_dis_intraday"], label="ID Discharge")
        ax5.set_title("Storage / 储能"); ax5.legend(fontsize=8)
        ax5.set_xlabel("15-min"); ax5.set_ylabel("MW")

        ax6.plot(id_["P_net_day_ahead"], label="DA")
        ax6.plot(id_["P_net_intraday"], label="ID")
        ax6.set_title("Net Imbalance / 净不平衡"); ax6.legend(fontsize=8)
        ax6.set_xlabel("15-min"); ax6.set_ylabel("MW")

        t = np.arange(96) / 4
        ax7.plot(t, id_["P_wind_day_ahead"], label="DA Wind")
        ax7.plot(t, id_["P_wind_intraday_forecast"], label="ID Wind", alpha=0.6)
        ax7.plot(t, id_["P_solar_day_ahead"], label="DA Solar")
        ax7.plot(t, id_["P_solar_intraday_forecast"], label="ID Solar", alpha=0.6)
        ax7.plot(t, id_["P_load_day_ahead"], label="DA Load")
        ax7.plot(t, id_["P_load_intraday_forecast"], label="ID Load", alpha=0.6)
        ax7.set_title("Forecasts / 预测对比"); ax7.legend(fontsize=7, ncol=2)
        ax7.set_xlabel("Hour"); ax7.set_ylabel("MW")

        self._fig2.suptitle("Intraday Adjustment / 日内校正", fontweight="bold")
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
        showinfo("Saved / 已保存", f"Results saved to:\n{path}")

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
                self._save_figures_png(path.replace(".pdf", "_1.png"))
        else:
            self._save_figures_png(path)
        showinfo("Saved / 已保存", f"Figures saved to:\n{path}")

    def _save_figures_png(self, base_path: str) -> None:
        p2 = base_path.replace(".png", "") + "_intraday.png"
        self._fig1.savefig(base_path, dpi=150, bbox_inches="tight")
        self._fig2.savefig(p2, dpi=150, bbox_inches="tight")

    def _on_clear(self) -> None:
        self.log_txt.delete("1.0", END)
        self.results = None
        self.status_lbl.configure(text="Ready / 就绪")
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
