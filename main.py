# -*- coding: utf-8 -*-
"""
比亚迪电池检测 - 主程序
基于Kivy框架，适配Android 10车机系统
"""

import os
import sys
import threading
import time
from datetime import datetime

# Kivy配置
from kivy.config import Config
Config.set('graphics', 'fullscreen', 'auto')
Config.set('graphics', 'window_state', 'maximized')

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.progressbar import ProgressBar
from kivy.uix.widget import Widget
from kivy.uix.popup import Popup
from kivy.clock import Clock
from kivy.graphics import Color, Line, Rectangle, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.utils import platform, get_color_from_hex
from kivy.core.window import Window
from kivy.animation import Animation

# 导入自定义模块
from bms_reader import BMSReader
from battery_analyzer import BatteryAnalyzer

# 颜色方案 - BYD专业蓝黑风格
COLORS = {
    'bg_dark': (0.08, 0.09, 0.12, 1),       # 深色背景
    'bg_card': (0.12, 0.14, 0.18, 1),       # 卡片背景
    'bg_card2': (0.15, 0.17, 0.22, 1),      # 卡片背景2
    'primary': (0.0, 0.6, 0.9, 1),          # 主色调蓝
    'primary_light': (0.2, 0.7, 1.0, 1),    # 浅蓝
    'accent_green': (0.0, 0.85, 0.5, 1),    # 绿色强调
    'accent_yellow': (1.0, 0.75, 0.1, 1),   # 黄色强调
    'accent_red': (0.95, 0.25, 0.25, 1),    # 红色强调
    'accent_orange': (1.0, 0.5, 0.1, 1),    # 橙色强调
    'text_primary': (0.95, 0.95, 0.97, 1),  # 主文字
    'text_secondary': (0.65, 0.68, 0.72, 1),# 次要文字
    'text_muted': (0.45, 0.48, 0.52, 1),    # 弱化文字
    'divider': (0.2, 0.22, 0.26, 1),        # 分割线
    'white': (1, 1, 1, 1),
    'black': (0, 0, 0, 1),
}


class RoundedCard(BoxLayout):
    """圆角卡片容器"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.padding = dp(12)
        self.spacing = dp(8)
        with self.canvas.before:
            Color(*COLORS['bg_card'])
            self.rect = RoundedRectangle(
                pos=self.pos, size=self.size, radius=[dp(8)]
            )
        self.bind(pos=self._update_rect, size=self._update_rect)

    def _update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size


class MetricLabel(BoxLayout):
    """指标标签组件"""
    def __init__(self, label, value, color=None, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'horizontal'
        self.size_hint_y = None
        self.height = dp(32)
        self.padding = [0, dp(2)]

        self.label_widget = Label(
            text=label,
            color=COLORS['text_secondary'],
            font_size=sp(13),
            halign='left',
            valign='middle',
            size_hint_x=0.45,
        )
        self.label_widget.bind(size=self.label_widget.setter('text_size'))

        if color is None:
            color = COLORS['text_primary']

        self.value_widget = Label(
            text=str(value),
            color=color,
            font_size=sp(13),
            bold=True,
            halign='right',
            valign='middle',
            size_hint_x=0.55,
        )
        self.value_widget.bind(size=self.value_widget.setter('text_size'))

        self.add_widget(self.label_widget)
        self.add_widget(self.value_widget)

    def update_value(self, value, color=None):
        self.value_widget.text = str(value)
        if color:
            self.value_widget.color = color


class StatusBadge(Label):
    """状态徽章"""
    def __init__(self, text, color=None, **kwargs):
        super().__init__(**kwargs)
        self.text = text
        self.size_hint = (None, None)
        self.size = (dp(60), dp(24))
        self.font_size = sp(11)
        self.bold = True
        self.halign = 'center'
        self.valign = 'middle'
        self.color = COLORS['white']
        if color:
            self.bg_color = color
        else:
            self.bg_color = COLORS['primary']
        self.bind(size=self.setter('text_size'))

        with self.canvas.before:
            Color(*self.bg_color)
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(12)])
        self.bind(pos=self._update, size=self._update)

    def _update(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size


class GaugeWidget(Widget):
    """仪表盘组件"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (None, None)
        self.size = (dp(160), dp(160))
        self.value = 0
        self.max_value = 100
        self.label = ""
        self.unit = ""
        self.color = COLORS['primary']
        self.bind(pos=self._update, size=self._update)
        self._update()

    def set_value(self, value, max_value=100, label="", unit=""):
        self.value = value
        self.max_value = max_value
        self.label = label
        self.unit = unit
        self._update()

    def _update(self, *args):
        self.canvas.clear()
        cx = self.width / 2
        cy = self.height / 2
        r = min(cx, cy) - dp(10)

        with self.canvas:
            # 背景圆环
            Color(*COLORS['bg_card2'])
            Line(circle=(cx, cy, r), width=dp(12))

            # 进度圆环
            if self.max_value > 0:
                ratio = min(self.value / self.max_value, 1.0)
                angle = 360 * ratio

                if ratio > 0.8:
                    Color(*COLORS['accent_green'])
                elif ratio > 0.5:
                    Color(*COLORS['accent_yellow'])
                elif ratio > 0.3:
                    Color(*COLORS['accent_orange'])
                else:
                    Color(*COLORS['accent_red'])

                Line(circle=(cx, cy, r), width=dp(12),
                     angle_start=90 - angle, angle_end=90,
                     cap='round')

        # 使用Label显示数值（通过add_widget处理）
        self._draw_labels(cx, cy)

    def _draw_labels(self, cx, cy):
        # 清除旧的label
        for child in self.children[:]:
            if isinstance(child, Label):
                self.remove_widget(child)

        # 数值标签
        val_label = Label(
            text=f"{self.value:.1f}",
            color=COLORS['text_primary'],
            font_size=sp(28),
            bold=True,
            pos=(self.x, self.y + cy - dp(20)),
            size=(self.width, dp(36)),
            halign='center',
            valign='middle',
        )
        val_label.bind(size=val_label.setter('text_size'))

        # 单位标签
        unit_label = Label(
            text=self.unit,
            color=COLORS['text_secondary'],
            font_size=sp(12),
            pos=(self.x, self.y + cy - dp(50)),
            size=(self.width, dp(20)),
            halign='center',
            valign='middle',
        )

        # 描述标签
        desc_label = Label(
            text=self.label,
            color=COLORS['text_muted'],
            font_size=sp(11),
            pos=(self.x, self.y + cy - dp(70)),
            size=(self.width, dp(20)),
            halign='center',
            valign='middle',
        )

        self.add_widget(val_label)
        self.add_widget(unit_label)
        self.add_widget(desc_label)


