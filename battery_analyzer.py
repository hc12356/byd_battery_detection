# -*- coding: utf-8 -*-
"""
比亚迪电池分析计算模块
计算电池寿命、循环寿命、SOH、SOC等关键指标
"""

import math
import json
import os
import time
from datetime import datetime
from collections import deque


class BatteryAnalyzer:
    """电池寿命分析计算器"""

    # 比亚迪刀片电池(LiFePO4)参数
    LFP_NOMINAL_VOLTAGE = 3.2       # 标称电压 (V)
    LFP_MAX_VOLTAGE = 3.65          # 最高电压 (V)
    LFP_MIN_VOLTAGE = 2.5           # 最低电压 (V)
    LFP_CYCLE_LIFE = 3000           # 典型循环寿命 (80%容量)
    LFP_CALENDAR_LIFE = 8           # 日历寿命 (年)

    # 三元锂电池(NCM)参数
    NCM_NOMINAL_VOLTAGE = 3.7
    NCM_MAX_VOLTAGE = 4.2
    NCM_MIN_VOLTAGE = 2.8
    NCM_CYCLE_LIFE = 1500
    NCM_CALENDAR_LIFE = 8

    def __init__(self):
        self.history_file = None
        self.history = []
        self.max_history = 100

    def set_history_file(self, path):
        """设置历史数据文件路径"""
        self.history_file = path
        self._load_history()

    def _load_history(self):
        """加载历史数据"""
        if self.history_file and os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r') as f:
                    self.history = json.load(f)
                if len(self.history) > self.max_history:
                    self.history = self.history[-self.max_history:]
            except (json.JSONDecodeError, IOError):
                self.history = []

    def save_history(self, data):
        """保存历史数据"""
        if not self.history_file:
            return
        self.history.append({
            "timestamp": datetime.now().isoformat(),
            "data": data
        })
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]
        try:
            os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
            with open(self.history_file, 'w') as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
        except IOError:
            pass

    def analyze_battery_health(self, data):
        """综合分析电池健康状态"""
        analysis = {}

        # 1. SOH分析
        soh = self._extract_soh(data)
        analysis["soh"] = soh
        analysis["soh_grade"] = self._grade_soh(soh)
        analysis["soh_description"] = self._describe_soh(soh)

        # 2. 容量衰减分析
        capacity_analysis = self._analyze_capacity(data)
        analysis.update(capacity_analysis)

        # 3. 内阻分析
        resistance_analysis = self._analyze_resistance(data)
        analysis.update(resistance_analysis)

        # 4. 电芯一致性分析
        cell_analysis = self._analyze_cell_consistency(data)
        analysis.update(cell_analysis)

        # 5. 循环寿命分析
        cycle_analysis = self._analyze_cycle_life(data)
        analysis.update(cycle_analysis)

        # 6. 日历寿命分析
        calendar_analysis = self._analyze_calendar_life(data)
        analysis.update(calendar_analysis)

        # 7. 综合评分
        analysis["overall_score"] = self._calculate_overall_score(analysis)
        analysis["overall_grade"] = self._grade_overall(analysis["overall_score"])

        # 8. 建议
        analysis["recommendations"] = self._generate_recommendations(analysis)

        return analysis

    def _extract_soh(self, data):
        """从数据中提取SOH"""
        soh_str = data.get("电池健康度(SOH)", "N/A")
        if soh_str != "N/A":
            try:
                return float(soh_str.replace("%", ""))
            except ValueError:
                pass
        return None

    def _grade_soh(self, soh):
        """SOH等级评定"""
        if soh is None:
            return "未知"
        if soh >= 95:
            return "优秀"
        elif soh >= 90:
            return "良好"
        elif soh >= 85:
            return "一般"
        elif soh >= 80:
            return "需关注"
        elif soh >= 70:
            return "较差"
        else:
            return "严重衰减"

    def _describe_soh(self, soh):
        """SOH详细描述"""
        if soh is None:
            return "无法获取SOH数据"
        if soh >= 95:
            return "电池状态极佳，容量保持率优秀，无明显衰减迹象"
        elif soh >= 90:
            return "电池状态良好，容量略有衰减，属于正常老化范围"
        elif soh >= 85:
            return "电池有一定程度衰减，但仍可正常使用，建议定期检测"
        elif soh >= 80:
            return "电池衰减较为明显，续航里程已有明显下降，建议关注"
        elif soh >= 70:
            return "电池衰减严重，续航大幅下降，建议考虑维修或更换"
        else:
            return "电池已严重老化，强烈建议更换电池"

    def _analyze_capacity(self, data):
        """容量分析"""
        analysis = {}

        charge_full_str = data.get("当前满充容量", "N/A")
        charge_design_str = data.get("设计容量", "N/A")

        charge_full = None
        charge_design = None
        try:
            if charge_full_str != "N/A":
                charge_full = float(charge_full_str.replace("Ah", ""))
        except ValueError:
            pass
        try:
            if charge_design_str != "N/A":
                charge_design = float(charge_design_str.replace("Ah", ""))
        except ValueError:
            pass

        if charge_full and charge_design:
            degradation_pct = (1 - charge_full / charge_design) * 100
            analysis["capacity_retention"] = round(charge_full / charge_design * 100, 2)
            analysis["capacity_degradation_pct"] = round(degradation_pct, 2)
            analysis["capacity_loss_ah"] = round(charge_design - charge_full, 2)

            # 估算剩余可用容量
            analysis["charge_full_ah"] = charge_full
            analysis["charge_design_ah"] = charge_design

        return analysis

    def _analyze_resistance(self, data):
        """内阻分析"""
        analysis = {}
        resistance_str = data.get("电池内阻", "N/A")
        if resistance_str != "N/A":
            try:
                resistance = float(resistance_str.replace("mΩ", ""))
                analysis["resistance_mohm"] = resistance

                if resistance < 5:
                    analysis["resistance_grade"] = "优秀"
                    analysis["resistance_desc"] = "内阻极低，电池状态极佳"
                elif resistance < 10:
                    analysis["resistance_grade"] = "良好"
                    analysis["resistance_desc"] = "内阻正常，电池性能良好"
                elif resistance < 20:
                    analysis["resistance_grade"] = "一般"
                    analysis["resistance_desc"] = "内阻偏高，注意电池老化趋势"
                elif resistance < 50:
                    analysis["resistance_grade"] = "较差"
                    analysis["resistance_desc"] = "内阻明显升高，电池老化明显"
                else:
                    analysis["resistance_grade"] = "严重"
                    analysis["resistance_desc"] = "内阻过高，电池严重老化"

                # 估算内阻增长率
                if resistance < 5:
                    analysis["resistance_increase_est"] = "正常范围"
                elif resistance < 10:
                    analysis["resistance_increase_est"] = "约增长100%"
                elif resistance < 20:
                    analysis["resistance_increase_est"] = "约增长300%"
                else:
                    analysis["resistance_increase_est"] = "超过500%"
            except ValueError:
                pass
        return analysis

    def _analyze_cell_consistency(self, data):
        """电芯一致性分析"""
        analysis = {}
        cell_diff_str = data.get("电芯压差", "N/A")
        cell_count_str = data.get("电芯数量", "N/A")

        if cell_diff_str != "N/A":
            try:
                cell_diff = float(cell_diff_str.replace("mV", ""))
                analysis["cell_voltage_diff_mv"] = cell_diff

                if cell_diff < 5:
                    analysis["cell_balance_grade"] = "优秀"
                    analysis["cell_balance_desc"] = "电芯一致性极佳，BMS均衡良好"
                elif cell_diff < 10:
                    analysis["cell_balance_grade"] = "良好"
                    analysis["cell_balance_desc"] = "电芯一致性良好，属正常范围"
                elif cell_diff < 30:
                    analysis["cell_balance_grade"] = "一般"
                    analysis["cell_balance_desc"] = "电芯存在一定压差，建议关注"
                elif cell_diff < 50:
                    analysis["cell_balance_grade"] = "较差"
                    analysis["cell_balance_desc"] = "电芯压差较大，可能影响续航"
                elif cell_diff < 100:
                    analysis["cell_balance_grade"] = "差"
                    analysis["cell_balance_desc"] = "电芯严重不均衡，需要专业检测"
                else:
                    analysis["cell_balance_grade"] = "危险"
                    analysis["cell_balance_desc"] = "电芯压差过大，存在安全风险！"
            except ValueError:
                pass

        if cell_count_str != "N/A":
            try:
                analysis["cell_count"] = int(cell_count_str)
            except ValueError:
                pass

        return analysis

    def _analyze_cycle_life(self, data):
        """循环寿命分析"""
        analysis = {}
        cycle_str = data.get("循环次数", "N/A")
        soh = self._extract_soh(data)

        if cycle_str != "N/A":
            try:
                cycles = int(cycle_str)
                analysis["current_cycles"] = cycles

                # 根据电池类型设定总循环寿命
                battery_type = data.get("电池类型", "LiFePO4")
                if "LiFePO4" in str(battery_type) or "LFP" in str(battery_type).upper():
                    max_cycles = self.LFP_CYCLE_LIFE
                else:
                    max_cycles = self.NCM_CYCLE_LIFE

                analysis["estimated_max_cycles"] = max_cycles
                analysis["cycle_usage_pct"] = round(cycles / max_cycles * 100, 2)
                analysis["remaining_cycles"] = max_cycles - cycles

                if cycles < max_cycles * 0.3:
                    analysis["cycle_grade"] = "前期"
                    analysis["cycle_desc"] = "电池处于使用前期，循环寿命充裕"
                elif cycles < max_cycles * 0.6:
                    analysis["cycle_grade"] = "中期"
                    analysis["cycle_desc"] = "电池处于使用中期，性能稳定"
                elif cycles < max_cycles * 0.8:
                    analysis["cycle_grade"] = "中后期"
                    analysis["cycle_desc"] = "电池已使用较多循环，注意保养"
                elif cycles < max_cycles:
                    analysis["cycle_grade"] = "后期"
                    analysis["cycle_desc"] = "电池接近设计循环寿命，容量衰减明显"
                else:
                    analysis["cycle_grade"] = "超期"
                    analysis["cycle_desc"] = "已超过设计循环寿命，建议更换"

            except ValueError:
                pass
        elif soh is not None:
            # 根据SOH估算循环次数
            if soh >= 95:
                est_cycles = 0
            elif soh >= 90:
                est_cycles = int(self.LFP_CYCLE_LIFE * 0.1)
            elif soh >= 85:
                est_cycles = int(self.LFP_CYCLE_LIFE * 0.3)
            elif soh >= 80:
                est_cycles = int(self.LFP_CYCLE_LIFE * 0.5)
            elif soh >= 70:
                est_cycles = int(self.LFP_CYCLE_LIFE * 0.8)
            else:
                est_cycles = self.LFP_CYCLE_LIFE

            analysis["estimated_cycles"] = est_cycles
            analysis["cycle_est_note"] = "基于SOH估算"

        return analysis

    def _analyze_calendar_life(self, data):
        """日历寿命分析"""
        analysis = {}

        # 默认使用8年日历寿命（比亚迪刀片电池）
        calendar_life = self.LFP_CALENDAR_LIFE

        analysis["calendar_life_years"] = calendar_life
        analysis["calendar_life_note"] = (
            f"比亚迪刀片电池日历寿命约为{calendar_life}年，"
            "实际寿命受使用习惯、充放电频率、环境温度等因素影响"
        )

        soh = self._extract_soh(data)
        if soh is not None:
            # 估算已使用年限
            if soh >= 95:
                est_years = 0.5
            elif soh >= 90:
                est_years = 1.5
            elif soh >= 85:
                est_years = 3
            elif soh >= 80:
                est_years = 5
            elif soh >= 70:
                est_years = 7
            else:
                est_years = calendar_life

            analysis["estimated_age_years"] = est_years
            analysis["remaining_years"] = max(0, calendar_life - est_years)

        return analysis

    def _calculate_overall_score(self, analysis):
        """计算综合评分 (0-100)"""
        score = 100.0
        deductions = []

        # SOH扣分
        soh = analysis.get("soh")
        if soh is not None:
            if soh < 100:
                soh_deduction = (100 - soh) * 0.8
                deductions.append(("SOH衰减", soh_deduction))

        # 内阻扣分
        resistance = analysis.get("resistance_mohm")
        if resistance is not None:
            if resistance > 5:
                resistance_deduction = min((resistance - 5) * 2, 30)
                deductions.append(("内阻升高", resistance_deduction))

        # 电芯压差扣分
        cell_diff = analysis.get("cell_voltage_diff_mv")
        if cell_diff is not None:
            if cell_diff > 5:
                cell_deduction = min((cell_diff - 5) * 0.5, 25)
                deductions.append(("电芯不均衡", cell_deduction))

        # 循环次数扣分
        cycle_pct = analysis.get("cycle_usage_pct")
        if cycle_pct is not None:
            if cycle_pct > 10:
                cycle_deduction = min(cycle_pct * 0.3, 30)
                deductions.append(("循环使用", cycle_deduction))

        for _, deduction in deductions:
            score -= deduction

        return max(0, round(score, 1))

    def _grade_overall(self, score):
        """综合评分等级"""
        if score >= 90:
            return "A - 优秀"
        elif score >= 80:
            return "B - 良好"
        elif score >= 70:
            return "C - 一般"
        elif score >= 60:
            return "D - 需关注"
        else:
            return "E - 建议更换"

    def _generate_recommendations(self, analysis):
        """生成电池保养建议"""
        recommendations = []

        soh = analysis.get("soh")
        if soh is not None and soh < 85:
            recommendations.append("建议定期进行电池健康检测，关注容量衰减趋势")

        resistance = analysis.get("resistance_mohm")
        if resistance is not None and resistance > 15:
            recommendations.append("电池内阻偏高，建议避免大电流快充，减少急加速")

        cell_diff = analysis.get("cell_voltage_diff_mv")
        if cell_diff is not None and cell_diff > 20:
            recommendations.append("电芯存在一定压差，建议进行一次完整的慢充均衡")

        cycle_pct = analysis.get("cycle_usage_pct")
        if cycle_pct is not None and cycle_pct > 60:
            recommendations.append("电池已使用较多循环，建议避免深度放电(低于20%充电)")

        # 通用建议
        recommendations.append("保持电量在20%-80%之间，可延长电池寿命")
        recommendations.append("避免长时间高温暴晒，高温加速电池老化")
        recommendations.append("建议每月至少进行一次慢充(交流充电)")

        return recommendations

    def calculate_remaining_range(self, data, efficiency_wh_per_km=160):
        """估算剩余续航里程"""
        charge_full_str = data.get("当前满充容量", "N/A")
        capacity_str = data.get("当前电量", "N/A")
        voltage_str = data.get("总电压", "N/A")

        try:
            charge_full = float(charge_full_str.replace("Ah", "")) if charge_full_str != "N/A" else None
            capacity_pct = float(capacity_str.replace("%", "")) if capacity_str != "N/A" else None
            voltage = float(voltage_str.replace("V", "")) if voltage_str != "N/A" else None
        except (ValueError, AttributeError):
            return None

        if charge_full and capacity_pct and voltage:
            energy_kwh = charge_full * voltage / 1000.0
            available_kwh = energy_kwh * capacity_pct / 100.0
            range_km = available_kwh * 1000 / efficiency_wh_per_km
            return round(range_km, 1)

        return None

    def calculate_degradation_rate(self):
        """计算容量衰减速率"""
        if len(self.history) < 2:
            return None

        first = self.history[0]["data"]
        last = self.history[-1]["data"]

        first_time = datetime.fromisoformat(self.history[0]["timestamp"])
        last_time = datetime.fromisoformat(self.history[-1]["timestamp"])
        days = (last_time - first_time).days

        if days <= 0:
            return None

        try:
            first_soh = float(first.get("电池健康度(SOH)", "100%").replace("%", ""))
            last_soh = float(last.get("电池健康度(SOH)", "100%").replace("%", ""))
        except (ValueError, AttributeError):
            return None

        degradation = first_soh - last_soh
        rate_per_month = degradation / days * 30
        rate_per_year = degradation / days * 365

        return {
            "days_tracked": days,
            "total_degradation_pct": round(degradation, 2),
            "rate_per_month_pct": round(rate_per_month, 4),
            "rate_per_year_pct": round(rate_per_year, 2),
            "estimated_remaining_years": (
                round((last_soh - 70) / rate_per_year, 1) if rate_per_year > 0 else None
            ),
        }

    def get_charging_recommendation(self, data):
        """获取充电建议"""
        capacity_str = data.get("当前电量", "N/A")
        temp_str = data.get("电池温度", "N/A")

        try:
            capacity = float(capacity_str.replace("%", ""))
            temp = float(temp_str.replace("°C", ""))
        except (ValueError, AttributeError):
            return "无法获取充电建议"

        recommendations = []

        if capacity < 10:
            recommendations.append("电量过低，请尽快充电！")
        elif capacity < 20:
            recommendations.append("建议立即充电，避免深度放电")
        elif capacity > 85:
            recommendations.append("电量充足，无需充电")
            recommendations.append("如非长途需要，不建议充至100%")
        else:
            recommendations.append("电量正常，可根据需要充电")

        if temp < 0:
            recommendations.append("温度过低，建议先预热再快充")
        elif temp < 10:
            recommendations.append("低温环境，充电速度可能受限")
        elif temp > 40:
            recommendations.append("温度偏高，建议冷却后再充电")
        elif temp > 35:
            recommendations.append("注意电池温度，避免高温快充")

        return "\n".join(recommendations)