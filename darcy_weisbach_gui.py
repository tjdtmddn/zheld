"""Tkinter GUI for the Darcy-Weisbach pipe-loss analyzer."""

from __future__ import annotations

import csv
import json
import math
from datetime import datetime
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from darcy_weisbach import (
    FLUID_PRESETS,
    MATERIAL_ROUGHNESS_M,
    AnalysisResult,
    analyze,
    calculate_component_loss_coefficients,
    configure_matplotlib_korean,
    save_plot,
    save_report,
)
from phase_two import (
    PumpCurvePoint,
    find_operating_point,
    parallel_branch_flows,
    parallel_resistance,
    pump_head_at_flow,
    series_resistance,
    system_head,
)
from advanced_analysis import (
    NetworkEdge,
    combine_pump_curves,
    monte_carlo_analysis,
    rectangular_hydraulic_diameter,
    sensitivity_analysis,
    solve_network,
    summarize_results,
)

UNIT_FACTORS = {
    "flow": {"m³/s": 1.0, "L/s": 1e-3, "m³/h": 1 / 3600},
    "length": {"m": 1.0, "mm": 1e-3, "km": 1000.0},
}
CSV_REQUIRED_ALTERNATIVES = (
    ("flow_rate_m3_s", "velocity_m_s", "flow_rate", "velocity"),
    ("diameter_m", "diameter"),
    ("pipe_length_m", "pipe_length"),
    ("material", "absolute_roughness_m", "absolute_roughness"),
)
CSV_DIRECTORY = Path(__file__).resolve().parent / "csv"
OUTPUT_DIRECTORY = Path(__file__).resolve().parent / "output"


class DarcyWeisbachApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Darcy-Weisbach 관로 분석기")
        self.geometry("720x720")
        self.minsize(620, 620)
        self.result: AnalysisResult | None = None
        self.batch_results: list[tuple[str, AnalysisResult]] = []
        self._criteria: dict[str, float | None] = {}
        self.transition_policy = tk.StringVar(value="warn")
        self._build_widgets()

    def _build_widgets(self) -> None:
        style = ttk.Style(self)
        style.configure("App.TFrame", background="#F5F7FA")
        style.configure("Card.TFrame", background="#FFFFFF")
        style.configure("Header.TLabel", background="#F5F7FA", foreground="#172033",
                        font=("Segoe UI", 18, "bold"))
        style.configure("Subtitle.TLabel", background="#F5F7FA", foreground="#64748B")
        style.configure("CardTitle.TLabel", background="#FFFFFF", foreground="#64748B",
                        font=("Segoe UI", 9))
        style.configure("CardValue.TLabel", background="#FFFFFF", foreground="#172033",
                        font=("Segoe UI", 15, "bold"))
        style.configure("Primary.TButton", background="#2563EB", foreground="white",
                        padding=(14, 7), font=("Segoe UI", 10, "bold"))
        style.configure("Section.TLabelframe", background="#FFFFFF")
        style.configure("Section.TLabelframe.Label", foreground="#172033",
                        font=("Segoe UI", 10, "bold"))
        style.configure("Status.TLabel", background="#E2E8F0", foreground="#475569",
                        padding=(10, 5))
        style.configure("Treeview", rowheight=28, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

        self.configure(background="#F5F7FA")
        self.geometry("1180x780")
        self.minsize(900, 650)
        self.bind_all("<MouseWheel>", self._on_mousewheel)
        self.status_var = tk.StringVar(value="입력 대기 · 계산할 조건을 입력하세요")
        self._summary_values: dict[str, ttk.Label] = {}

        root = ttk.Frame(self, style="App.TFrame", padding=(22, 18))
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=0, minsize=360)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(1, weight=1)

        header = ttk.Frame(root, style="App.TFrame")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 16))
        ttk.Label(header, text="Darcy-Weisbach 관로 분석기", style="Header.TLabel").pack(anchor="w")
        ttk.Label(header, text="관로 손실, 펌프 요구량과 기간별 결과를 한 화면에서 분석합니다.",
                  style="Subtitle.TLabel").pack(anchor="w", pady=(3, 0))
        ttk.Label(header, textvariable=self.status_var, style="Status.TLabel").pack(
            side="right", anchor="e", pady=(0, 3))

        input_shell = ttk.Frame(root, style="Card.TFrame", padding=14)
        input_shell.grid(row=1, column=0, sticky="nsew", padx=(0, 14))
        input_shell.columnconfigure(0, weight=1)
        input_shell.rowconfigure(1, weight=1)
        ttk.Label(input_shell, text="입력 조건", font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 10))

        canvas = tk.Canvas(input_shell, highlightthickness=0, background="#FFFFFF")
        scrollbar = ttk.Scrollbar(input_shell, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=1, column=0, sticky="nsew")
        scrollbar.grid(row=1, column=1, sticky="ns")
        form = ttk.Frame(canvas, style="Card.TFrame", padding=(0, 0, 6, 0))
        window_id = canvas.create_window((0, 0), window=form, anchor="nw")
        form.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window_id, width=event.width))
        self._canvas = canvas
        form.columnconfigure(1, weight=1)

        self.flow_mode = tk.StringVar(value="flow_rate")
        basic = ttk.LabelFrame(form, text="기본 관로 조건", style="Section.TLabelframe", padding=10)
        basic.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        basic.columnconfigure(1, weight=1)
        ttk.Label(basic, text="입력 방식").grid(row=0, column=0, sticky="w", pady=4)
        mode_frame = ttk.Frame(basic)
        mode_frame.grid(row=0, column=1, columnspan=2, sticky="w")
        ttk.Radiobutton(mode_frame, text="유량 Q", variable=self.flow_mode, value="flow_rate",
                        command=self._update_flow_label).pack(side="left", padx=(0, 12))
        ttk.Radiobutton(mode_frame, text="유속 V", variable=self.flow_mode, value="velocity",
                        command=self._update_flow_label).pack(side="left")
        self.flow_label = ttk.Label(basic, text="유량 Q (m³/s)")
        self.flow_label.grid(row=1, column=0, sticky="w", pady=4)
        self.flow_entry = ttk.Entry(basic)
        self.flow_entry.insert(0, "0.015")
        self.flow_entry.grid(row=1, column=1, sticky="ew", pady=4)
        self.flow_unit_combo = ttk.Combobox(basic, values=list(UNIT_FACTORS["flow"]),
                                            state="readonly", width=8)
        self.flow_unit_combo.set("m³/s")
        self.flow_unit_combo.grid(row=1, column=2, padx=(6, 0))
        self._add_entry(basic, 2, "관경 D", "0.1", "diameter")
        self.diameter_unit_combo = ttk.Combobox(basic, values=list(UNIT_FACTORS["length"]),
                                                state="readonly", width=8)
        self.diameter_unit_combo.set("m")
        self.diameter_unit_combo.grid(row=2, column=3, padx=(6, 0))
        self._add_entry(basic, 3, "관 길이 L", "20", "length")
        self.length_unit_combo = ttk.Combobox(basic, values=list(UNIT_FACTORS["length"]),
                                              state="readonly", width=8)
        self.length_unit_combo.set("m")
        self.length_unit_combo.grid(row=3, column=3, padx=(6, 0))
        self._add_entry(basic, 4, "물 온도 (°C)", "20", "temperature")
        ttk.Label(basic, text="유체").grid(row=5, column=0, sticky="w", pady=4)
        self.fluid_combo = ttk.Combobox(
            basic, values=("water", "air", "custom"), state="readonly", width=12
        )
        self.fluid_combo.set("water")
        self.fluid_combo.grid(row=5, column=1, sticky="w", pady=4)
        self.fluid_combo.bind("<<ComboboxSelected>>", lambda _event: self._update_fluid_state())
        self._add_entry(basic, 6, "밀도 (kg/m³)", "", "density")
        self._add_entry(basic, 7, "동적 점성계수 (Pa·s)", "", "viscosity")

        loss = ttk.LabelFrame(form, text="손실 및 펌프 조건", style="Section.TLabelframe", padding=10)
        loss.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        loss.columnconfigure(1, weight=1)
        ttk.Label(loss, text="관 조도").grid(row=0, column=0, sticky="w", pady=4)
        roughness_frame = ttk.Frame(loss)
        roughness_frame.grid(row=0, column=1, columnspan=2, sticky="ew")
        roughness_frame.columnconfigure(1, weight=1)
        self.roughness_mode = tk.StringVar(value="material")
        ttk.Radiobutton(roughness_frame, text="재질", variable=self.roughness_mode,
                        value="material", command=self._update_roughness_state).grid(row=0, column=0, sticky="w")
        self.material_combo = ttk.Combobox(roughness_frame, values=sorted(MATERIAL_ROUGHNESS_M),
                                           state="readonly")
        self.material_combo.set("commercial-steel")
        self.material_combo.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        ttk.Radiobutton(roughness_frame, text="직접 입력 ε (m)", variable=self.roughness_mode,
                        value="roughness", command=self._update_roughness_state).grid(row=1, column=0, sticky="w", pady=(5, 0))
        self.roughness_entry = ttk.Entry(roughness_frame, state="disabled")
        self.roughness_entry.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(5, 0))
        self._add_entry(loss, 1, "부차적 손실계수 K", "0", "minor_k")
        self._add_entry(loss, 2, "펌프 효율 (0~1)", "", "efficiency")
        self._add_entry(loss, 3, "정수두/높이차 (m)", "0", "static_head")

        criteria = ttk.LabelFrame(form, text="기준 및 기간 필터", style="Section.TLabelframe", padding=10)
        criteria.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        criteria.columnconfigure(1, weight=1)
        for row, label, name in (
            (0, "최대 유속 (m/s)", "max_velocity"),
            (1, "최대 손실수두 (m)", "max_head_loss"),
            (2, "최대 압력손실 (kPa)", "max_pressure_loss"),
        ):
            ttk.Label(criteria, text=label).grid(row=row, column=0, sticky="w", pady=4)
            entry = ttk.Entry(criteria)
            entry.grid(row=row, column=1, sticky="ew", pady=4)
            setattr(self, f"{name}_entry", entry)
        ttk.Label(criteria, text="기간 시작").grid(row=3, column=0, sticky="w", pady=4)
        self.period_start_entry = ttk.Entry(criteria)
        self.period_start_entry.grid(row=3, column=1, sticky="ew", pady=4)
        ttk.Label(criteria, text="기간 종료").grid(row=4, column=0, sticky="w", pady=4)
        self.period_end_entry = ttk.Entry(criteria)
        self.period_end_entry.grid(row=4, column=1, sticky="ew", pady=4)
        ttk.Label(criteria, text="YYYY-MM-DD · CSV timestamp에만 적용",
                  foreground="#64748B").grid(row=5, column=0, columnspan=2, sticky="w")
        ttk.Label(criteria, text="부품별 손실 (이름:개수:K)").grid(row=6, column=0, sticky="w", pady=4)
        self.minor_components_entry = ttk.Entry(criteria)
        self.minor_components_entry.grid(row=6, column=1, sticky="ew", pady=4)
        ttk.Label(criteria, text="예: 입구:1:0.5,엘보:4:0.3",
                  foreground="#64748B").grid(row=7, column=0, columnspan=2, sticky="w")
        ttk.Label(criteria, text="천이영역").grid(row=8, column=0, sticky="w", pady=4)
        self.transition_policy_combo = ttk.Combobox(criteria, textvariable=self.transition_policy,
                                                    values=("warn", "stop"), state="readonly", width=12)
        self.transition_policy_combo.grid(row=8, column=1, sticky="w", pady=4)

        actions = ttk.LabelFrame(form, text="작업", style="Section.TLabelframe", padding=10)
        actions.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        ttk.Button(actions, text="계산하기", style="Primary.TButton",
                   command=self._calculate).grid(row=0, column=0, columnspan=2, sticky="ew", padx=(0, 5), pady=3)
        ttk.Button(actions, text="초기화", command=self._reset).grid(row=0, column=2, sticky="ew", pady=3)
        ttk.Button(actions, text="결과 갱신", command=self._refresh_results).grid(row=1, column=0, sticky="ew", padx=(0, 5), pady=3)
        ttk.Button(actions, text="보고서 저장", command=self._save_report).grid(row=1, column=1, sticky="ew", padx=5, pady=3)
        ttk.Button(actions, text="그래프 저장", command=self._save_plot).grid(row=1, column=2, sticky="ew", padx=(5, 0), pady=3)
        ttk.Button(actions, text="PDF 보고서", command=self._save_pdf_report).grid(row=2, column=0, columnspan=3, sticky="ew", pady=3)
        ttk.Button(actions, text="결과 비교", command=self._show_result_comparison).grid(row=3, column=0, columnspan=3, sticky="ew", pady=3)
        for column in range(3):
            actions.columnconfigure(column, weight=1)

        files = ttk.LabelFrame(form, text="파일", style="Section.TLabelframe", padding=10)
        files.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        file_buttons = (
            ("프로젝트 열기", self._load_project), ("프로젝트 저장", self._save_project),
            ("CSV 불러오기", self._load_csv), ("입력 CSV 저장", self._save_input_csv),
            ("입력 CSV 양식 저장", self._save_input_template_csv),
            ("CSV 일괄 계산", self._calculate_csv), ("결과 CSV 저장", self._save_current_results_csv),
        )
        for index, (text, command) in enumerate(file_buttons):
            ttk.Button(files, text=text, command=command).grid(
                row=index // 2, column=index % 2, sticky="ew", padx=3, pady=3)
        files.columnconfigure(0, weight=1)
        files.columnconfigure(1, weight=1)

        advanced = ttk.LabelFrame(form, text="고급 분석", style="Section.TLabelframe", padding=10)
        advanced.grid(row=5, column=0, columnspan=3, sticky="ew")
        advanced_buttons = (
            ("펌프 곡선", self._open_pump_curve), ("직렬/병렬 관로", self._open_network),
            ("민감도·불확실성", self._open_advanced_analysis), ("다중노드 관망", self._open_network_solver),
            ("수력직경", self._open_hydraulic_diameter), ("펌프 조합", self._open_pump_combination),
        )
        for index, (text, command) in enumerate(advanced_buttons):
            ttk.Button(advanced, text=text, command=command).grid(
                row=index // 2, column=index % 2, sticky="ew", padx=3, pady=3)
        advanced.columnconfigure(0, weight=1)
        advanced.columnconfigure(1, weight=1)

        result_shell = ttk.Frame(root, style="Card.TFrame", padding=14)
        result_shell.grid(row=1, column=1, sticky="nsew")
        result_shell.columnconfigure(0, weight=1)
        result_shell.rowconfigure(1, weight=1)
        ttk.Label(result_shell, text="분석 결과", font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 10))
        self.result_notebook = ttk.Notebook(result_shell)
        self.result_notebook.grid(row=1, column=0, sticky="nsew")

        summary_tab = ttk.Frame(self.result_notebook, padding=12)
        detail_tab = ttk.Frame(self.result_notebook, padding=12)
        table_tab = ttk.Frame(self.result_notebook, padding=12)
        graph_tab = ttk.Frame(self.result_notebook, padding=12)
        self.result_notebook.add(summary_tab, text="요약")
        self.result_notebook.add(detail_tab, text="상세 계산")
        self.result_notebook.add(table_tab, text="기간별 결과")
        self.result_notebook.add(graph_tab, text="그래프")
        for tab in (summary_tab, detail_tab, table_tab, graph_tab):
            tab.columnconfigure(0, weight=1)
            tab.rowconfigure(0, weight=1)

        cards = ttk.Frame(summary_tab)
        cards.grid(row=0, column=0, sticky="new")
        card_items = (
            ("평균 유속", "velocity", "m/s"), ("전체 손실수두", "head_loss", "m"),
            ("압력손실", "pressure", "kPa"), ("필요 펌프수두", "pump_head", "m"),
            ("Reynolds 수", "reynolds", ""), ("펌프동력", "power", "kW"),
        )
        for index, (title, key, unit) in enumerate(card_items):
            card = ttk.Frame(cards, style="Card.TFrame", padding=12, relief="solid", borderwidth=1)
            card.grid(row=index // 2, column=index % 2, sticky="ew", padx=4, pady=4)
            cards.columnconfigure(index % 2, weight=1)
            ttk.Label(card, text=title, style="CardTitle.TLabel").pack(anchor="w")
            value_label = ttk.Label(card, text=f"— {unit}".rstrip(), style="CardValue.TLabel")
            value_label.pack(anchor="w", pady=(5, 0))
            self._summary_values[key] = value_label
        ttk.Label(summary_tab, text="계산 후 핵심 지표와 기준 판정이 표시됩니다.",
                  foreground="#64748B").grid(row=1, column=0, sticky="sw", pady=(16, 0))

        self.result_text = tk.Text(detail_tab, height=8, width=80, state="disabled",
                                   font=("Consolas", 9), relief="flat", background="#F8FAFC")
        self.result_text.grid(row=0, column=0, sticky="nsew")
        detail_scrollbar = ttk.Scrollbar(detail_tab, orient="vertical", command=self.result_text.yview)
        detail_scrollbar.grid(row=0, column=1, sticky="ns")
        self.result_text.configure(yscrollcommand=detail_scrollbar.set)

        table_frame = ttk.Frame(table_tab)
        table_frame.grid(row=0, column=0, sticky="nsew")
        table_tab.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        columns = ("period", "regime", "velocity", "head_loss", "pressure", "status")
        self.result_table = ttk.Treeview(table_frame, columns=columns, show="headings")
        headings = {
            "period": "기간/행",
            "regime": "유동 구간",
            "velocity": "유속 (m/s)",
            "head_loss": "전체손실수두 (m)",
            "pressure": "압력손실 (kPa)",
            "status": "기준 판정",
        }
        for column in columns:
            self.result_table.heading(column, text=headings[column])
            self.result_table.column(column, width=120, anchor="center")
        self.result_table.grid(row=0, column=0, sticky="nsew")
        table_scrollbar = ttk.Scrollbar(
            table_frame, orient="vertical", command=self.result_table.yview
        )
        table_scrollbar.grid(row=0, column=1, sticky="ns")
        self.result_table.configure(yscrollcommand=table_scrollbar.set)
        self.result_table.bind("<<TreeviewSelect>>", self._on_result_selected)
        self._visible_results: list[tuple[str, AnalysisResult]] = []
        self.graph_frame = ttk.Frame(graph_tab)
        self.graph_frame.grid(row=0, column=0, sticky="nsew")
        self.graph_frame.columnconfigure(0, weight=1)
        self.graph_frame.rowconfigure(0, weight=1)
        graph_controls = ttk.Frame(self.graph_frame)
        graph_controls.grid(row=0, column=0, sticky="ew")
        ttk.Label(graph_controls, text="그래프 항목").pack(side="left")
        self.graph_metric = ttk.Combobox(
            graph_controls,
            values=("전체손실수두", "압력손실", "평균유속", "Reynolds 수", "필요펌프수두", "펌프동력"),
            state="readonly",
            width=16,
        )
        self.graph_metric.set("전체손실수두")
        self.graph_metric.pack(side="left", padx=6)
        self.graph_metric.bind("<<ComboboxSelected>>", lambda _event: self._refresh_results())
        self.graph_canvas_frame = ttk.Frame(self.graph_frame)
        self.graph_canvas_frame.grid(row=1, column=0, sticky="nsew")
        self.graph_frame.rowconfigure(1, weight=1)
        self._update_roughness_state()
        self._update_fluid_state()

    def _on_mousewheel(self, event: tk.Event) -> None:
        self._canvas.yview_scroll(int(-event.delta / 120), "units")

    def _add_entry(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        default: str,
        name: str,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
        entry = ttk.Entry(parent)
        entry.insert(0, default)
        entry.grid(row=row, column=1, columnspan=2, sticky="ew", pady=4)
        setattr(self, f"{name}_entry", entry)

    def _update_flow_label(self) -> None:
        label = "유량 Q (m³/s)" if self.flow_mode.get() == "flow_rate" else "유속 V (m/s)"
        self.flow_label.configure(text=label)

    def _update_roughness_state(self) -> None:
        material_mode = self.roughness_mode.get() == "material"
        self.material_combo.configure(state="readonly" if material_mode else "disabled")
        self.roughness_entry.configure(state="disabled" if material_mode else "normal")

    def _update_fluid_state(self) -> None:
        preset = self.fluid_combo.get()
        custom = preset == "custom"
        for entry, value in (
            (self.density_entry, FLUID_PRESETS.get(preset, ("", ""))[0]),
            (self.viscosity_entry, FLUID_PRESETS.get(preset, ("", ""))[1]),
        ):
            entry.configure(state="normal" if custom else "disabled")
            if not custom:
                self._set_entry(entry, str(value))

    def _number(self, entry: ttk.Entry, label: str, optional: bool = False) -> float | None:
        value = entry.get().strip()
        if optional and not value:
            return None
        try:
            number = float(value)
        except ValueError as exc:
            entry.focus_set()
            entry.selection_range(0, tk.END)
            raise ValueError(f"{label}에 숫자를 입력하세요.") from exc
        if not math.isfinite(number):
            entry.focus_set()
            entry.selection_range(0, tk.END)
            raise ValueError(f"{label}에는 유한한 숫자를 입력하세요.")
        return number

    def _unit_value(self, entry: ttk.Entry, kind: str, label: str, unit: str) -> float:
        value = self._positive_number(entry, label)
        return value * UNIT_FACTORS[kind][unit]

    def _parse_components(self) -> dict[str, tuple[int, float]] | None:
        text = self.minor_components_entry.get().strip()
        if not text:
            return None
        components: dict[str, tuple[int, float]] = {}
        try:
            for item in text.split(","):
                name, count, coefficient = (part.strip() for part in item.split(":"))
                if not name:
                    raise ValueError
                components[name] = (int(count), float(coefficient))
            calculate_component_loss_coefficients(components)
        except (ValueError, TypeError) as exc:
            self.minor_components_entry.focus_set()
            raise ValueError(
                "부품별 손실은 '이름:개수:K' 형식으로 입력하세요."
            ) from exc
        return components

    def _nonnegative_number(
        self, entry: ttk.Entry, label: str, optional: bool = False
    ) -> float | None:
        number = self._number(entry, label, optional)
        if number is not None and number < 0:
            entry.focus_set()
            entry.selection_range(0, tk.END)
            raise ValueError(f"{label}은(는) 0 이상이어야 합니다.")
        return number

    def _positive_number(self, entry: ttk.Entry, label: str) -> float:
        number = self._number(entry, label)
        if number is None or number <= 0:
            entry.focus_set()
            entry.selection_range(0, tk.END)
            raise ValueError(f"{label}은(는) 0보다 커야 합니다.")
        return number

    def _calculate(self) -> None:
        try:
            flow_value = self._unit_value(
                self.flow_entry,
                "flow",
                self.flow_label.cget("text"),
                self.flow_unit_combo.get(),
            )
            diameter = self._unit_value(
                self.diameter_entry, "length", "관경", self.diameter_unit_combo.get()
            )
            length = self._unit_value(
                self.length_entry, "length", "관 길이", self.length_unit_combo.get()
            )
            temperature = self._number(self.temperature_entry, "물 온도", optional=True)
            minor_k = self._nonnegative_number(self.minor_k_entry, "부차적 손실계수")
            static_head = self._nonnegative_number(self.static_head_entry, "정수두/높이차")
            components = self._parse_components()
            efficiency = self._number(self.efficiency_entry, "펌프 효율", optional=True)
            if efficiency is not None and not 0 < efficiency <= 1:
                self.efficiency_entry.focus_set()
                self.efficiency_entry.selection_range(0, tk.END)
                raise ValueError("펌프 효율은 0보다 크고 1 이하여야 합니다.")
            kwargs = {
                "diameter_m": diameter,
                "pipe_length_m": length,
                "temperature_c": temperature,
                "minor_loss_coefficient": minor_k,
                "static_head_m": static_head,
                "minor_loss_components": components,
                "pump_efficiency": efficiency,
                "transitional_policy": self.transition_policy.get(),
                "fluid": self.fluid_combo.get(),
            }
            if self.fluid_combo.get() == "custom":
                kwargs["density_kg_m3"] = self._positive_number(
                    self.density_entry, "밀도"
                )
                kwargs["dynamic_viscosity_pa_s"] = self._positive_number(
                    self.viscosity_entry, "동적 점성계수"
                )
            if self.flow_mode.get() == "flow_rate":
                kwargs["flow_rate_m3_s"] = flow_value
            else:
                kwargs["velocity_m_s"] = flow_value
            if self.roughness_mode.get() == "material":
                kwargs["material"] = self.material_combo.get()
            else:
                kwargs["absolute_roughness_m"] = self._nonnegative_number(
                    self.roughness_entry, "절대조도"
                )
            self.result = analyze(**kwargs)
            self.batch_results = [("", self.result)]
        except (TypeError, ValueError, RuntimeError) as exc:
            messagebox.showerror("입력 오류", str(exc), parent=self)
            return
        self._display_result(self.result)
        self._refresh_results()

    def _display_result(self, result: AnalysisResult) -> None:
        self._summary_values["velocity"].configure(text=f"{result.velocity_m_s:.4f} m/s")
        self._summary_values["head_loss"].configure(
            text=f"{result.total_head_loss_m:.4f} m"
        )
        self._summary_values["pressure"].configure(
            text=f"{result.pressure_loss_pa / 1000:.4f} kPa"
        )
        self._summary_values["pump_head"].configure(
            text=f"{result.required_pump_head_m:.4f} m"
        )
        self._summary_values["reynolds"].configure(text=f"{result.reynolds_number:.4g}")
        power = "—" if result.pump_power_w is None else f"{result.pump_power_w / 1000:.4f} kW"
        self._summary_values["power"].configure(text=power)
        self.status_var.set(f"계산 완료 · {result.flow_regime}")
        lines = [
            f"유동 구간: {result.flow_regime}",
            f"레이놀즈 수 (Re): {result.reynolds_number:.6g}",
            f"Darcy 마찰계수 (f): {result.friction_factor:.10f}",
            f"유량: {result.flow_rate_m3_s:.6g} m³/s",
            f"단면적: {result.area_m2:.6g} m²",
            f"평균 유속: {result.velocity_m_s:.6f} m/s",
            f"상대조도: {result.relative_roughness:.6g}",
            f"주손실수두: {result.major_head_loss_m:.6f} m",
            f"부차적 손실수두: {result.minor_head_loss_m:.6f} m",
            f"전체 손실수두: {result.total_head_loss_m:.6f} m",
            f"정수두/높이차: {result.static_head_m:.6f} m",
            f"필요 펌프수두: {result.required_pump_head_m:.6f} m",
            f"압력손실: {result.pressure_loss_pa / 1000:.6f} kPa",
            f"유체 물성: 밀도 {getattr(result, 'density_kg_m3', '계산값')} kg/m³",
        ]
        lines.append("\n[계산식 및 중간값]")
        lines.extend(result.equations)
        if result.pump_power_w is not None:
            lines.append(f"필요 펌프동력: {result.pump_power_w / 1000:.6f} kW")
        if result.warning:
            lines.append(f"\n경고: {result.warning}")
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", tk.END)
        self.result_text.insert("1.0", "\n".join(lines))
        self.result_text.configure(state="disabled")

    def _read_criteria(self) -> dict[str, float | None]:
        return {
            "max_velocity": self._nonnegative_number(
                self.max_velocity_entry, "최대 유속", optional=True
            ),
            "max_head_loss": self._nonnegative_number(
                self.max_head_loss_entry, "최대 전체손실수두", optional=True
            ),
            "max_pressure_loss": self._nonnegative_number(
                self.max_pressure_loss_entry, "최대 압력손실", optional=True
            ),
        }

    def _row_status(self, result: AnalysisResult, criteria: dict[str, float | None]) -> str:
        checks = (
            criteria["max_velocity"] is not None
            and result.velocity_m_s > criteria["max_velocity"],
            criteria["max_head_loss"] is not None
            and result.total_head_loss_m > criteria["max_head_loss"],
            criteria["max_pressure_loss"] is not None
            and result.pressure_loss_pa / 1000 > criteria["max_pressure_loss"],
        )
        return "초과" if any(checks) else "정상"

    def _on_result_selected(self, _event: tk.Event) -> None:
        selected = self.result_table.selection()
        if not selected:
            return
        index = self.result_table.index(selected[0])
        if index < len(self._visible_results):
            self.result = self._visible_results[index][1]
            self._display_result(self.result)

    def _refresh_results(self) -> None:
        if not self.batch_results:
            return
        try:
            criteria = self._read_criteria()
            start = self.period_start_entry.get().strip()
            end = self.period_end_entry.get().strip()
            for value, label in ((start, "시작 기간"), (end, "종료 기간")):
                if value:
                    datetime.strptime(value, "%Y-%m-%d")
            if start and end and start > end:
                raise ValueError("시작 기간은 종료 기간보다 빠르거나 같아야 합니다.")
        except ValueError as exc:
            messagebox.showerror("조건 오류", str(exc), parent=self)
            return
        self._criteria = criteria
        visible = [
            item for item in self.batch_results
            if (not start or not item[0] or item[0][:10] >= start)
            and (not end or not item[0] or item[0][:10] <= end)
        ]
        self._visible_results = visible
        for item in self.result_table.get_children():
            self.result_table.delete(item)
        for period, result in visible:
            self.result_table.insert(
                "",
                "end",
                values=(
                    period or "직접 입력",
                    result.flow_regime,
                    f"{result.velocity_m_s:.4f}",
                    f"{result.total_head_loss_m:.4f}",
                    f"{result.pressure_loss_pa / 1000:.4f}",
                    self._row_status(result, criteria),
                ),
            )
        self._draw_graph(visible, criteria)

    def _draw_graph(
        self,
        results: list[tuple[str, AnalysisResult]],
        criteria: dict[str, float | None],
    ) -> None:
        for child in self.graph_canvas_frame.winfo_children():
            child.destroy()
        try:
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            from matplotlib.figure import Figure
        except ImportError:
            ttk.Label(self.graph_canvas_frame, text="그래프에는 matplotlib이 필요합니다.").grid()
            return
        configure_matplotlib_korean()
        figure = Figure(figsize=(7, 2.8), dpi=100)
        axis = figure.add_subplot(111)
        labels = [period or str(index + 1) for index, (period, _) in enumerate(results)]
        metric = self.graph_metric.get()
        value_map = {
            "전체손실수두": ([result.total_head_loss_m for _, result in results], "m"),
            "압력손실": ([result.pressure_loss_pa / 1000 for _, result in results], "kPa"),
            "평균유속": ([result.velocity_m_s for _, result in results], "m/s"),
            "Reynolds 수": ([result.reynolds_number for _, result in results], ""),
            "필요펌프수두": ([result.required_pump_head_m for _, result in results], "m"),
            "펌프동력": (
                [(result.pump_power_w or 0) / 1000 for _, result in results],
                "kW",
            ),
        }
        values, unit = value_map.get(metric, value_map["전체손실수두"])
        axis.plot(labels, values, marker="o", label=f"{metric} ({unit})")
        if criteria.get("max_head_loss") is not None:
            axis.axhline(
                criteria["max_head_loss"],
                color="red",
                linestyle="--",
                label="최대 기준",
            )
        axis.set_ylabel(f"{metric} ({unit})")
        axis.set_title(f"기간별 {metric}")
        axis.legend(loc="best")
        axis.tick_params(axis="x", rotation=30)
        figure.tight_layout()
        canvas = FigureCanvasTkAgg(figure, master=self.graph_canvas_frame)
        canvas.draw()
        canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")

    def _open_pump_curve(self) -> None:
        window = tk.Toplevel(self)
        window.title("펌프 곡선 · 시스템 곡선")
        window.geometry("600x520")
        frame = ttk.Frame(window, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(
            frame, text="펌프 곡선 학습 도구", font=("Segoe UI", 13, "bold")
        ).pack(anchor="w")
        ttk.Label(
            frame, text="펌프점은 Q(m³/s):H(m) 형식으로 쉼표 구분 (예: 0:30,0.01:25,0.02:15)"
        ).pack(anchor="w", pady=(8, 3))
        points_entry = ttk.Entry(frame)
        points_entry.insert(0, "0:30,0.01:25,0.02:15")
        points_entry.pack(fill="x")
        values_frame = ttk.Frame(frame)
        values_frame.pack(fill="x", pady=8)
        ttk.Label(values_frame, text="정수두 (m)").grid(row=0, column=0, sticky="w")
        static_entry = ttk.Entry(values_frame, width=14)
        static_entry.insert(0, "5")
        static_entry.grid(row=0, column=1, padx=6)
        ttk.Label(values_frame, text="시스템 저항 R (m/(m³/s)²)").grid(
            row=0, column=2, sticky="w"
        )
        resistance_entry = ttk.Entry(values_frame, width=14)
        resistance_entry.insert(0, "50000")
        resistance_entry.grid(row=0, column=3, padx=6)
        output = tk.Text(frame, height=8, state="disabled")
        output.pack(fill="x", pady=6)
        graph = tk.Canvas(frame, height=180, background="white")
        graph.pack(fill="both", expand=True)

        def calculate() -> None:
            try:
                points = []
                for item in points_entry.get().split(","):
                    flow, head = (float(part.strip()) for part in item.split(":"))
                    points.append(PumpCurvePoint(flow, head))
                static_head = float(static_entry.get())
                resistance = float(resistance_entry.get())
                operating = find_operating_point(points, static_head, resistance)
                lines = [
                    "H_pump = H_system 교점",
                    f"운전 유량: {operating.flow_rate_m3_s:.6g} m³/s",
                    f"펌프 수두: {operating.pump_head_m:.6f} m",
                    f"시스템 수두: {operating.system_head_m:.6f} m",
                    f"잔차: {operating.residual_m:.3g} m",
                    "",
                    "H_system = H_static + R Q²",
                    f"= {static_head:.6g} + {resistance:.6g} Q²",
                ]
                output.configure(state="normal")
                output.delete("1.0", tk.END)
                output.insert("1.0", "\n".join(lines))
                output.configure(state="disabled")
                self._draw_curve_canvas(
                    graph, points, static_head, resistance, operating.flow_rate_m3_s
                )
            except (TypeError, ValueError, ZeroDivisionError) as exc:
                messagebox.showerror("펌프 곡선 입력 오류", str(exc), parent=window)

        ttk.Button(frame, text="운전점 계산", command=calculate).pack(anchor="e")
        calculate()

    @staticmethod
    def _draw_curve_canvas(
        canvas: tk.Canvas,
        points: list[PumpCurvePoint],
        static_head: float,
        resistance: float,
        operating_flow: float,
    ) -> None:
        canvas.delete("all")
        width = max(canvas.winfo_width(), 500)
        height = max(canvas.winfo_height(), 160)
        ordered = sorted(points, key=lambda point: point.flow_rate_m3_s)
        max_flow = ordered[-1].flow_rate_m3_s
        max_head = max(
            max(point.head_m for point in ordered),
            system_head(max_flow, static_head, resistance),
            1.0,
        )
        def xy(flow: float, head: float) -> tuple[float, float]:
            return 40 + 0.88 * width * flow / max_flow, height - 25 - 0.82 * height * head / max_head
        canvas.create_line(40, height - 25, width - 20, height - 25, fill="black")
        canvas.create_line(40, height - 25, 40, 10, fill="black")
        pump_coords = [xy(point.flow_rate_m3_s, point.head_m) for point in ordered]
        canvas.create_line(*[coordinate for point in pump_coords for coordinate in point], fill="#4472C4", width=2)
        system_coords = [
            xy(max_flow * index / 40, system_head(max_flow * index / 40, static_head, resistance))
            for index in range(41)
        ]
        canvas.create_line(*[coordinate for point in system_coords for coordinate in point], fill="#ED7D31", width=2)
        op = xy(operating_flow, system_head(operating_flow, static_head, resistance))
        canvas.create_oval(op[0] - 4, op[1] - 4, op[0] + 4, op[1] + 4, fill="red")
        canvas.create_text(100, 15, text="파랑: 펌프 곡선   주황: 시스템 곡선   빨강: 운전점", anchor="w")

    def _open_network(self) -> None:
        window = tk.Toplevel(self)
        window.title("직렬·병렬 관로 학습 도구")
        window.geometry("560x430")
        frame = ttk.Frame(window, padding=12)
        frame.pack(fill="both", expand=True)
        mode = tk.StringVar(value="series")
        ttk.Label(frame, text="관로 등가저항 분석", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(frame, text="각 관로의 저항 R을 쉼표로 입력 (H_loss = R Q²)").pack(anchor="w", pady=6)
        resistance_entry = ttk.Entry(frame)
        resistance_entry.insert(0, "1000,2000,1500")
        resistance_entry.pack(fill="x")
        mode_frame = ttk.Frame(frame)
        mode_frame.pack(anchor="w", pady=6)
        ttk.Radiobutton(mode_frame, text="직렬", variable=mode, value="series").pack(side="left")
        ttk.Radiobutton(mode_frame, text="병렬", variable=mode, value="parallel").pack(side="left", padx=12)
        flow_entry = ttk.Entry(frame)
        flow_entry.insert(0, "0.02")
        ttk.Label(frame, text="병렬 전체 유량 Q (m³/s, 병렬에서 사용)").pack(anchor="w")
        flow_entry.pack(fill="x")
        output = tk.Text(frame, height=8, state="disabled")
        output.pack(fill="x", pady=8)
        diagram = tk.Canvas(frame, height=140, background="white")
        diagram.pack(fill="both", expand=True)

        def calculate() -> None:
            try:
                resistances = [float(value.strip()) for value in resistance_entry.get().split(",")]
                if mode.get() == "series":
                    equivalent = series_resistance(resistances)
                    lines = [
                        "직렬: R_eq = R₁ + R₂ + ...",
                        f"R_eq = {equivalent:.6g}",
                    ]
                    self._draw_network_canvas(diagram, len(resistances), False)
                else:
                    equivalent = parallel_resistance(resistances)
                    total_flow = float(flow_entry.get())
                    flows = parallel_branch_flows(total_flow, resistances)
                    lines = [
                        "병렬: 1/sqrt(R_eq) = Σ 1/sqrt(R_i)",
                        f"R_eq = {equivalent:.6g}",
                        f"분기 유량: {', '.join(f'{flow:.6g}' for flow in flows)} m³/s",
                        f"유량 합계: {sum(flows):.6g} m³/s",
                    ]
                    self._draw_network_canvas(diagram, len(resistances), True)
                output.configure(state="normal")
                output.delete("1.0", tk.END)
                output.insert("1.0", "\n".join(lines))
                output.configure(state="disabled")
            except (TypeError, ValueError, ZeroDivisionError) as exc:
                messagebox.showerror("관로 입력 오류", str(exc), parent=window)

        ttk.Button(frame, text="등가저항 계산", command=calculate).pack(anchor="e")
        calculate()

    @staticmethod
    def _draw_network_canvas(canvas: tk.Canvas, count: int, parallel: bool) -> None:
        canvas.delete("all")
        width = max(canvas.winfo_width(), 500)
        height = max(canvas.winfo_height(), 120)
        if parallel:
            for index in range(count):
                y = 25 + index * (height - 50) / max(count - 1, 1)
                canvas.create_line(20, height / 2, 90, y, fill="#4472C4", width=2)
                canvas.create_rectangle(90, y - 8, width - 90, y + 8, fill="#D9EAF7")
                canvas.create_line(width - 90, y, width - 20, height / 2, fill="#4472C4", width=2)
        else:
            y = height / 2
            for index in range(count):
                left = 30 + index * (width - 60) / count
                right = 30 + (index + 1) * (width - 60) / count
                canvas.create_line(left, y, left + 12, y, fill="#4472C4", width=2)
                canvas.create_rectangle(left + 12, y - 10, right - 12, y + 10, fill="#D9EAF7")
                canvas.create_line(right - 12, y, right, y, fill="#4472C4", width=2)

    def _base_analysis_kwargs(self) -> dict[str, object]:
        flow = self._unit_value(
            self.flow_entry, "flow", self.flow_label.cget("text"), self.flow_unit_combo.get()
        )
        kwargs: dict[str, object] = {
            "diameter_m": self._unit_value(
                self.diameter_entry, "length", "관경", self.diameter_unit_combo.get()
            ),
            "pipe_length_m": self._unit_value(
                self.length_entry, "length", "관 길이", self.length_unit_combo.get()
            ),
            "temperature_c": self._number(self.temperature_entry, "물 온도", optional=True),
            "minor_loss_coefficient": self._nonnegative_number(
                self.minor_k_entry, "부차적 손실계수"
            ),
            "static_head_m": self._nonnegative_number(
                self.static_head_entry, "정수두/높이차"
            ),
            "pump_efficiency": self._number(
                self.efficiency_entry, "펌프 효율", optional=True
            ),
            "minor_loss_components": self._parse_components(),
            "transitional_policy": self.transition_policy.get(),
            "fluid": self.fluid_combo.get(),
        }
        if self.fluid_combo.get() == "custom":
            kwargs["density_kg_m3"] = self._positive_number(self.density_entry, "밀도")
            kwargs["dynamic_viscosity_pa_s"] = self._positive_number(
                self.viscosity_entry, "동적 점성계수"
            )
        if self.flow_mode.get() == "flow_rate":
            kwargs["flow_rate_m3_s"] = flow
        else:
            kwargs["velocity_m_s"] = flow
        if self.roughness_mode.get() == "material":
            kwargs["material"] = self.material_combo.get()
        else:
            kwargs["absolute_roughness_m"] = self._nonnegative_number(
                self.roughness_entry, "절대조도"
            )
        return kwargs

    def _open_advanced_analysis(self) -> None:
        window = tk.Toplevel(self)
        window.title("민감도·불확실성 분석")
        window.geometry("650x520")
        frame = ttk.Frame(window, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="민감도 및 불확실성", font=("Segoe UI", 13, "bold")).pack(
            anchor="w"
        )
        ttk.Label(frame, text="민감도 변수").pack(anchor="w", pady=(8, 2))
        parameter = ttk.Combobox(
            frame,
            values=("flow_rate_m3_s", "diameter_m", "pipe_length_m", "static_head_m"),
            state="readonly",
        )
        parameter.set("flow_rate_m3_s")
        parameter.pack(fill="x")
        ttk.Label(frame, text="민감도 값(쉼표 구분)").pack(anchor="w", pady=(6, 2))
        values_entry = ttk.Entry(frame)
        values_entry.insert(0, "0.005,0.01,0.015,0.02")
        values_entry.pack(fill="x")
        ttk.Label(frame, text="불확실성 범위: 변수=최소:최대 (쉼표 구분)").pack(
            anchor="w", pady=(6, 2)
        )
        ranges_entry = ttk.Entry(frame)
        ranges_entry.insert(0, "flow_rate_m3_s=0.01:0.02")
        ranges_entry.pack(fill="x")
        samples_entry = ttk.Entry(frame, width=12)
        samples_entry.insert(0, "100")
        ttk.Label(frame, text="표본 수").pack(anchor="w", pady=(6, 2))
        samples_entry.pack(anchor="w")
        output = tk.Text(frame, height=13, state="disabled")
        output.pack(fill="both", expand=True, pady=8)

        def run() -> None:
            try:
                kwargs = self._base_analysis_kwargs()
                values = [float(value.strip()) for value in values_entry.get().split(",")]
                points = sensitivity_analysis(kwargs, parameter.get(), values)
                ranges: dict[str, tuple[float, float]] = {}
                for item in ranges_entry.get().split(","):
                    if not item.strip():
                        continue
                    name, bounds = item.split("=")
                    low, high = (float(value) for value in bounds.split(":"))
                    ranges[name.strip()] = (low, high)
                samples = monte_carlo_analysis(
                    kwargs, ranges, samples=int(samples_entry.get()), seed=0
                ) if ranges else ()
                lines = ["[민감도 결과]"]
                lines.extend(
                    f"{point.parameter:.6g} -> 손실수두 {point.result.total_head_loss_m:.6f} m"
                    for point in points
                )
                if samples:
                    summary = summarize_results(samples)
                    lines.extend(
                        ["", "[불확실성 요약]"]
                        + [f"{key}: {value:.6g}" for key, value in summary.items()]
                    )
                output.configure(state="normal")
                output.delete("1.0", tk.END)
                output.insert("1.0", "\n".join(lines))
                output.configure(state="disabled")
            except (TypeError, ValueError, RuntimeError) as exc:
                messagebox.showerror("고급 분석 오류", str(exc), parent=window)

        ttk.Button(frame, text="분석 실행", command=run).pack(anchor="e")
        run()

    def _open_network_solver(self) -> None:
        window = tk.Toplevel(self)
        window.title("다중노드 관망 해석")
        window.geometry("700x560")
        frame = ttk.Frame(window, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="노드와 관로를 텍스트로 입력", font=("Segoe UI", 13, "bold")).pack(
            anchor="w"
        )
        ttk.Label(frame, text="노드: 이름=수두, 미지수는 이름=? (예: source=10,junction=?,sink=0)").pack(
            anchor="w", pady=(8, 2)
        )
        nodes_entry = ttk.Entry(frame)
        nodes_entry.insert(0, "source=10,junction=?,sink=0")
        nodes_entry.pack(fill="x")
        ttk.Label(frame, text="관로: 이름:시작:끝:저항 (예: main:source:junction:1000)").pack(
            anchor="w", pady=(6, 2)
        )
        edges_entry = ttk.Entry(frame)
        edges_entry.insert(0, "main:source:junction:1000,branch:junction:sink:1000")
        edges_entry.pack(fill="x")
        ttk.Label(frame, text="수요: 노드=유량 (양수는 인출, 예: sink=0.01)").pack(
            anchor="w", pady=(6, 2)
        )
        demands_entry = ttk.Entry(frame)
        demands_entry.insert(0, "junction=0")
        demands_entry.pack(fill="x")
        output = tk.Text(frame, height=16, state="disabled")
        output.pack(fill="both", expand=True, pady=8)

        def run() -> None:
            try:
                nodes: dict[str, float | None] = {}
                for item in nodes_entry.get().split(","):
                    name, value = item.split("=")
                    nodes[name.strip()] = None if value.strip() == "?" else float(value)
                edges = []
                for item in edges_entry.get().split(","):
                    name, start, end, resistance = item.split(":")
                    edges.append(NetworkEdge(name, start, end, float(resistance)))
                demands = {}
                for item in demands_entry.get().split(","):
                    if item.strip():
                        name, value = item.split("=")
                        demands[name.strip()] = float(value)
                result = solve_network(nodes, edges, demands)
                lines = ["[노드 수두]"]
                lines.extend(f"{name}: {head:.6f} m" for name, head in result.heads_m.items())
                lines.append("\n[관로 유량]")
                lines.extend(f"{name}: {flow:.6g} m³/s" for name, flow in result.flows_m3_s.items())
                lines.append(f"\n반복 횟수: {result.iterations}, 최대 잔차: {result.residual:.3g}")
                output.configure(state="normal")
                output.delete("1.0", tk.END)
                output.insert("1.0", "\n".join(lines))
                output.configure(state="disabled")
            except (TypeError, ValueError, RuntimeError) as exc:
                messagebox.showerror("관망 입력 오류", str(exc), parent=window)

        ttk.Button(frame, text="관망 계산", command=run).pack(anchor="e")
        run()

    def _open_hydraulic_diameter(self) -> None:
        window = tk.Toplevel(self)
        window.title("수력직경 계산")
        frame = ttk.Frame(window, padding=12)
        frame.pack(fill="both", expand=True)
        entries = []
        for label, default in (("폭 (m)", "0.2"), ("높이 (m)", "0.1")):
            ttk.Label(frame, text=label).pack(anchor="w")
            entry = ttk.Entry(frame)
            entry.insert(0, default)
            entry.pack(fill="x", pady=(0, 6))
            entries.append(entry)
        result = ttk.Label(frame, text="")
        result.pack(anchor="w", pady=6)

        def calculate() -> None:
            try:
                diameter = rectangular_hydraulic_diameter(
                    float(entries[0].get()), float(entries[1].get())
                )
                result.configure(
                    text=f"D_h = 4A/P = {diameter:.6f} m\n"
                    "이 값을 Reynolds 수와 Darcy-Weisbach 계산의 대표 직경으로 사용할 수 있습니다."
                )
            except ValueError as exc:
                messagebox.showerror("수력직경 입력 오류", str(exc), parent=window)

        ttk.Button(frame, text="계산", command=calculate).pack(anchor="e")
        calculate()

    def _open_pump_combination(self) -> None:
        window = tk.Toplevel(self)
        window.title("펌프 직렬·병렬 조합")
        frame = ttk.Frame(window, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="각 펌프 곡선을 Q:H 형식으로 입력").pack(anchor="w")
        first = ttk.Entry(frame)
        first.insert(0, "0:30,0.02:15")
        first.pack(fill="x", pady=4)
        second = ttk.Entry(frame)
        second.insert(0, "0:25,0.02:12")
        second.pack(fill="x", pady=4)
        mode = ttk.Combobox(frame, values=("series", "parallel"), state="readonly")
        mode.set("series")
        mode.pack(anchor="w", pady=4)
        result = tk.Text(frame, height=8, state="disabled")
        result.pack(fill="both", expand=True)

        def calculate() -> None:
            try:
                curves = []
                for entry in (first, second):
                    curves.append(
                        tuple(
                            PumpCurvePoint(float(flow), float(head))
                            for flow, head in (
                                part.split(":") for part in entry.get().split(",")
                            )
                        )
                    )
                combined = combine_pump_curves(curves, mode.get())
                text = "\n".join(
                    f"Q={point.flow_rate_m3_s:.6g} m³/s, H={point.head_m:.6g} m"
                    for point in combined
                )
                result.configure(state="normal")
                result.delete("1.0", tk.END)
                result.insert("1.0", text)
                result.configure(state="disabled")
            except (TypeError, ValueError, ZeroDivisionError) as exc:
                messagebox.showerror("펌프 조합 입력 오류", str(exc), parent=window)

        ttk.Button(frame, text="조합 계산", command=calculate).pack(anchor="e")
        calculate()

    def _save_report(self) -> None:
        if self.result is None:
            messagebox.showwarning("알림", "먼저 계산을 실행하세요.", parent=self)
            return
        path = OUTPUT_DIRECTORY / "darcy_weisbach_report.txt"
        try:
            save_report(self.result, path)
        except OSError as exc:
            messagebox.showerror("보고서 저장 오류", str(exc), parent=self)
            return
        messagebox.showinfo("저장 완료", f"보고서를 저장했습니다.\n{path}", parent=self)

    def _save_plot(self) -> None:
        if self.result is None:
            messagebox.showwarning("알림", "먼저 계산을 실행하세요.", parent=self)
            return
        path = OUTPUT_DIRECTORY / "darcy_weisbach_analysis.png"
        try:
            save_plot(self.result, path)
        except (OSError, RuntimeError) as exc:
            messagebox.showerror("그래프 저장 오류", str(exc), parent=self)
            return
        messagebox.showinfo("저장 완료", f"그래프를 저장했습니다.\n{path}", parent=self)

    def _save_pdf_report(self) -> None:
        if self.result is None:
            messagebox.showwarning("알림", "먼저 계산을 실행하세요.", parent=self)
            return
        path = filedialog.asksaveasfilename(
            parent=self,
            title="PDF 보고서 저장",
            initialdir=str(OUTPUT_DIRECTORY),
            defaultextension=".pdf",
            initialfile="darcy_weisbach_report.pdf",
            filetypes=[("PDF 파일", "*.pdf")],
        )
        if not path:
            return
        try:
            from matplotlib.backends.backend_pdf import PdfPages
            import matplotlib.pyplot as plt
            configure_matplotlib_korean()
            with PdfPages(path) as pdf:
                figure = plt.figure(figsize=(8.27, 11.69))
                figure.text(
                    0.08, 0.95,
                    "Darcy-Weisbach 관로 분석 보고서",
                    fontsize=16, weight="bold", va="top",
                )
                figure.text(
                    0.08, 0.90,
                    self.result_text.get("1.0", tk.END),
                    fontsize=9, va="top", family="DejaVu Sans",
                )
                pdf.savefig(figure, bbox_inches="tight")
                plt.close(figure)
            messagebox.showinfo("저장 완료", f"PDF 보고서를 저장했습니다.\n{path}", parent=self)
        except (OSError, RuntimeError, ImportError) as exc:
            messagebox.showerror("PDF 보고서 저장 오류", str(exc), parent=self)

    def _show_result_comparison(self) -> None:
        if len(self.batch_results) < 2:
            messagebox.showwarning(
                "알림", "비교하려면 두 개 이상의 계산 결과가 필요합니다.", parent=self
            )
            return
        window = tk.Toplevel(self)
        window.title("계산 결과 비교")
        window.geometry("760x420")
        text = tk.Text(window, state="normal", font=("Consolas", 10))
        text.pack(fill="both", expand=True, padx=12, pady=12)
        text.insert("1.0", "기간/행\t유속(m/s)\tRe\t손실수두(m)\t압력(kPa)\t펌프동력(kW)\n")
        text.insert("end", "-" * 100 + "\n")
        for period, result in self.batch_results:
            power = "" if result.pump_power_w is None else f"{result.pump_power_w / 1000:.4g}"
            text.insert(
                "end",
                f"{period or '직접 입력'}\t{result.velocity_m_s:.4g}\t"
                f"{result.reynolds_number:.4g}\t{result.total_head_loss_m:.4g}\t"
                f"{result.pressure_loss_pa / 1000:.4g}\t{power}\n",
            )
        text.configure(state="disabled")

    def _input_row_from_form(self) -> dict[str, str]:
        flow_value = self.flow_entry.get().strip()
        flow_si = (
            float(flow_value) * UNIT_FACTORS["flow"][self.flow_unit_combo.get()]
            if flow_value
            else ""
        )
        diameter = self.diameter_entry.get().strip()
        length = self.length_entry.get().strip()
        row = {
            "timestamp": "",
            "flow_rate_m3_s": str(flow_si) if self.flow_mode.get() == "flow_rate" else "",
            "velocity_m_s": flow_value if self.flow_mode.get() == "velocity" else "",
            "diameter_m": str(float(diameter) * UNIT_FACTORS["length"][self.diameter_unit_combo.get()]),
            "pipe_length_m": str(float(length) * UNIT_FACTORS["length"][self.length_unit_combo.get()]),
            "material": self.material_combo.get()
            if self.roughness_mode.get() == "material"
            else "",
            "absolute_roughness_m": self.roughness_entry.get().strip()
            if self.roughness_mode.get() == "roughness"
            else "",
            "temperature_c": self.temperature_entry.get().strip(),
            "minor_loss_coefficient": self.minor_k_entry.get().strip(),
            "static_head_m": self.static_head_entry.get().strip(),
            "minor_loss_components": self.minor_components_entry.get().strip(),
            "pump_efficiency": self.efficiency_entry.get().strip(),
            "transitional_policy": self.transition_policy.get(),
        }
        return row

    def _save_input_csv(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self,
            title="입력 데이터 CSV 저장",
            initialdir=str(CSV_DIRECTORY),
            defaultextension=".csv",
            initialfile="darcy_weisbach_input.csv",
            filetypes=[("CSV 파일", "*.csv")],
        )
        if not path:
            return
        try:
            row = self._input_row_from_form()
            if not row["flow_rate_m3_s"] and not row["velocity_m_s"]:
                self.flow_entry.focus_set()
                raise ValueError("유량 또는 유속을 입력하세요.")
            self._positive_number(self.flow_entry, self.flow_label.cget("text"))
            self._positive_number(self.diameter_entry, "관경")
            self._positive_number(self.length_entry, "관 길이")
            self._number(self.temperature_entry, "물 온도", optional=True)
            self._nonnegative_number(self.minor_k_entry, "부차적 손실계수")
            self._nonnegative_number(self.static_head_entry, "정수두/높이차")
            efficiency = self._number(
                self.efficiency_entry, "펌프 효율", optional=True
            )
            if efficiency is not None and not 0 < efficiency <= 1:
                raise ValueError("펌프 효율은 0보다 크고 1 이하여야 합니다.")
            if self.roughness_mode.get() == "roughness":
                self._nonnegative_number(self.roughness_entry, "절대조도")
            with Path(path).open("w", encoding="utf-8-sig", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=list(row))
                writer.writeheader()
                writer.writerow(row)
        except (OSError, UnicodeError, ValueError) as exc:
            messagebox.showerror("입력 CSV 저장 오류", str(exc), parent=self)
            return
        messagebox.showinfo("저장 완료", f"입력 데이터를 저장했습니다.\n{path}", parent=self)

    def _save_input_template_csv(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self,
            title="입력 CSV 양식 저장",
            initialdir=str(CSV_DIRECTORY),
            defaultextension=".csv",
            initialfile="darcy_weisbach_input_template.csv",
            filetypes=[("CSV 파일", "*.csv")],
        )
        if not path:
            return
        fields = [
            "timestamp", "flow_rate_m3_s", "velocity_m_s", "diameter_m",
            "pipe_length_m", "material", "absolute_roughness_m", "temperature_c",
            "minor_loss_coefficient", "minor_loss_components", "static_head_m",
            "pump_efficiency", "transitional_policy", "fluid",
            "density_kg_m3", "dynamic_viscosity_pa_s",
        ]
        rows = [
            {
                "timestamp": "2026-01-01",
                "flow_rate_m3_s": "0.015",
                "velocity_m_s": "",
                "diameter_m": "0.1",
                "pipe_length_m": "20",
                "material": "PVC",
                "absolute_roughness_m": "",
                "temperature_c": "20",
                "minor_loss_coefficient": "0",
                "minor_loss_components": "",
                "static_head_m": "0",
                "pump_efficiency": "0.75",
                "transitional_policy": "warn",
                "fluid": "water",
                "density_kg_m3": "",
                "dynamic_viscosity_pa_s": "",
            },
            {
                "timestamp": "2026-01-02",
                "flow_rate_m3_s": "",
                "velocity_m_s": "1.5",
                "diameter_m": "0.1",
                "pipe_length_m": "20",
                "material": "",
                "absolute_roughness_m": "0.0000015",
                "temperature_c": "20",
                "minor_loss_coefficient": "0.5",
                "minor_loss_components": "엘보:2:0.3",
                "static_head_m": "2",
                "pump_efficiency": "",
                "transitional_policy": "warn",
                "fluid": "water",
                "density_kg_m3": "",
                "dynamic_viscosity_pa_s": "",
            },
        ]
        try:
            with Path(path).open("w", encoding="utf-8-sig", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
        except (OSError, UnicodeError) as exc:
            messagebox.showerror("입력 CSV 양식 저장 오류", str(exc), parent=self)
            return
        messagebox.showinfo(
            "저장 완료",
            "입력 CSV 양식을 저장했습니다.\n"
            "예시 행을 수정하거나 추가한 뒤 CSV 불러오기 또는 CSV 일괄 계산에 사용하세요.\n"
            f"{path}",
            parent=self,
        )

    def _save_current_results_csv(self) -> None:
        if not self.batch_results:
            messagebox.showwarning("알림", "먼저 데이터를 계산하세요.", parent=self)
            return
        try:
            criteria = self._read_criteria()
            start = self.period_start_entry.get().strip()
            end = self.period_end_entry.get().strip()
            for value, label in ((start, "시작 기간"), (end, "종료 기간")):
                if value:
                    datetime.strptime(value, "%Y-%m-%d")
            if start and end and start > end:
                raise ValueError("시작 기간은 종료 기간보다 빠르거나 같아야 합니다.")
        except ValueError as exc:
            messagebox.showerror("조건 오류", str(exc), parent=self)
            return
        visible = [
            item for item in self.batch_results
            if (not start or not item[0] or item[0][:10] >= start)
            and (not end or not item[0] or item[0][:10] <= end)
        ]
        if not visible:
            messagebox.showwarning("알림", "현재 조건에 맞는 결과가 없습니다.", parent=self)
            return
        path = filedialog.asksaveasfilename(
            parent=self,
            title="처리 결과 CSV 저장",
            initialdir=str(CSV_DIRECTORY),
            defaultextension=".csv",
            initialfile="darcy_weisbach_filtered_results.csv",
            filetypes=[("CSV 파일", "*.csv")],
        )
        if not path:
            return
        try:
            self._write_results_csv(visible, Path(path), criteria)
        except (OSError, UnicodeError) as exc:
            messagebox.showerror("결과 CSV 저장 오류", str(exc), parent=self)
            return
        messagebox.showinfo(
            "저장 완료",
            f"{len(visible)}개 처리 결과를 저장했습니다.\n{path}",
            parent=self,
        )

    def _load_csv(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="입력 CSV 선택",
            initialdir=str(CSV_DIRECTORY),
            filetypes=[("CSV 파일", "*.csv"), ("모든 파일", "*.*")],
        )
        if not path:
            return
        try:
            with Path(path).open("r", encoding="utf-8-sig", newline="") as file:
                reader = csv.DictReader(file)
                self._validate_csv_headers(reader.fieldnames)
                row = next(reader, None)
                if row is None:
                    raise ValueError("CSV에 데이터 행이 없습니다.")
                row = self._normalise_csv_row(row, 2)
            self._set_form_from_row(row)
            messagebox.showinfo(
                "불러오기 완료",
                "첫 번째 데이터 행을 입력창에 불러왔습니다.\n"
                "여러 행을 계산하려면 'CSV 일괄 계산'을 사용하세요.",
                parent=self,
            )
        except (OSError, UnicodeError, ValueError) as exc:
            messagebox.showerror("CSV 불러오기 오류", str(exc), parent=self)

    def _set_form_from_row(self, row: dict[str, str | None]) -> None:
        flow_rate = self._row_value(row, "flow_rate_m3_s")
        velocity = self._row_value(row, "velocity_m_s")
        if bool(flow_rate) == bool(velocity):
            raise ValueError(
                "flow_rate_m3_s와 velocity_m_s 중 정확히 하나가 필요합니다."
            )
        if flow_rate:
            self.flow_mode.set("flow_rate")
            self._set_entry(self.flow_entry, flow_rate)
        else:
            self.flow_mode.set("velocity")
            self._set_entry(self.flow_entry, velocity)
        self._update_flow_label()
        self._set_entry(self.diameter_entry, self._row_value(row, "diameter_m"))
        self._set_entry(self.length_entry, self._row_value(row, "pipe_length_m"))
        self.diameter_unit_combo.set("m")
        self.length_unit_combo.set("m")
        material = self._row_value(row, "material")
        roughness = self._row_value(row, "absolute_roughness_m")
        if bool(material) == bool(roughness):
            raise ValueError(
                "material과 absolute_roughness_m 중 정확히 하나가 필요합니다."
            )
        if material:
            self.roughness_mode.set("material")
            self.material_combo.set(material)
        else:
            self.roughness_mode.set("roughness")
            self._update_roughness_state()
            self._set_entry(self.roughness_entry, roughness)
        for key, entry in (
            ("temperature_c", self.temperature_entry),
            ("minor_loss_coefficient", self.minor_k_entry),
            ("static_head_m", self.static_head_entry),
            ("minor_loss_components", self.minor_components_entry),
            ("pump_efficiency", self.efficiency_entry),
        ):
            self._set_entry(entry, self._row_value(row, key, default=""))
        fluid = self._row_value(row, "fluid", "water") or "water"
        self.fluid_combo.set(fluid)
        self._update_fluid_state()
        if fluid == "custom":
            self._set_entry(self.density_entry, self._row_value(row, "density_kg_m3"))
            self._set_entry(
                self.viscosity_entry,
                self._row_value(row, "dynamic_viscosity_pa_s"),
            )
        self.transition_policy.set(
            self._row_value(row, "transitional_policy", "warn") or "warn"
        )
        self._update_roughness_state()

    @staticmethod
    def _row_value(
        row: dict[str, str | None], key: str, default: str = ""
    ) -> str:
        value = row.get(key)
        return default if value is None else value.strip()

    @staticmethod
    def _validate_csv_headers(fieldnames: list[str] | None) -> None:
        if not fieldnames:
            raise ValueError("CSV에 헤더 행이 없습니다.")
        headers = {field.strip() for field in fieldnames if field}
        for alternatives in CSV_REQUIRED_ALTERNATIVES:
            if not any(name in headers for name in alternatives):
                raise ValueError(
                    "CSV 필수 열이 없습니다: " + " 또는 ".join(alternatives)
                )
        for unit_name in ("flow_unit", "velocity_unit", "diameter_unit",
                          "length_unit", "roughness_unit"):
            if unit_name in headers:
                continue
        allowed_units = {
            "flow_unit": set(UNIT_FACTORS["flow"]),
            "velocity_unit": {"m/s"},
            "diameter_unit": set(UNIT_FACTORS["length"]),
            "length_unit": set(UNIT_FACTORS["length"]),
            "roughness_unit": set(UNIT_FACTORS["length"]),
        }
        unknown = [
            field for field in headers
            if field.endswith("_unit") and field not in allowed_units
        ]
        if unknown:
            raise ValueError(f"지원하지 않는 단위 열: {', '.join(sorted(unknown))}")

    @classmethod
    def _normalise_csv_row(
        cls, row: dict[str, str | None], row_number: int
    ) -> dict[str, str | None]:
        normalised = dict(row)

        def value(key: str) -> str:
            raw = normalised.get(key)
            return "" if raw is None else raw.strip()

        def scaled(
            base_key: str,
            unit_key: str,
            factor_group: str,
            fallback_key: str | None = None,
        ) -> None:
            if fallback_key and value(base_key) and value(fallback_key):
                raise ValueError(
                    f"{row_number}행: {base_key}와 {fallback_key} 중 하나만 입력하세요."
                )
            source_key = base_key if value(base_key) else fallback_key
            if source_key is None or not value(source_key):
                return
            unit = value(unit_key) or next(iter(UNIT_FACTORS[factor_group]))
            factors = UNIT_FACTORS[factor_group]
            if unit not in factors:
                raise ValueError(
                    f"{row_number}행: {unit_key}는 {', '.join(factors)} 중 하나여야 합니다."
                )
            try:
                number = float(value(source_key))
            except ValueError as exc:
                raise ValueError(f"{row_number}행: {source_key}에 숫자를 입력하세요.") from exc
            if not math.isfinite(number):
                raise ValueError(f"{row_number}행: {source_key}에는 유한한 숫자가 필요합니다.")
            normalised[base_key] = str(number * factors[unit])

        scaled("flow_rate_m3_s", "flow_unit", "flow", "flow_rate")
        scaled("diameter_m", "diameter_unit", "length", "diameter")
        scaled("pipe_length_m", "length_unit", "length", "pipe_length")
        scaled("absolute_roughness_m", "roughness_unit", "length", "absolute_roughness")
        if (value("flow_rate_m3_s") or value("flow_rate")) and (
            value("velocity_m_s") or value("velocity")
        ):
            raise ValueError(
                f"{row_number}행: 유량과 유속 중 하나만 입력하세요."
            )
        if (value("material") and value("absolute_roughness_m")) or (
            value("material") and value("absolute_roughness")
        ):
            raise ValueError(
                f"{row_number}행: 재질과 절대조도 중 하나만 입력하세요."
            )
        if value("velocity_m_s") or value("velocity"):
            velocity_key = "velocity_m_s" if value("velocity_m_s") else "velocity"
            unit = value("velocity_unit") or "m/s"
            if unit != "m/s":
                raise ValueError(f"{row_number}행: velocity_unit은 m/s만 지원합니다.")
            normalised["velocity_m_s"] = value(velocity_key)

        timestamp = value("timestamp")
        cls._validate_timestamp(timestamp, row_number)
        return normalised

    @staticmethod
    def _set_entry(entry: ttk.Entry, value: str) -> None:
        entry.delete(0, tk.END)
        entry.insert(0, value)

    def _row_to_result(self, row: dict[str, str | None], row_number: int) -> AnalysisResult:
        try:
            flow_rate = self._row_value(row, "flow_rate_m3_s")
            velocity = self._row_value(row, "velocity_m_s")
            if bool(flow_rate) == bool(velocity):
                raise ValueError(
                    "flow_rate_m3_s와 velocity_m_s 중 정확히 하나가 필요합니다."
                )
            material = self._row_value(row, "material")
            roughness = self._row_value(row, "absolute_roughness_m")
            if bool(material) == bool(roughness):
                raise ValueError(
                    "material과 absolute_roughness_m 중 정확히 하나가 필요합니다."
                )
            kwargs = {
                "diameter_m": float(self._row_value(row, "diameter_m")),
                "pipe_length_m": float(self._row_value(row, "pipe_length_m")),
                "temperature_c": self._optional_row_float(row, "temperature_c"),
                "minor_loss_coefficient": float(
                    self._row_value(row, "minor_loss_coefficient", "0")
                ),
                "static_head_m": float(
                    self._row_value(row, "static_head_m", "0")
                ),
                "pump_efficiency": self._optional_row_float(row, "pump_efficiency"),
                "transitional_policy": self._row_value(
                    row, "transitional_policy", "warn"
                ) or "warn",
                "fluid": self._row_value(row, "fluid", "water") or "water",
            }
            if kwargs["fluid"] == "custom":
                kwargs["density_kg_m3"] = float(
                    self._row_value(row, "density_kg_m3")
                )
                kwargs["dynamic_viscosity_pa_s"] = float(
                    self._row_value(row, "dynamic_viscosity_pa_s")
                )
            components_text = self._row_value(row, "minor_loss_components")
            if components_text:
                components = {}
                for item in components_text.split(","):
                    name, count, coefficient = (
                        part.strip() for part in item.split(":")
                    )
                    components[name] = (int(count), float(coefficient))
                kwargs["minor_loss_components"] = components
            if flow_rate:
                kwargs["flow_rate_m3_s"] = float(flow_rate)
            else:
                kwargs["velocity_m_s"] = float(velocity)
            if material:
                kwargs["material"] = material
            else:
                kwargs["absolute_roughness_m"] = float(roughness)
            return analyze(**kwargs)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{row_number}행: {exc}") from exc

    def _optional_row_float(
        self, row: dict[str, str | None], key: str
    ) -> float | None:
        value = self._row_value(row, key)
        return None if not value else float(value)

    @staticmethod
    def _validate_timestamp(value: str, row_number: int) -> str:
        if value:
            try:
                datetime.fromisoformat(value)
            except ValueError as exc:
                raise ValueError(
                    f"{row_number}행: timestamp는 YYYY-MM-DD 또는 "
                    "YYYY-MM-DD HH:MM:SS 형식이어야 합니다."
                ) from exc
        return value

    def _calculate_csv(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="일괄 계산할 CSV 선택",
            initialdir=str(CSV_DIRECTORY),
            filetypes=[("CSV 파일", "*.csv"), ("모든 파일", "*.*")],
        )
        if not path:
            return
        try:
            with Path(path).open("r", encoding="utf-8-sig", newline="") as file:
                reader = csv.DictReader(file)
                self._validate_csv_headers(reader.fieldnames)
                results = []
                errors: list[tuple[int, str]] = []
                for number, row in enumerate(reader, start=2):
                    try:
                        row = self._normalise_csv_row(row, number)
                        timestamp = self._row_value(row, "timestamp")
                        results.append((timestamp, self._row_to_result(row, number)))
                    except (KeyError, TypeError, ValueError) as exc:
                        errors.append((number, str(exc)))
            if not results:
                if errors:
                    raise ValueError("계산 가능한 행이 없습니다.\n" + "\n".join(errors[:20]))
                raise ValueError("CSV에 데이터 행이 없습니다.")
            output = filedialog.asksaveasfilename(
                parent=self,
                title="결과 CSV 저장",
                initialdir=str(CSV_DIRECTORY),
                defaultextension=".csv",
                initialfile="darcy_weisbach_results.csv",
                filetypes=[("CSV 파일", "*.csv")],
            )
            if not output:
                return
            self._write_results_csv(results, Path(output))
            error_output = None
            if errors:
                error_output = Path(output).with_name(
                    Path(output).stem + "_errors.csv"
                )
                self._write_csv_errors(errors, error_output)
            self.batch_results = results
            self.result = results[0][1]
            self._display_result(self.result)
            self._refresh_results()
            messagebox.showinfo(
                "일괄 계산 완료",
                f"{len(results)}개 행을 계산하고 저장했습니다.\n{output}"
                + (
                    f"\n\n오류로 제외된 행: {len(errors)}개\n"
                    + "\n".join(f"{number}행: {message}" for number, message in errors[:10])
                    + ("\n..." if len(errors) > 10 else "")
                    if errors else ""
                ),
                parent=self,
            )
        except (OSError, UnicodeError, ValueError) as exc:
            messagebox.showerror("CSV 일괄 계산 오류", str(exc), parent=self)

    def _write_results_csv(
        self,
        results: list[tuple[str, AnalysisResult]],
        path: Path,
        criteria: dict[str, float | None] | None = None,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fields = [
            "timestamp", "flow_rate_m3_s", "area_m2", "velocity_m_s", "reynolds_number",
            "relative_roughness", "flow_regime", "friction_factor",
            "major_head_loss_m", "minor_head_loss_m", "total_head_loss_m",
            "pressure_loss_pa", "pump_power_w", "warning", "criteria_status",
            "static_head_m", "required_pump_head_m", "diameter_m",
            "pipe_length_m", "absolute_roughness_m", "equations",
            "transitional_policy", "fluid", "density_kg_m3",
            "dynamic_viscosity_pa_s",
        ]
        with path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            for period, result in results:
                row = {
                    "timestamp": period,
                    **{
                        field: getattr(result, field)
                        for field in fields
                        if field not in {
                            "timestamp", "criteria_status", "transitional_policy"
                        }
                    },
                }
                row["criteria_status"] = (
                    self._row_status(result, criteria)
                    if criteria is not None
                    else ""
                )
                row["transitional_policy"] = result.transitional_policy
                row["fluid"] = result.fluid
                row["density_kg_m3"] = result.density_kg_m3
                row["dynamic_viscosity_pa_s"] = result.dynamic_viscosity_pa_s
                row["equations"] = " | ".join(result.equations)
                writer.writerow(row)

    @staticmethod
    def _write_csv_errors(
        errors: list[tuple[int, str]], path: Path
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["row_number", "error_message"])
            writer.writerows(errors)

    def _project_data(self) -> dict[str, object]:
        return {
            "input": self._input_row_from_form(),
            "criteria": {
                "max_velocity": self.max_velocity_entry.get(),
                "max_head_loss": self.max_head_loss_entry.get(),
                "max_pressure_loss": self.max_pressure_loss_entry.get(),
                "period_start": self.period_start_entry.get(),
                "period_end": self.period_end_entry.get(),
            },
            "graph_metric": self.graph_metric.get(),
            "transitional_policy": self.transition_policy.get(),
            "fluid": self.fluid_combo.get(),
            "density_kg_m3": self.density_entry.get().strip(),
            "dynamic_viscosity_pa_s": self.viscosity_entry.get().strip(),
        }

    def _save_project(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self,
            title="프로젝트 저장",
            defaultextension=".json",
            initialfile="darcy_weisbach_project.json",
            filetypes=[("JSON 프로젝트", "*.json")],
        )
        if not path:
            return
        try:
            with Path(path).open("w", encoding="utf-8") as file:
                json.dump(self._project_data(), file, ensure_ascii=False, indent=2)
        except (OSError, TypeError, ValueError) as exc:
            messagebox.showerror("프로젝트 저장 오류", str(exc), parent=self)
            return
        messagebox.showinfo("저장 완료", f"프로젝트를 저장했습니다.\n{path}", parent=self)

    def _load_project(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="프로젝트 열기",
            filetypes=[("JSON 프로젝트", "*.json"), ("모든 파일", "*.*")],
        )
        if not path:
            return
        try:
            with Path(path).open("r", encoding="utf-8") as file:
                data = json.load(file)
            input_data = data["input"]
            if not isinstance(input_data, dict):
                raise ValueError("프로젝트 입력 데이터가 올바르지 않습니다.")
            self._set_form_from_row({str(k): str(v) for k, v in input_data.items()})
            criteria = data.get("criteria", {})
            for key, entry in (
                ("max_velocity", self.max_velocity_entry),
                ("max_head_loss", self.max_head_loss_entry),
                ("max_pressure_loss", self.max_pressure_loss_entry),
                ("period_start", self.period_start_entry),
                ("period_end", self.period_end_entry),
            ):
                self._set_entry(entry, str(criteria.get(key, "")))
            self.graph_metric.set(data.get("graph_metric", "전체손실수두"))
            self.transition_policy.set(data.get("transitional_policy", "warn"))
        except (OSError, UnicodeError, KeyError, TypeError, ValueError) as exc:
            messagebox.showerror("프로젝트 열기 오류", str(exc), parent=self)
            return
        messagebox.showinfo("불러오기 완료", "프로젝트 입력값을 불러왔습니다.", parent=self)

    def _reset(self) -> None:
        self.flow_mode.set("flow_rate")
        self.transition_policy.set("warn")
        self.flow_entry.delete(0, tk.END)
        self.flow_entry.insert(0, "0.015")
        for entry, default in (
            (self.diameter_entry, "0.1"),
            (self.length_entry, "20"),
            (self.temperature_entry, "20"),
            (self.minor_k_entry, "0"),
            (self.static_head_entry, "0"),
            (self.efficiency_entry, ""),
        ):
            entry.delete(0, tk.END)
            entry.insert(0, default)
        self.roughness_mode.set("material")
        self.material_combo.set("commercial-steel")
        self.roughness_entry.configure(state="normal")
        self.roughness_entry.delete(0, tk.END)
        self.roughness_entry.configure(state="disabled")
        self.result = None
        self.batch_results = []
        for entry in (
            self.max_velocity_entry,
            self.max_head_loss_entry,
            self.max_pressure_loss_entry,
            self.period_start_entry,
            self.period_end_entry,
        ):
            entry.delete(0, tk.END)
        for item in self.result_table.get_children():
            self.result_table.delete(item)
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", tk.END)
        self.result_text.configure(state="disabled")
        self._draw_graph([], {})
        for key, unit in (
            ("velocity", "m/s"), ("head_loss", "m"), ("pressure", "kPa"),
            ("pump_head", "m"), ("reynolds", ""), ("power", "kW"),
        ):
            self._summary_values[key].configure(text=f"— {unit}".rstrip())
        self.status_var.set("입력 대기 · 계산할 조건을 입력하세요")
        self._update_flow_label()
        self._update_roughness_state()


def main() -> None:
    app = DarcyWeisbachApp()
    app.mainloop()


if __name__ == "__main__":
    main()