class DashboardTab(TabbedPanelItem):
    """仪表盘标签页"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.text = "仪表盘"
        self._build_ui()

    def _build_ui(self):
        layout = BoxLayout(orientation='vertical', padding=dp(12), spacing=dp(10))

        # 顶部标题
        header = BoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(40),
            spacing=dp(8)
        )
        title = Label(
            text="比亚迪电池检测",
            color=COLORS['text_primary'],
            font_size=sp(18),
            bold=True,
            halign='left',
            valign='middle',
            size_hint_x=0.7,
        )
        title.bind(size=title.setter('text_size'))
        self.status_badge = StatusBadge(text="检测中...", color=COLORS['primary'])
        header.add_widget(title)
        header.add_widget(self.status_badge)
        layout.add_widget(header)

        # SOH仪表盘区域
        gauge_row = BoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(180),
            spacing=dp(10),
            padding=[0, dp(5)]
        )
        self.soh_gauge = GaugeWidget()
        gauge_row.add_widget(self.soh_gauge)

        # 关键指标卡片
        key_card = RoundedCard(
            size_hint_x=0.6,
            padding=dp(10),
            spacing=dp(4)
        )
        self.metric_voltage = MetricLabel("总电压", "-- V")
        self.metric_current = MetricLabel("电流", "-- A")
        self.metric_temp = MetricLabel("电池温度", "-- °C")
        self.metric_capacity = MetricLabel("当前电量", "-- %")
        self.metric_charge = MetricLabel("满充容量", "-- Ah")
        self.metric_cycle = MetricLabel("循环次数", "--")
        self.metric_soh = MetricLabel("健康度(SOH)", "-- %",
                                      color=COLORS['accent_green'])

        key_card.add_widget(self.metric_voltage)
        key_card.add_widget(self.metric_current)
        key_card.add_widget(self.metric_temp)
        key_card.add_widget(self.metric_capacity)
        key_card.add_widget(self.metric_charge)
        key_card.add_widget(self.metric_cycle)
        key_card.add_widget(self.metric_soh)

        gauge_row.add_widget(key_card)
        layout.add_widget(gauge_row)

        # 状态摘要卡片
        status_card = RoundedCard(
            size_hint_y=None,
            height=dp(100),
            padding=dp(10),
            spacing=dp(6)
        )
        status_title = Label(
            text="电池状态摘要",
            color=COLORS['text_primary'],
            font_size=sp(14),
            bold=True,
            size_hint_y=None,
            height=dp(22),
            halign='left',
            valign='middle',
        )
        status_title.bind(size=status_title.setter('text_size'))
        self.status_label = Label(
            text="正在获取数据...",
            color=COLORS['text_secondary'],
            font_size=sp(12),
            size_hint_y=None,
            height=dp(60),
            halign='left',
            valign='top',
        )
        self.status_label.bind(size=self.status_label.setter('text_size'))
        status_card.add_widget(status_title)
        status_card.add_widget(self.status_label)
        layout.add_widget(status_card)

        # 剩余空间
        layout.add_widget(Widget())

        self.add_widget(layout)

    def update_data(self, data, analysis):
        """更新仪表盘数据"""
        # 更新SOH仪表盘
        soh_str = data.get("电池健康度(SOH)", "N/A")
        try:
            soh = float(soh_str.replace("%", ""))
            self.soh_gauge.set_value(soh, 100, "健康度", "%")
        except (ValueError, AttributeError):
            self.soh_gauge.set_value(0, 100, "N/A", "")

        # 更新状态徽章
        grade = analysis.get("overall_grade", "未知")
        self.status_badge.text = grade
        if "A" in str(grade):
            self.status_badge.bg_color = COLORS['accent_green']
        elif "B" in str(grade):
            self.status_badge.bg_color = COLORS['primary']
        elif "C" in str(grade):
            self.status_badge.bg_color = COLORS['accent_yellow']
        elif "D" in str(grade):
            self.status_badge.bg_color = COLORS['accent_orange']
        else:
            self.status_badge.bg_color = COLORS['accent_red']

        # 更新关键指标
        self.metric_voltage.update_value(data.get("总电压", "--"))
        self.metric_current.update_value(data.get("电流", "--"))
        self.metric_temp.update_value(data.get("电池温度", "--"))
        self.metric_capacity.update_value(data.get("当前电量", "--"))
        self.metric_charge.update_value(data.get("当前满充容量", "--"))
        self.metric_cycle.update_value(data.get("循环次数", "--"))

        soh_val = data.get("电池健康度(SOH)", "--")
        soh_color = COLORS['accent_green']
        try:
            s = float(soh_val.replace("%", ""))
            if s < 80:
                soh_color = COLORS['accent_red']
            elif s < 90:
                soh_color = COLORS['accent_yellow']
        except (ValueError, AttributeError):
            pass
        self.metric_soh.update_value(soh_val, soh_color)

        # 更新状态摘要
        desc = analysis.get("soh_description", "")
        grade_text = analysis.get("overall_grade", "")
        score = analysis.get("overall_score", "--")
        self.status_label.text = (
            f"综合评分: {score}/100  等级: {grade_text}\n\n{desc}"
        )


class DetailTab(TabbedPanelItem):
    """电池详情标签页"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.text = "电池详情"
        self._build_ui()

    def _build_ui(self):
        scroll = ScrollView(do_scroll_x=False, do_scroll_y=True)
        self.layout = BoxLayout(
            orientation='vertical',
            padding=dp(12),
            spacing=dp(10),
            size_hint_y=None,
        )
        self.layout.bind(minimum_height=self.layout.setter('height'))

        scroll.add_widget(self.layout)
        self.add_widget(scroll)

    def update_data(self, data, analysis):
        """更新详情数据"""
        self.layout.clear_widgets()

        # 基本信息卡片
        self._add_section("基本信息", [
            ("电池制造商", data.get("电池制造商", "--")),
            ("电池型号", data.get("电池型号", "--")),
            ("电池类型", data.get("电池类型", "--")),
            ("电池序列号", data.get("电池序列号", "--")),
            ("数据采集时间", data.get("采集时间", "--")),
            ("数据源", data.get("数据源", "--")),
        ])

        # 电压电流信息
        self._add_section("电气参数", [
            ("总电压", data.get("总电压", "--")),
            ("电流", data.get("电流", "--")),
            ("电池温度", data.get("电池温度", "--")),
            ("电池内阻", data.get("电池内阻", "--")),
            ("绝缘电阻", data.get("绝缘电阻", "--")),
        ])

        # 容量信息
        self._add_section("容量信息", [
            ("当前电量", data.get("当前电量", "--")),
            ("当前满充容量", data.get("当前满充容量", "--")),
            ("设计容量", data.get("设计容量", "--")),
            ("容量衰减", data.get("容量衰减", "--")),
            ("可用电量", data.get("可用电量", "--")),
            ("总电量", data.get("总电量", "--")),
        ])

        # 电芯信息
        cell_count = data.get("电芯数量", "--")
        if cell_count != "--" and cell_count != "N/A":
            cells = data.get("_cells", [])
            cell_items = [
                ("电芯数量", cell_count),
                ("最高电芯电压", data.get("最高电芯电压", "--")),
                ("最低电芯电压", data.get("最低电芯电压", "--")),
                ("电芯压差", data.get("电芯压差", "--")),
            ]
            if cells:
                for i, v in enumerate(cells):
                    cell_items.append((f"电芯#{i+1} 电压", f"{v:.3f}V"))
            self._add_section("电芯信息", cell_items)

        # 充放电信息
        self._add_section("充放电状态", [
            ("电池健康状态", data.get("电池健康状态", "--")),
            ("充放电状态", data.get("充放电状态", "--")),
            ("充电功率限制", data.get("充电功率限制", "--")),
            ("放电功率限制", data.get("放电功率限制", "--")),
            ("循环次数", data.get("循环次数", "--")),
        ])

        # 分析数据
        self._add_section("电池分析", [
            ("SOH健康度", data.get("电池健康度(SOH)", "--")),
            ("SOH等级", analysis.get("soh_grade", "--")),
            ("综合评分", f"{analysis.get('overall_score', '--')}/100"),
            ("综合等级", analysis.get("overall_grade", "--")),
            ("内阻等级", analysis.get("resistance_grade", "--")),
            ("电芯均衡等级", analysis.get("cell_balance_grade", "--")),
            ("循环寿命阶段", analysis.get("cycle_grade", "--")),
        ])

        # 添加间隔
        spacer = Widget(size_hint_y=None, height=dp(20))
        self.layout.add_widget(spacer)

    def _add_section(self, title, items):
        """添加一个数据分区"""
        card = RoundedCard(
            size_hint_y=None,
            height=dp(36 + len(items) * 32),
            padding=dp(10),
            spacing=dp(4)
        )

        section_title = Label(
            text=title,
            color=COLORS['primary_light'],
            font_size=sp(14),
            bold=True,
            size_hint_y=None,
            height=dp(24),
            halign='left',
            valign='middle',
        )
        section_title.bind(size=section_title.setter('text_size'))
        card.add_widget(section_title)

        for label, value in items:
            if value is not None and value != "N/A":
                metric = MetricLabel(label, str(value))
                card.add_widget(metric)

        self.layout.add_widget(card)


class CellTab(TabbedPanelItem):
    """电芯详情标签页"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.text = "电芯详情"
        self._build_ui()

    def _build_ui(self):
        scroll = ScrollView(do_scroll_x=False, do_scroll_y=True)
        self.layout = BoxLayout(
            orientation='vertical',
            padding=dp(12),
            spacing=dp(10),
            size_hint_y=None,
        )
        self.layout.bind(minimum_height=self.layout.setter('height'))
        scroll.add_widget(self.layout)
        self.add_widget(scroll)

    def update_data(self, data, analysis):
        """更新电芯详情"""
        self.layout.clear_widgets()

        cells = data.get("_cells", [])
        if not cells:
            no_data = Label(
                text="暂无电芯详细数据\n\n请确认BMS数据源是否可用",
                color=COLORS['text_muted'],
                font_size=sp(14),
                halign='center',
                valign='middle',
                size_hint_y=None,
                height=dp(100),
            )
            self.layout.add_widget(no_data)
            return

        # 电芯概览
        overview_card = RoundedCard(
            size_hint_y=None,
            height=dp(140),
            padding=dp(10),
            spacing=dp(6)
        )
        overview_title = Label(
            text="电芯概览",
            color=COLORS['primary_light'],
            font_size=sp(14),
            bold=True,
            size_hint_y=None,
            height=dp(24),
            halign='left',
            valign='middle',
        )
        overview_title.bind(size=overview_title.setter('text_size'))
        overview_card.add_widget(overview_title)

        if cells:
            max_v = max(cells)
            min_v = min(cells)
            avg_v = sum(cells) / len(cells)
            diff_v = (max_v - min_v) * 1000  # mV

            items = [
                ("电芯数量", str(len(cells))),
                ("最高电压", f"{max_v:.3f}V"),
                ("最低电压", f"{min_v:.3f}V"),
                ("平均电压", f"{avg_v:.3f}V"),
                ("电芯压差", f"{diff_v:.1f}mV"),
            ]

            for label, value in items:
                metric = MetricLabel(label, value)
                overview_card.add_widget(metric)

        self.layout.add_widget(overview_card)

        # 电芯电压分布图
        chart_card = RoundedCard(
            size_hint_y=None,
            height=dp(40 + max(len(cells) * 20, 100)),
            padding=dp(10),
            spacing=dp(4)
        )
        chart_title = Label(
            text="电芯电压分布",
            color=COLORS['primary_light'],
            font_size=sp(14),
            bold=True,
            size_hint_y=None,
            height=dp(24),
            halign='left',
            valign='middle',
        )
        chart_title.bind(size=chart_title.setter('text_size'))
        chart_card.add_widget(chart_title)

        # 电芯电压条形图
        min_v = min(cells)
        max_v = max(cells)
        v_range = max_v - min_v if max_v > min_v else 0.1

        for i, v in enumerate(cells):
            bar_row = BoxLayout(
                orientation='horizontal',
                size_hint_y=None,
                height=dp(22),
                spacing=dp(4)
            )

            cell_label = Label(
                text=f"#{i+1}",
                color=COLORS['text_secondary'],
                font_size=sp(10),
                size_hint_x=0.08,
                halign='right',
                valign='middle',
            )
            cell_label.bind(size=cell_label.setter('text_size'))

            # 电压条
            bar_container = BoxLayout(
                orientation='horizontal',
                size_hint_x=0.7,
                padding=[0, dp(4)]
            )
            bar_width = (v - min_v) / v_range * 0.8 + 0.2
            bar = Widget(size_hint_x=bar_width)

            # 颜色：接近最高为绿，接近最低为红
            if v_range > 0:
                ratio = (v - min_v) / v_range
                if ratio > 0.8:
                    bar_color = COLORS['accent_green']
                elif ratio > 0.5:
                    bar_color = COLORS['primary']
                elif ratio > 0.3:
                    bar_color = COLORS['accent_yellow']
                else:
                    bar_color = COLORS['accent_red']
            else:
                bar_color = COLORS['accent_green']

            with bar.canvas.before:
                Color(*bar_color)
                bar.rect = RoundedRectangle(
                    pos=bar.pos, size=bar.size, radius=[dp(3)]
                )
            bar.bind(pos=self._update_bar_rect, size=self._update_bar_rect)

            bar_container.add_widget(bar)
            bar_container.add_widget(Widget())  # spacer

            value_label = Label(
                text=f"{v:.3f}V",
                color=COLORS['text_primary'],
                font_size=sp(10),
                size_hint_x=0.22,
                halign='left',
                valign='middle',
            )
            value_label.bind(size=value_label.setter('text_size'))

            bar_row.add_widget(cell_label)
            bar_row.add_widget(bar_container)
            bar_row.add_widget(value_label)
            chart_card.add_widget(bar_row)

        self.layout.add_widget(chart_card)

        # 电芯均衡状态
        diff_mv = (max_v - min_v) * 1000
        balance_card = RoundedCard(
            size_hint_y=None,
            height=dp(100),
            padding=dp(10),
            spacing=dp(6)
        )
        balance_title = Label(
            text="均衡状态评估",
            color=COLORS['primary_light'],
            font_size=sp(14),
            bold=True,
            size_hint_y=None,
            height=dp(24),
            halign='left',
            valign='middle',
        )
        balance_title.bind(size=balance_title.setter('text_size'))
        balance_card.add_widget(balance_title)

        if diff_mv < 5:
            balance_text = "电芯一致性极佳，BMS均衡系统工作正常"
            balance_color = COLORS['accent_green']
        elif diff_mv < 10:
            balance_text = "电芯一致性良好，在正常范围内"
            balance_color = COLORS['primary']
        elif diff_mv < 30:
            balance_text = "存在一定压差，建议慢充均衡"
            balance_color = COLORS['accent_yellow']
        elif diff_mv < 50:
            balance_text = "压差较大，续航可能受影响"
            balance_color = COLORS['accent_orange']
        else:
            balance_text = "电芯严重不均衡，需要专业检测！"
            balance_color = COLORS['accent_red']

        balance_label = Label(
            text=balance_text,
            color=balance_color,
            font_size=sp(12),
            size_hint_y=None,
            height=dp(50),
            halign='left',
            valign='top',
        )
        balance_label.bind(size=balance_label.setter('text_size'))
        balance_card.add_widget(balance_label)
        self.layout.add_widget(balance_card)

        spacer = Widget(size_hint_y=None, height=dp(20))
        self.layout.add_widget(spacer)

    def _update_bar_rect(self, instance, value):
        if hasattr(instance, 'rect'):
            instance.rect.pos = instance.pos
            instance.rect.size = instance.size


class HealthTab(TabbedPanelItem):
    """健康分析标签页"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.text = "健康分析"
        self._build_ui()

    def _build_ui(self):
        scroll = ScrollView(do_scroll_x=False, do_scroll_y=True)
        self.layout = BoxLayout(
            orientation='vertical',
            padding=dp(12),
            spacing=dp(10),
            size_hint_y=None,
        )
        self.layout.bind(minimum_height=self.layout.setter('height'))
        scroll.add_widget(self.layout)
        self.add_widget(scroll)

    def update_data(self, data, analysis):
        """更新健康分析"""
        self.layout.clear_widgets()

        # 综合评分大卡片
        score_card = RoundedCard(
            size_hint_y=None,
            height=dp(120),
            padding=dp(15),
            spacing=dp(6)
        )
        score_layout = BoxLayout(orientation='horizontal', spacing=dp(15))

        # 评分显示
        score_box = BoxLayout(
            orientation='vertical',
            size_hint_x=0.4,
            spacing=dp(4)
        )
        score = analysis.get("overall_score", "--")
        grade = analysis.get("overall_grade", "--")

        score_label = Label(
            text=str(score),
            color=COLORS['primary_light'],
            font_size=sp(42),
            bold=True,
            halign='center',
            valign='middle',
        )
        score_label.bind(size=score_label.setter('text_size'))

        score_max = Label(
            text="/100",
            color=COLORS['text_muted'],
            font_size=sp(14),
            halign='center',
            valign='middle',
        )
        score_max.bind(size=score_max.setter('text_size'))

        grade_label = Label(
            text=f"等级: {grade}",
            color=COLORS['text_primary'],
            font_size=sp(14),
            bold=True,
            halign='center',
            valign='middle',
        )
        grade_label.bind(size=grade_label.setter('text_size'))

        score_box.add_widget(Widget())
        score_box.add_widget(score_label)
        score_box.add_widget(score_max)
        score_box.add_widget(grade_label)
        score_box.add_widget(Widget())

        score_layout.add_widget(score_box)

        # 评分详情
        detail_box = BoxLayout(
            orientation='vertical',
            size_hint_x=0.6,
            spacing=dp(4)
        )
        detail_items = [
            ("SOH健康度", analysis.get("soh_grade", "--")),
            ("内阻状态", analysis.get("resistance_grade", "--")),
            ("电芯一致性", analysis.get("cell_balance_grade", "--")),
            ("循环寿命", analysis.get("cycle_grade", "--")),
        ]
        for label, value in detail_items:
            detail_row = BoxLayout(
                orientation='horizontal',
                size_hint_y=None,
                height=dp(24),
                spacing=dp(4)
            )
            dl = Label(
                text=label,
                color=COLORS['text_secondary'],
                font_size=sp(12),
                size_hint_x=0.45,
                halign='left',
                valign='middle',
            )
            dl.bind(size=dl.setter('text_size'))
            dv = Label(
                text=str(value),
                color=COLORS['text_primary'],
                font_size=sp(12),
                bold=True,
                size_hint_x=0.55,
                halign='right',
                valign='middle',
            )
            dv.bind(size=dv.setter('text_size'))
            detail_row.add_widget(dl)
            detail_row.add_widget(dv)
            detail_box.add_widget(detail_row)

        score_layout.add_widget(detail_box)
        score_card.add_widget(score_layout)
        self.layout.add_widget(score_card)

        # SOH详细分析
        self._add_analysis_card("SOH 健康度分析", [
            f"当前SOH: {data.get('电池健康度(SOH)', '--')}",
            f"等级: {analysis.get('soh_grade', '--')}",
            analysis.get('soh_description', ''),
        ])

        # 容量衰减分析
        cap_items = []
        retention = analysis.get("capacity_retention")
        if retention is not None:
            cap_items.append(f"容量保持率: {retention}%")
        degradation = analysis.get("capacity_degradation_pct")
        if degradation is not None:
            cap_items.append(f"容量衰减: {degradation}%")
        loss = analysis.get("capacity_loss_ah")
        if loss is not None:
            cap_items.append(f"容量损失: {loss}Ah")
        if cap_items:
            self._add_analysis_card("容量衰减分析", cap_items)

        # 内阻分析
        resistance = analysis.get("resistance_mohm")
        if resistance is not None:
            self._add_analysis_card("内阻分析", [
                f"当前内阻: {resistance}mΩ",
                f"等级: {analysis.get('resistance_grade', '--')}",
                f"估算增长率: {analysis.get('resistance_increase_est', '--')}",
                analysis.get('resistance_desc', ''),
            ])

        # 循环寿命
        cycle_items = []
        current_cycles = analysis.get("current_cycles")
        if current_cycles is not None:
            cycle_items.append(f"当前循环次数: {current_cycles}")
        max_cycles = analysis.get("estimated_max_cycles")
        if max_cycles is not None:
            cycle_items.append(f"设计循环寿命: {max_cycles}次")
        remaining = analysis.get("remaining_cycles")
        if remaining is not None:
            cycle_items.append(f"剩余循环次数: {remaining}次")
        if cycle_items:
            cycle_items.append(f"阶段: {analysis.get('cycle_grade', '--')}")
            cycle_items.append(analysis.get('cycle_desc', ''))
            self._add_analysis_card("循环寿命分析", cycle_items)

        # 日历寿命
        self._add_analysis_card("日历寿命分析", [
            f"设计日历寿命: {analysis.get('calendar_life_years', '--')}年",
            f"估算已使用: {analysis.get('estimated_age_years', '--')}年",
            f"估算剩余: {analysis.get('remaining_years', '--')}年",
            analysis.get('calendar_life_note', ''),
        ])

        # 保养建议
        recommendations = analysis.get("recommendations", [])
        if recommendations:
            rec_text = "\n".join([f"• {r}" for r in recommendations])
            self._add_analysis_card("保养建议", [rec_text])

        spacer = Widget(size_hint_y=None, height=dp(20))
        self.layout.add_widget(spacer)

    def _add_analysis_card(self, title, items):
        """添加分析卡片"""
        card = RoundedCard(
            size_hint_y=None,
            height=dp(40 + len(items) * 24),
            padding=dp(10),
            spacing=dp(4)
        )
        section_title = Label(
            text=title,
            color=COLORS['primary_light'],
            font_size=sp(14),
            bold=True,
            size_hint_y=None,
            height=dp(24),
            halign='left',
            valign='middle',
        )
        section_title.bind(size=section_title.setter('text_size'))
        card.add_widget(section_title)

        for item in items:
            item_label = Label(
                text=str(item),
                color=COLORS['text_secondary'],
                font_size=sp(12),
                size_hint_y=None,
                height=dp(22),
                halign='left',
                valign='top',
            )
            item_label.bind(size=item_label.setter('text_size'))
            card.add_widget(item_label)

        self.layout.add_widget(card)


class HistoryTab(TabbedPanelItem):
    """历史记录标签页"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.text = "历史记录"
        self._build_ui()

    def _build_ui(self):
        scroll = ScrollView(do_scroll_x=False, do_scroll_y=True)
        self.layout = BoxLayout(
            orientation='vertical',
            padding=dp(12),
            spacing=dp(10),
            size_hint_y=None,
        )
        self.layout.bind(minimum_height=self.layout.setter('height'))
        scroll.add_widget(self.layout)
        self.add_widget(scroll)

    def update_data(self, data, analysis):
        """更新历史记录"""
        self.layout.clear_widgets()

        # 当前数据摘要
        summary_card = RoundedCard(
            size_hint_y=None,
            height=dp(120),
            padding=dp(10),
            spacing=dp(6)
        )
        title = Label(
            text="当前检测结果",
            color=COLORS['primary_light'],
            font_size=sp(14),
            bold=True,
            size_hint_y=None,
            height=dp(24),
            halign='left',
            valign='middle',
        )
        title.bind(size=title.setter('text_size'))
        summary_card.add_widget(title)

        summary_items = [
            f"检测时间: {data.get('采集时间', '--')}",
            f"SOH: {data.get('电池健康度(SOH)', '--')}",
            f"综合评分: {analysis.get('overall_score', '--')}/100",
            f"综合等级: {analysis.get('overall_grade', '--')}",
        ]
        for item in summary_items:
            item_label = Label(
                text=item,
                color=COLORS['text_secondary'],
                font_size=sp(12),
                size_hint_y=None,
                height=dp(22),
                halign='left',
                valign='middle',
            )
            item_label.bind(size=item_label.setter('text_size'))
            summary_card.add_widget(item_label)

        self.layout.add_widget(summary_card)

        # 导出/刷新按钮
        btn_layout = BoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(40),
            spacing=dp(10)
        )
        save_btn = Button(
            text="保存检测记录",
            background_color=COLORS['primary'],
            color=COLORS['white'],
            font_size=sp(13),
            size_hint_x=0.5,
        )
        save_btn.bind(on_release=self._save_record)
        export_btn = Button(
            text="导出数据",
            background_color=COLORS['bg_card2'],
            color=COLORS['text_primary'],
            font_size=sp(13),
            size_hint_x=0.5,
        )
        export_btn.bind(on_release=self._export_data)
        btn_layout.add_widget(save_btn)
        btn_layout.add_widget(export_btn)
        self.layout.add_widget(btn_layout)

        # 操作说明
        info_card = RoundedCard(
            size_hint_y=None,
            height=dp(100),
            padding=dp(10),
            spacing=dp(6)
        )
        info_title = Label(
            text="使用说明",
            color=COLORS['primary_light'],
            font_size=sp(14),
            bold=True,
            size_hint_y=None,
            height=dp(24),
            halign='left',
            valign='middle',
        )
        info_title.bind(size=info_title.setter('text_size'))
        info_card.add_widget(info_title)

        info_text = Label(
            text=(
                "• 本应用通过ADB权限读取BMS电池管理系统数据\n"
                "• 检测数据仅供参考，不代表官方检测结果\n"
                "• 建议定期记录数据以追踪电池衰减趋势\n"
                "• 如需专业检测，请联系比亚迪授权服务中心"
            ),
            color=COLORS['text_muted'],
            font_size=sp(11),
            size_hint_y=None,
            height=dp(70),
            halign='left',
            valign='top',
        )
        info_text.bind(size=info_text.setter('text_size'))
        info_card.add_widget(info_text)
        self.layout.add_widget(info_card)

        spacer = Widget(size_hint_y=None, height=dp(20))
        self.layout.add_widget(spacer)

    def _save_record(self, instance):
        """保存记录"""
        app = App.get_running_app()
        data = app.current_data
        analysis = app.current_analysis

        save_text = "检测记录已保存到本地存储"
        if data:
            try:
                # 保存到本地
                save_path = "/sdcard/byd_battery_records.txt"
                with open(save_path, "a", encoding="utf-8") as f:
                    f.write(f"\n=== {data.get('采集时间', '--')} ===\n")
                    f.write(f"SOH: {data.get('电池健康度(SOH)', '--')}\n")
                    f.write(f"电压: {data.get('总电压', '--')}\n")
                    f.write(f"电流: {data.get('电流', '--')}\n")
                    f.write(f"温度: {data.get('电池温度', '--')}\n")
                    f.write(f"循环次数: {data.get('循环次数', '--')}\n")
                    f.write(f"综合评分: {analysis.get('overall_score', '--')}/100\n")
                    f.write(f"综合等级: {analysis.get('overall_grade', '--')}\n")
                save_text = f"记录已保存到:\n{save_path}"
            except Exception as e:
                save_text = f"保存失败: {str(e)}"

        popup = Popup(
            title="保存记录",
            content=Label(
                text=save_text,
                color=COLORS['text_primary'],
                font_size=sp(14),
                size_hint_y=None,
                height=dp(80),
                halign='center',
                valign='middle',
            ),
            size_hint=(0.7, 0.3),
            background_color=COLORS['bg_card'],
            title_color=COLORS['text_primary'],
        )
        popup.open()

    def _export_data(self, instance):
        """导出数据"""
        app = App.get_running_app()
        data = app.current_data
        analysis = app.current_analysis

        export_text = "数据导出功能开发中...\n请稍后重试"
        if data:
            try:
                import json
                export_data = {
                    "app": "比亚迪电池检测",
                    "version": "1.0.0",
                    "raw_data": {k: v for k, v in data.items() if not k.startswith('_')},
                    "analysis": analysis,
                }
                save_path = "/sdcard/byd_battery_export.json"
                with open(save_path, "w", encoding="utf-8") as f:
                    json.dump(export_data, f, ensure_ascii=False, indent=2)
                export_text = f"数据已导出到:\n{save_path}"
            except Exception as e:
                export_text = f"导出失败: {str(e)}"

        popup = Popup(
            title="导出数据",
            content=Label(
                text=export_text,
                color=COLORS['text_primary'],
                font_size=sp(14),
                size_hint_y=None,
                height=dp(80),
                halign='center',
                valign='middle',
            ),
            size_hint=(0.7, 0.3),
            background_color=COLORS['bg_card'],
            title_color=COLORS['text_primary'],
        )
        popup.open()


class MainPanel(TabbedPanel):
    """主面板"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.do_default_tab = False
        self.tab_width = dp(80)
        self.background_color = COLORS['bg_dark']
        self.default_tab_text_color = COLORS['text_secondary']
        self.tab_text_color = COLORS['text_primary']

        self.dashboard_tab = DashboardTab()
        self.detail_tab = DetailTab()
        self.cell_tab = CellTab()
        self.health_tab = HealthTab()
        self.history_tab = HistoryTab()

        self.add_widget(self.dashboard_tab)
        self.add_widget(self.detail_tab)
        self.add_widget(self.cell_tab)
        self.add_widget(self.health_tab)
        self.add_widget(self.history_tab)

        self.default_tab = self.dashboard_tab


class BatteryDetectionApp(App):
    """比亚迪电池检测应用"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.reader = BMSReader()
        self.analyzer = BatteryAnalyzer()
        self.current_data = {}
        self.current_analysis = {}
        self.is_reading = False
        self.refresh_interval = 5  # 刷新间隔(秒)

        # 设置历史数据存储路径
        try:
            from android.storage import app_storage_path
            storage_path = app_storage_path()
            self.analyzer.set_history_file(
                os.path.join(storage_path, "battery_history.json")
            )
        except ImportError:
            self.analyzer.set_history_file("battery_history.json")

    def build(self):
        self.title = "比亚迪电池检测"
        self.icon = "icon.png"

        # 设置窗口背景
        Window.clearcolor = COLORS['bg_dark']

        self.main_panel = MainPanel()

        # 启动数据刷新
        Clock.schedule_interval(self._refresh_data, self.refresh_interval)
        # 立即执行一次
        Clock.schedule_once(lambda dt: self._refresh_data(0), 0.5)

        return self.main_panel

    def _refresh_data(self, dt):
        """刷新数据"""
        if self.is_reading:
            return
        self.is_reading = True

        def do_read():
            try:
                data = self.reader.get_comprehensive_data()
                analysis = self.analyzer.analyze_battery_health(data)
                self.current_data = data
                self.current_analysis = analysis

                # 保存历史
                self.analyzer.save_history(data)

                # 在主线程更新UI
                Clock.schedule_once(lambda dt: self._update_ui(data, analysis), 0)
            except Exception as e:
                Clock.schedule_once(
                    lambda dt, err=str(e): self._show_error(err), 0
                )
            finally:
                self.is_reading = False

        threading.Thread(target=do_read, daemon=True).start()

    def _update_ui(self, data, analysis):
        """更新所有UI"""
        self.main_panel.dashboard_tab.update_data(data, analysis)
        self.main_panel.detail_tab.update_data(data, analysis)
        self.main_panel.cell_tab.update_data(data, analysis)
        self.main_panel.health_tab.update_data(data, analysis)
        self.main_panel.history_tab.update_data(data, analysis)

    def _show_error(self, error_msg):
        """显示错误"""
        print(f"数据读取错误: {error_msg}")

    def on_pause(self):
        return True

    def on_resume(self):
        pass


if __name__ == '__main__':
    BatteryDetectionApp().run()