# -*- coding: utf-8 -*-
"""
比亚迪BMS数据读取模块
支持多种数据源：Android BatteryManager API、系统文件、CAN总线数据
"""

import os
import re
import time
import subprocess
from datetime import datetime
from collections import OrderedDict

# 尝试导入Pyjnius（Android专用）
try:
    from jnius import autoclass, cast
    HAS_JNIUS = True
except ImportError:
    HAS_JNIUS = False

# Android相关类
if HAS_JNIUS:
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    Context = autoclass('android.content.Context')
    BatteryManager = autoclass('android.os.BatteryManager')
    IntentFilter = autoclass('android.content.IntentFilter')
    Intent = autoclass('android.content.Intent')
    Build = autoclass('android.os.Build')
    Environment = autoclass('android.os.Environment')
    File = autoclass('java.io.File')
    BufferedReader = autoclass('java.io.BufferedReader')
    InputStreamReader = autoclass('java.io.InputStreamReader')
    Runtime = autoclass('java.lang.Runtime')


class BMSReader:
    """比亚迪BMS电池数据读取器"""

    # BMS相关系统文件路径
    POWER_SUPPLY_BASE = "/sys/class/power_supply"
    BATTERY_PATH = "/sys/class/power_supply/battery"
    BMS_PATH = "/sys/class/power_supply/bms"
    CHARGER_PATH = "/sys/class/power_supply/charger"
    USB_PATH = "/sys/class/power_supply/usb"

    # BYD专用CAN/BMS数据路径（根据车型可能不同）
    BYD_CAN_PATHS = [
        "/sys/devices/platform/byd_can/",
        "/sys/devices/virtual/byd_bms/",
        "/sys/kernel/byd_bms/",
        "/proc/byd_bms/",
        "/sys/class/byd_bms/",
        # 22款宋Pro DMi 特有路径
        "/sys/devices/platform/soc/soc:byd_bms/",
        "/sys/devices/platform/soc/bydec-bms/",
        "/sys/class/power_supply/byd_battery/",
        "/sys/devices/virtual/power_supply/byd_bms/",
        "/sys/devices/platform/mtk_bms/",
        "/sys/devices/platform/mediatek_bms/",
        "/proc/byd_can/",
        "/sys/kernel/debug/byd_bms/",
        "/sys/class/misc/byd_bms/",
    ]

    # 比亚迪DMi车型特有CAN ID
    BYD_DMI_CAN_IDS = {
        "BMS_SOC": 0x350,        # SOC信息
        "BMS_VOLTAGE": 0x351,    # 总电压
        "BMS_CURRENT": 0x352,    # 电流
        "BMS_TEMP": 0x353,       # 温度
        "BMS_SOH": 0x354,        # 健康度
        "BMS_CYCLE": 0x355,      # 循环次数
        "BMS_CELL_V1_4": 0x360,  # 电芯1-4电压
        "BMS_CELL_V5_8": 0x361,  # 电芯5-8电压
        "BMS_CELL_V9_12": 0x362, # 电芯9-12电压
        "BMS_CELL_T1_4": 0x363,  # 电芯1-4温度
        "BMS_CELL_T5_8": 0x364,  # 电芯5-8温度
        "BMS_INSULATION": 0x365, # 绝缘电阻
        "BMS_STATUS": 0x366,     # 状态信息
        "BMS_FW_VERSION": 0x367, # 固件版本
    }

    # 电池属性文件映射
    BATTERY_FILES = {
        "capacity": "capacity",           # 当前电量百分比
        "capacity_raw": "capacity_raw",   # 原始容量值
        "charge_full": "charge_full",     # 充满容量 (mAh)
        "charge_full_design": "charge_full_design",  # 设计容量 (mAh)
        "charge_counter": "charge_counter",  # 充电计数器
        "current_now": "current_now",     # 当前电流 (mA或uA)
        "current_avg": "current_avg",     # 平均电流
        "voltage_now": "voltage_now",     # 当前电压 (mV或uV)
        "voltage_avg": "voltage_avg",     # 平均电压
        "voltage_max": "voltage_max_design",  # 最大电压
        "voltage_min": "voltage_min_design",  # 最小电压
        "temp": "temp",                   # 温度 (0.1°C)
        "temp_ambient": "temp_ambient",   # 环境温度
        "health": "health",               # 健康状态
        "status": "status",               # 充电状态
        "technology": "technology",       # 电池技术
        "type": "type",                   # 电池类型
        "present": "present",             # 电池是否存在
        "cycle_count": "cycle_count",     # 循环次数
        "time_to_full_now": "time_to_full_now",  # 充满剩余时间
        "time_to_empty_now": "time_to_empty_now",  # 放空剩余时间
        "charge_type": "charge_type",     # 充电类型
        "battery_charging_enabled": "battery_charging_enabled",
        "input_current_max": "input_current_max",
        "input_current_settled": "input_current_settled",
        "constant_charge_current_max": "constant_charge_current_max",
        "fastcharge_mode": "fastcharge_mode",
        "system_temp_level": "system_temp_level",
        "resistance": "resistance",       # 内阻
        "resistance_now": "resistance_now",
        "resistance_id": "resistance_id",
        "soh": "soh",                     # State of Health
        "cell_voltage": "cell_voltage",   # 电芯电压
        "cell_balance": "cell_balance",   # 电芯平衡状态
    }

    # BMS专用文件
    BMS_FILES = {
        "bms_capacity": "capacity",
        "bms_voltage": "voltage",
        "bms_current": "current",
        "bms_temp": "temp",
        "bms_soh": "soh",
        "bms_soc": "soc",
        "bms_cycle": "cycle_count",
        "bms_cell_v1": "cell_voltage_1",
        "bms_cell_v2": "cell_voltage_2",
        "bms_cell_v3": "cell_voltage_3",
        "bms_cell_v4": "cell_voltage_4",
        "bms_cell_v5": "cell_voltage_5",
        "bms_cell_v6": "cell_voltage_6",
        "bms_cell_v7": "cell_voltage_7",
        "bms_cell_v8": "cell_voltage_8",
        "bms_cell_v9": "cell_voltage_9",
        "bms_cell_v10": "cell_voltage_10",
        "bms_cell_v11": "cell_voltage_11",
        "bms_cell_v12": "cell_voltage_12",
        "bms_cell_t1": "cell_temp_1",
        "bms_cell_t2": "cell_temp_2",
        "bms_cell_t3": "cell_temp_3",
        "bms_cell_t4": "cell_temp_4",
        "bms_cell_r1": "cell_resistance_1",
        "bms_cell_r2": "cell_resistance_2",
        "bms_cell_r3": "cell_resistance_3",
        "bms_cell_r4": "cell_resistance_4",
        "bms_total_voltage": "total_voltage",
        "bms_max_cell_v": "max_cell_voltage",
        "bms_min_cell_v": "min_cell_voltage",
        "bms_cell_diff": "cell_voltage_diff",
        "bms_charge_power": "charge_power_limit",
        "bms_discharge_power": "discharge_power_limit",
        "bms_insulation": "insulation_resistance",
        "bms_serial": "serial_number",
        "bms_fw_version": "firmware_version",
        "bms_hw_version": "hardware_version",
    }

    def __init__(self):
        self.data = {}
        self.cell_voltages = []
        self.cell_temps = []
        self.cell_resistances = []
        self.errors = []
        self.available_sources = []
        self.is_byd_device = False
        self.device_info = {}
        self._check_available_sources()
        self._detect_byd_device()

    def _check_available_sources(self):
        """检查可用的数据源"""
        if os.path.exists(self.BATTERY_PATH):
            self.available_sources.append("battery_sysfs")
        if os.path.exists(self.BMS_PATH):
            self.available_sources.append("bms_sysfs")
        if HAS_JNIUS:
            self.available_sources.append("battery_manager_api")
        for path in self.BYD_CAN_PATHS:
            if os.path.exists(path):
                self.available_sources.append(f"byd_can:{path}")
                break

    def _detect_byd_device(self):
        """检测是否为比亚迪设备"""
        try:
            # 检查系统属性
            if HAS_JNIUS:
                try:
                    SystemProperties = autoclass('android.os.SystemProperties')
                    manufacturer = SystemProperties.get('ro.product.manufacturer', '')
                    model = SystemProperties.get('ro.product.model', '')
                    brand = SystemProperties.get('ro.product.brand', '')
                    self.device_info['manufacturer'] = manufacturer
                    self.device_info['model'] = model
                    self.device_info['brand'] = brand
                    if 'BYD' in manufacturer.upper() or 'BYD' in brand.upper() or 'BYD' in model.upper():
                        self.is_byd_device = True
                except Exception:
                    pass
            # 通过构建属性检测
            build_prop = self._read_file_safe('/system/build.prop')
            if build_prop:
                for line in build_prop.split('\n'):
                    if 'ro.product.manufacturer' in line:
                        val = line.split('=')[-1].strip()
                        self.device_info['manufacturer'] = val
                        if 'BYD' in val.upper():
                            self.is_byd_device = True
                    if 'ro.product.model' in line:
                        self.device_info['model'] = line.split('=')[-1].strip()
            # 检测比亚迪特有文件
            byd_indicator_files = [
                '/sys/class/power_supply/byd_battery/',
                '/proc/byd_can/',
                '/sys/devices/platform/byd_can/',
            ]
            for path in byd_indicator_files:
                if os.path.exists(path):
                    self.is_byd_device = True
                    break
        except Exception as e:
            self.errors.append(f"设备检测异常: {str(e)}")

    def check_adb_permissions(self):
        """检查ADB/root权限状态"""
        permissions = {
            "has_root": False,
            "has_adb": False,
            "can_read_sysfs": False,
            "can_execute_dumpsys": False,
            "can_read_bms": False,
        }
        # 检查root权限
        try:
            result = subprocess.run(
                'su -c "id" 2>/dev/null', shell=True,
                capture_output=True, text=True, timeout=3
            )
            if 'uid=0' in result.stdout or 'root' in result.stdout:
                permissions["has_root"] = True
        except Exception:
            pass
        # 检查ADB可用性
        try:
            result = subprocess.run(
                'adb version 2>/dev/null', shell=True,
                capture_output=True, text=True, timeout=3
            )
            if 'Android Debug Bridge' in result.stdout:
                permissions["has_adb"] = True
        except Exception:
            pass
        # 检查sysfs读取权限
        try:
            test_file = '/sys/class/power_supply/battery/capacity'
            if os.path.exists(test_file):
                with open(test_file, 'r') as f:
                    f.read()
                    permissions["can_read_sysfs"] = True
        except Exception:
            pass
        # 检查BMS路径
        try:
            if os.path.exists(self.BMS_PATH):
                test_file = os.path.join(self.BMS_PATH, 'capacity')
                if os.path.exists(test_file):
                    with open(test_file, 'r') as f:
                        f.read()
                        permissions["can_read_bms"] = True
        except Exception:
            pass
        # 检查dumpsys权限
        try:
            result = subprocess.run(
                'dumpsys battery 2>/dev/null | head -5', shell=True,
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0 and result.stdout.strip():
                permissions["can_execute_dumpsys"] = True
        except Exception:
            pass
        return permissions

    def _read_file_safe(self, filepath):
        """安全读取文件内容"""
        try:
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    return f.read().strip()
        except (PermissionError, IOError, OSError) as e:
            self.errors.append(f"读取失败 {filepath}: {str(e)}")
        return None

    def _read_int(self, filepath):
        """读取整数值"""
        val = self._read_file_safe(filepath)
        if val is not None:
            try:
                return int(val)
            except ValueError:
                return None
        return None

    def _read_float(self, filepath):
        """读取浮点值"""
        val = self._read_file_safe(filepath)
        if val is not None:
            try:
                return float(val)
            except ValueError:
                return None
        return None

    def _execute_shell(self, command):
        """执行shell命令"""
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True,
                text=True, timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                self.errors.append(f"命令执行失败: {command} - {result.stderr}")
        except (subprocess.TimeoutExpired, Exception) as e:
            self.errors.append(f"命令执行异常: {command} - {str(e)}")
        return None

    def read_battery_sysfs(self):
        """从/sys/class/power_supply/battery读取数据"""
        data = {}
        base = self.BATTERY_PATH

        for key, filename in self.BATTERY_FILES.items():
            filepath = os.path.join(base, filename)
            val = self._read_file_safe(filepath)
            if val is not None:
                # 尝试转换为数字
                try:
                    if '.' in val:
                        data[key] = float(val)
                    else:
                        data[key] = int(val)
                except ValueError:
                    data[key] = val

        return data

    def read_bms_sysfs(self):
        """从/sys/class/power_supply/bms读取专用BMS数据"""
        data = {}
        if not os.path.exists(self.BMS_PATH):
            return data

        for key, filename in self.BMS_FILES.items():
            filepath = os.path.join(self.BMS_PATH, filename)
            val = self._read_file_safe(filepath)
            if val is not None:
                try:
                    if '.' in val:
                        data[key] = float(val)
                    else:
                        data[key] = int(val)
                except ValueError:
                    data[key] = val

        return data

    def read_battery_manager_api(self):
        """通过Android BatteryManager API读取数据"""
        if not HAS_JNIUS:
            return {}

        data = {}
        try:
            activity = PythonActivity.mActivity
            ifilter = IntentFilter(Intent.ACTION_BATTERY_CHANGED)
            intent = activity.registerReceiver(None, ifilter)

            if intent:
                # 基本属性
                data["api_level"] = intent.getIntExtra(BatteryManager.EXTRA_LEVEL, -1)
                data["api_scale"] = intent.getIntExtra(BatteryManager.EXTRA_SCALE, -1)
                data["api_voltage"] = intent.getIntExtra(BatteryManager.EXTRA_VOLTAGE, -1)
                data["api_temperature"] = intent.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, -1)
                data["api_technology"] = intent.getStringExtra(BatteryManager.EXTRA_TECHNOLOGY)
                data["api_health"] = intent.getIntExtra(BatteryManager.EXTRA_HEALTH, -1)
                data["api_status"] = intent.getIntExtra(BatteryManager.EXTRA_STATUS, -1)
                data["api_plugged"] = intent.getIntExtra(BatteryManager.EXTRA_PLUGGED, -1)
                data["api_present"] = intent.getBooleanExtra(BatteryManager.EXTRA_PRESENT, False)

                # 计算电量百分比
                if data["api_scale"] > 0:
                    data["api_capacity_pct"] = int(data["api_level"] * 100 / data["api_scale"])

                # 温度转换 (0.1°C -> °C)
                if data["api_temperature"] != -1:
                    data["api_temp_celsius"] = data["api_temperature"] / 10.0

            # Android 5.0+ 获取更多属性
            if hasattr(BatteryManager, 'BATTERY_PROPERTY_CAPACITY'):
                bm = activity.getSystemService(Context.BATTERY_SERVICE)
                if bm:
                    props = [
                        ("BATTERY_PROPERTY_CHARGE_COUNTER", BatteryManager.BATTERY_PROPERTY_CHARGE_COUNTER),
                        ("BATTERY_PROPERTY_CURRENT_NOW", BatteryManager.BATTERY_PROPERTY_CURRENT_NOW),
                        ("BATTERY_PROPERTY_CURRENT_AVERAGE", BatteryManager.BATTERY_PROPERTY_CURRENT_AVERAGE),
                        ("BATTERY_PROPERTY_CAPACITY", BatteryManager.BATTERY_PROPERTY_CAPACITY),
                        ("BATTERY_PROPERTY_ENERGY_COUNTER", BatteryManager.BATTERY_PROPERTY_ENERGY_COUNTER),
                    ]
                    for name, prop_id in props:
                        try:
                            val = bm.getLongProperty(prop_id)
                            data[f"api_{name}"] = val
                        except Exception:
                            pass

        except Exception as e:
            self.errors.append(f"BatteryManager API错误: {str(e)}")

        return data

    def read_byd_can_data(self):
        """尝试读取BYD CAN总线数据"""
        data = {}
        for base_path in self.BYD_CAN_PATHS:
            if os.path.exists(base_path):
                try:
                    for item in os.listdir(base_path):
                        filepath = os.path.join(base_path, item)
                        if os.path.isfile(filepath):
                            val = self._read_file_safe(filepath)
                            if val:
                                try:
                                    if '.' in val:
                                        data[f"can_{item}"] = float(val)
                                    else:
                                        data[f"can_{item}"] = int(val)
                                except ValueError:
                                    data[f"can_{item}"] = val
                except PermissionError:
                    self.errors.append(f"无法访问CAN数据路径: {base_path}")
        return data

    def read_dumpsys_battery(self):
        """通过dumpsys获取电池信息"""
        output = self._execute_shell("dumpsys batterystats")
        if not output:
            output = self._execute_shell("dumpsys battery")
        return output

    def read_dumpsys_battery_properties(self):
        """通过dumpsys batteryproperties获取电池属性"""
        output = self._execute_shell("dumpsys batteryproperties")
        return output

    def parse_dumpsys_data(self, dumpsys_output):
        """解析dumpsys输出"""
        data = {}
        if not dumpsys_output:
            return data

        patterns = {
            "level": r"level:\s*(\d+)",
            "scale": r"scale:\s*(\d+)",
            "voltage": r"voltage:\s*(\d+)",
            "temperature": r"temperature:\s*(\d+)",
            "technology": r"technology:\s*(\w+)",
            "health": r"health:\s*(\d+)",
            "status": r"status:\s*(\d+)",
            "plugged": r"plugged:\s*(\d+)",
            "charge_counter": r"charge counter:\s*(\d+)",
            "max_charging_current": r"max charging current:\s*(\d+)",
            "max_charging_voltage": r"max charging voltage:\s*(\d+)",
            "capacity": r"capacity:\s*(\d+)",
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, dumpsys_output, re.IGNORECASE)
            if match:
                try:
                    data[f"dumpsys_{key}"] = int(match.group(1))
                except ValueError:
                    data[f"dumpsys_{key}"] = match.group(1)

        return data

    def read_all(self):
        """读取所有可用的电池数据"""
        self.errors = []
        all_data = OrderedDict()
        all_data["timestamp"] = datetime.now().isoformat()
        all_data["available_sources"] = self.available_sources

        # 1. 系统文件数据
        battery_data = self.read_battery_sysfs()
        if battery_data:
            all_data["battery_sysfs"] = battery_data

        # 2. BMS专用数据
        bms_data = self.read_bms_sysfs()
        if bms_data:
            all_data["bms_sysfs"] = bms_data

        # 3. Android API数据
        if HAS_JNIUS:
            api_data = self.read_battery_manager_api()
            if api_data:
                all_data["battery_api"] = api_data

        # 4. CAN总线数据
        can_data = self.read_byd_can_data()
        if can_data:
            all_data["byd_can"] = can_data

        # 5. Dumpsys数据
        dumpsys_out = self.read_dumpsys_battery()
        if dumpsys_out:
            parsed = self.parse_dumpsys_data(dumpsys_out)
            if parsed:
                all_data["dumpsys"] = parsed

        # 6. 尝试读取更多系统信息
        self._read_additional_system_info(all_data)

        self.data = all_data
        return all_data

    def _read_additional_system_info(self, all_data):
        """读取额外的系统信息"""
        extra_info = {}

        # 尝试读取电池序列号
        serial = self._read_file_safe("/sys/class/power_supply/battery/serial_number")
        if serial:
            extra_info["serial_number"] = serial

        # 制造商信息
        manufacturer = self._read_file_safe("/sys/class/power_supply/battery/manufacturer")
        if manufacturer:
            extra_info["manufacturer"] = manufacturer

        # 型号
        model_name = self._read_file_safe("/sys/class/power_supply/battery/model_name")
        if model_name:
            extra_info["model_name"] = model_name

        # 尝试读取电池循环次数（多种路径）
        cycle_paths = [
            "/sys/class/power_supply/battery/cycle_count",
            "/sys/class/power_supply/battery/charge_cycle",
            "/sys/class/power_supply/bms/cycle_count",
            "/sys/devices/platform/byd_bms/cycle_count",
        ]
        for path in cycle_paths:
            cycle = self._read_int(path)
            if cycle is not None:
                extra_info["cycle_count"] = cycle
                break

        if extra_info:
            all_data["extra_info"] = extra_info

    def get_voltage(self):
        """获取电池总电压 (V)"""
        voltage = None

        # 尝试从系统文件获取
        v = self._read_int(os.path.join(self.BATTERY_PATH, "voltage_now"))
        if v is not None:
            # 电压单位可能是uV或mV
            if abs(v) > 1000000:  # uV
                voltage = v / 1000000.0
            elif abs(v) > 10000:  # mV
                voltage = v / 1000.0
            else:  # 已经是V
                voltage = float(v)

        # 尝试从BMS获取
        if voltage is None:
            bms_data = self.data.get("bms_sysfs", {})
            v = bms_data.get("bms_total_voltage")
            if v is not None:
                if v > 100:  # 可能是mV
                    voltage = v / 1000.0
                else:
                    voltage = float(v)

        # 尝试从API获取
        if voltage is None:
            api_data = self.data.get("battery_api", {})
            v = api_data.get("api_voltage")
            if v is not None and v > 0:
                voltage = v / 1000.0  # mV -> V

        return voltage

    def get_current(self):
        """获取电池电流 (A)，正值为充电，负值为放电"""
        current = None

        c = self._read_int(os.path.join(self.BATTERY_PATH, "current_now"))
        if c is not None:
            if abs(c) > 100000:  # uA
                current = c / 1000000.0
            elif abs(c) > 1000:  # mA
                current = c / 1000.0
            else:
                current = float(c)

        if current is None:
            bms_data = self.data.get("bms_sysfs", {})
            c = bms_data.get("bms_current")
            if c is not None:
                if abs(c) > 1000:
                    current = c / 1000.0
                else:
                    current = float(c)

        if current is None:
            api_data = self.data.get("battery_api", {})
            c = api_data.get("api_BATTERY_PROPERTY_CURRENT_NOW")
            if c is not None:
                if abs(c) > 1000000:
                    current = c / 1000000.0
                elif abs(c) > 1000:
                    current = c / 1000.0
                else:
                    current = float(c)

        return current

    def get_temperature(self):
        """获取电池温度 (°C)"""
        temp = None

        t = self._read_int(os.path.join(self.BATTERY_PATH, "temp"))
        if t is not None:
            if abs(t) > 100:  # 0.1°C
                temp = t / 10.0
            else:
                temp = float(t)

        if temp is None:
            api_data = self.data.get("battery_api", {})
            t = api_data.get("api_temp_celsius")
            if t is not None:
                temp = float(t)

        return temp

    def get_capacity_percent(self):
        """获取电池剩余容量百分比"""
        cap = self._read_int(os.path.join(self.BATTERY_PATH, "capacity"))
        if cap is not None:
            return cap

        api_data = self.data.get("battery_api", {})
        cap = api_data.get("api_capacity_pct")
        return cap

    def get_charge_full(self):
        """获取充满容量 (Ah)"""
        cap = self._read_int(os.path.join(self.BATTERY_PATH, "charge_full"))
        if cap is not None:
            if cap > 100000:  # uAh
                return cap / 1000000.0
            elif cap > 1000:  # mAh
                return cap / 1000.0
        return None

    def get_charge_full_design(self):
        """获取设计容量 (Ah)"""
        cap = self._read_int(os.path.join(self.BATTERY_PATH, "charge_full_design"))
        if cap is not None:
            if cap > 100000:
                return cap / 1000000.0
            elif cap > 1000:
                return cap / 1000.0
        return None

    def get_soh(self):
        """计算电池健康度 (SOH)"""
        # 首先尝试从比亚迪专用数据读取
        byd_data = self.data.get("byd_specific", {})
        if "soh_percent" in byd_data:
            return float(byd_data["soh_percent"])
        if "bms_soh" in byd_data:
            return float(byd_data["bms_soh"])

        # 尝试直接读取SOH
        soh = self._read_int(os.path.join(self.BATTERY_PATH, "soh"))
        if soh is not None:
            return float(soh)

        bms_data = self.data.get("bms_sysfs", {})
        soh = bms_data.get("bms_soh")
        if soh is not None:
            return float(soh)

        # 通过充满容量/设计容量计算
        charge_full = self.get_charge_full()
        charge_design = self.get_charge_full_design()

        if charge_full and charge_design and charge_design > 0:
            return (charge_full / charge_design) * 100.0

        return None

    def get_cycle_count(self):
        """获取电池循环次数"""
        # 首先尝试从比亚迪专用数据读取
        byd_data = self.data.get("byd_specific", {})
        if "cycle_count" in byd_data:
            try:
                return int(byd_data["cycle_count"])
            except (ValueError, TypeError):
                pass

        # 多种路径尝试
        paths = [
            "/sys/class/power_supply/battery/cycle_count",
            "/sys/class/power_supply/battery/charge_cycle",
            "/sys/class/power_supply/bms/cycle_count",
            "/sys/devices/platform/byd_bms/cycle_count",
        ]
        for path in paths:
            count = self._read_int(path)
            if count is not None:
                return count

        bms_data = self.data.get("bms_sysfs", {})
        count = bms_data.get("bms_cycle")
        if count is not None:
            return int(count)

        return None

    def get_cell_voltages(self):
        """获取各电芯电压"""
        cells = []

        # 首先尝试从比亚迪专用数据读取
        byd_data = self.data.get("byd_specific", {})
        if "cell_voltages_raw" in byd_data:
            raw = byd_data["cell_voltages_raw"]
            try:
                parts = raw.replace('\n', ',').replace(' ', ',').split(',')
                for p in parts:
                    try:
                        v = float(p.strip())
                        if v > 100:
                            cells.append(v / 1000.0)
                        elif v > 0:
                            cells.append(v)
                    except ValueError:
                        pass
            except Exception:
                pass

        if cells:
            return cells

        # 尝试从BMS路径读取
        bms_data = self.data.get("bms_sysfs", {})
        for i in range(1, 13):
            key = f"bms_cell_v{i}"
            if key in bms_data:
                v = bms_data[key]
                if isinstance(v, (int, float)):
                    if v > 100:  # mV
                        cells.append(v / 1000.0)
                    else:
                        cells.append(float(v))

        if cells:
            return cells

        # 尝试从系统文件读取
        cell_path = os.path.join(self.BATTERY_PATH, "cell_voltage")
        if os.path.exists(cell_path):
            val = self._read_file_safe(cell_path)
            if val:
                # 可能是逗号分隔的值
                parts = val.replace('\n', ',').replace(' ', ',').split(',')
                for p in parts:
                    try:
                        v = float(p.strip())
                        if v > 100:
                            cells.append(v / 1000.0)
                        elif v > 0:
                            cells.append(v)
                    except ValueError:
                        pass

        return cells

    def get_cell_voltage_diff(self):
        """获取电芯压差 (mV)"""
        cells = self.get_cell_voltages()
        if len(cells) >= 2:
            max_v = max(cells)
            min_v = min(cells)
            return (max_v - min_v) * 1000  # 转换为mV
        return None

    def get_resistance(self):
        """获取电池内阻 (mΩ)"""
        # 首先尝试从比亚迪专用数据读取
        byd_data = self.data.get("byd_specific", {})
        if "resistance" in byd_data:
            try:
                r = float(byd_data["resistance"])
                if r < 1:
                    return r * 1000
                elif r < 100:
                    return r
                else:
                    return r / 1000.0
            except (ValueError, TypeError):
                pass

        paths = [
            os.path.join(self.BATTERY_PATH, "resistance"),
            os.path.join(self.BATTERY_PATH, "resistance_now"),
            os.path.join(self.BMS_PATH, "resistance"),
            "/sys/devices/platform/byd_bms/resistance",
        ]
        for path in paths:
            r = self._read_float(path)
            if r is not None:
                if r < 1:  # Ω
                    return r * 1000
                elif r < 100:  # mΩ
                    return r
                else:  # uΩ
                    return r / 1000
        return None

    def get_health_status(self):
        """获取电池健康状态描述"""
        health = self._read_int(os.path.join(self.BATTERY_PATH, "health"))
        health_map = {
            1: "未知",
            2: "良好",
            3: "过热",
            4: "死亡",
            5: "过压",
            6: "故障",
            7: "冷却",
        }
        if health in health_map:
            return health_map[health]

        api_data = self.data.get("battery_api", {})
        api_health = api_data.get("api_health")
        if api_health in health_map:
            return health_map[api_health]

        return "未知"

    def get_charge_status(self):
        """获取充电状态"""
        status = self._read_int(os.path.join(self.BATTERY_PATH, "status"))
        status_map = {
            1: "未知",
            2: "充电中",
            3: "放电中",
            4: "未充电",
            5: "已充满",
        }
        if status in status_map:
            return status_map[status]

        api_data = self.data.get("battery_api", {})
        api_status = api_data.get("api_status")
        if api_status in status_map:
            return status_map[api_status]

        return "未知"

    def get_insulation_resistance(self):
        """获取绝缘电阻值 (kΩ)"""
        bms_data = self.data.get("bms_sysfs", {})
        r = bms_data.get("bms_insulation")
        if r is not None:
            return float(r)
        return None

    def read_byd_spro_dmi_specific(self):
        """针对22款宋Pro DMi 13.5车机的专用数据读取"""
        byd_data = {}

        # 尝试读取比亚迪专用proc接口
        proc_paths = [
            "/proc/byd_bms/bms_info",
            "/proc/byd_bms/bms_status",
            "/proc/byd_bms/cell_voltage",
            "/proc/byd_bms/cell_temp",
            "/proc/byd_bms/soh",
            "/proc/byd_bms/cycle_count",
            "/proc/byd_can/bms_data",
        ]

        for path in proc_paths:
            content = self._read_file_safe(path)
            if content:
                key = path.split("/")[-1]
                byd_data[key] = content

        # 尝试读取sysfs比亚迪专用节点
        sys_byd_paths = [
            "/sys/devices/platform/byd_bms/bms_soc",
            "/sys/devices/platform/byd_bms/bms_soh",
            "/sys/devices/platform/byd_bms/bms_voltage",
            "/sys/devices/platform/byd_bms/bms_current",
            "/sys/devices/platform/byd_bms/bms_temp",
            "/sys/devices/platform/byd_bms/cycle_count",
            "/sys/devices/platform/byd_bms/cell_voltage_max",
            "/sys/devices/platform/byd_bms/cell_voltage_min",
            "/sys/devices/platform/byd_bms/cell_voltage_diff",
            "/sys/devices/platform/byd_bms/charge_full",
            "/sys/devices/platform/byd_bms/charge_full_design",
            "/sys/devices/platform/byd_bms/resistance",
            "/sys/devices/platform/byd_bms/insulation_resistance",
            "/sys/devices/platform/byd_bms/charge_power_limit",
            "/sys/devices/platform/byd_bms/discharge_power_limit",
        ]

        for path in sys_byd_paths:
            val = self._read_file_safe(path)
            if val:
                key = path.split("/")[-1]
                try:
                    byd_data[key] = float(val)
                except ValueError:
                    byd_data[key] = val

        # 通过dumpsys获取更详细的电池属性
        dumpsys_props = self._execute_shell("dumpsys batteryproperties")
        if dumpsys_props:
            byd_data["dumpsys_properties"] = dumpsys_props

        # 尝试读取电池健康度 (SOH)
        soh_paths = [
            "/sys/class/power_supply/battery/soh",
            "/sys/class/power_supply/bms/soh",
            "/sys/class/power_supply/battery/capacity_level",
            "/sys/devices/platform/byd_bms/soh",
        ]
        for path in soh_paths:
            soh = self._read_file_safe(path)
            if soh:
                try:
                    byd_data["soh_percent"] = float(soh)
                    break
                except ValueError:
                    pass

        # 读取电芯电压数组 (如果存在)
        cell_v_path = "/sys/devices/platform/byd_bms/cell_voltages"
        cell_v_content = self._read_file_safe(cell_v_path)
        if cell_v_content:
            byd_data["cell_voltages_raw"] = cell_v_content

        # 读取电池序列号
        serial_paths = [
            "/sys/class/power_supply/battery/serial_number",
            "/sys/devices/platform/byd_bms/serial_number",
            "/sys/class/power_supply/bms/serial_number",
        ]
        for path in serial_paths:
            serial = self._read_file_safe(path)
            if serial:
                byd_data["serial_number"] = serial
                break

        # 读取电池制造商
        mfr_paths = [
            "/sys/class/power_supply/battery/manufacturer",
            "/sys/devices/platform/byd_bms/manufacturer",
        ]
        for path in mfr_paths:
            mfr = self._read_file_safe(path)
            if mfr:
                byd_data["manufacturer"] = mfr
                break

        # 读取电池型号
        model_paths = [
            "/sys/class/power_supply/battery/model_name",
            "/sys/devices/platform/byd_bms/model_name",
        ]
        for path in model_paths:
            model = self._read_file_safe(path)
            if model:
                byd_data["model_name"] = model
                break

        if byd_data:
            self.data["byd_specific"] = byd_data

        return byd_data

    def get_power_limits(self):
        """获取充放电功率限制"""
        bms_data = self.data.get("bms_sysfs", {})
        charge = bms_data.get("bms_charge_power")
        discharge = bms_data.get("bms_discharge_power")
        return {
            "charge_power_kw": charge / 1000.0 if charge else None,
            "discharge_power_kw": discharge / 1000.0 if discharge else None,
        }

    def get_battery_info(self):
        """获取电池基本信息"""
        # 首先尝试从比亚迪专用数据读取
        byd_data = self.data.get("byd_specific", {})
        
        manufacturer = byd_data.get("manufacturer")
        model_name = byd_data.get("model_name")
        serial = byd_data.get("serial_number")
        
        # 如果专用数据中没有，则从系统文件读取
        if not manufacturer:
            manufacturer = self._read_file_safe(
                os.path.join(self.BATTERY_PATH, "manufacturer")) or "比亚迪"
        
        if not model_name:
            model_name = self._read_file_safe(
                os.path.join(self.BATTERY_PATH, "model_name")) or "刀片电池"
        
        if not serial:
            serial = self._read_file_safe(
                os.path.join(self.BATTERY_PATH, "serial_number"))
        
        technology = self._read_file_safe(
            os.path.join(self.BATTERY_PATH, "technology")) or "LiFePO4"
        
        return {
            "manufacturer": manufacturer,
            "model_name": model_name,
            "technology": technology,
            "serial": serial,
        }

    def get_comprehensive_data(self):
        """获取综合电池数据"""
        self.read_all()
        self.read_byd_spro_dmi_specific()

        cells = self.get_cell_voltages()
        voltage = self.get_voltage()
        current = self.get_current()
        temp = self.get_temperature()
        soh = self.get_soh()
        cycle = self.get_cycle_count()
        resistance = self.get_resistance()
        cell_diff = self.get_cell_voltage_diff()
        charge_full = self.get_charge_full()
        charge_design = self.get_charge_full_design()
        capacity_pct = self.get_capacity_percent()
        permissions = self.check_adb_permissions()

        result = OrderedDict()

        # 设备信息
        result["采集时间"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        result["数据源"] = ", ".join(self.available_sources) if self.available_sources else "无可用数据源"
        result["设备类型"] = "比亚迪车机" if self.is_byd_device else "通用Android设备"
        if self.device_info.get('model'):
            result["设备型号"] = self.device_info['model']
        if self.device_info.get('manufacturer'):
            result["设备制造商"] = self.device_info['manufacturer']

        # ADB权限状态
        result["ADB权限"] = "已授权" if permissions["has_root"] or permissions["can_read_sysfs"] else "受限"
        result["Root权限"] = "已获取" if permissions["has_root"] else "未获取"
        result["BMS数据读取"] = "可用" if permissions["can_read_bms"] else "不可用"
        result["系统数据读取"] = "可用" if permissions["can_read_sysfs"] else "不可用"

        # 电池基本信息
        info = self.get_battery_info()
        result["电池制造商"] = info.get("manufacturer", "未知")
        result["电池型号"] = info.get("model_name", "未知")
        result["电池类型"] = info.get("technology", "未知")
        if info.get("serial"):
            result["电池序列号"] = info["serial"]

        # 状态信息
        result["电池健康状态"] = self.get_health_status()
        result["充放电状态"] = self.get_charge_status()

        # 核心数据
        result["当前电量"] = f"{capacity_pct}%" if capacity_pct is not None else "N/A"
        result["电池健康度(SOH)"] = f"{soh:.2f}%" if soh is not None else "N/A"
        result["总电压"] = f"{voltage:.2f}V" if voltage is not None else "N/A"
        result["电流"] = f"{current:.2f}A" if current is not None else "N/A"
        result["电池温度"] = f"{temp:.1f}°C" if temp is not None else "N/A"

        # 容量信息
        if charge_full is not None:
            result["当前满充容量"] = f"{charge_full:.2f}Ah"
        if charge_design is not None:
            result["设计容量"] = f"{charge_design:.2f}Ah"
        if charge_full and charge_design:
            degradation = charge_design - charge_full
            result["容量衰减"] = f"{degradation:.2f}Ah ({degradation/charge_design*100:.2f}%)"

        # 内阻
        if resistance is not None:
            result["电池内阻"] = f"{resistance:.2f}mΩ"

        # 循环次数
        if cycle is not None:
            result["循环次数"] = str(cycle)

        # 电芯数据
        if cells:
            result["电芯数量"] = str(len(cells))
            result["最高电芯电压"] = f"{max(cells):.3f}V"
            result["最低电芯电压"] = f"{min(cells):.3f}V"
            if cell_diff is not None:
                result["电芯压差"] = f"{cell_diff:.1f}mV"

        # 绝缘电阻
        ins_r = self.get_insulation_resistance()
        if ins_r is not None:
            result["绝缘电阻"] = f"{ins_r:.1f}kΩ"

        # 功率限制
        power = self.get_power_limits()
        if power["charge_power_kw"] is not None:
            result["充电功率限制"] = f"{power['charge_power_kw']:.1f}kW"
        if power["discharge_power_kw"] is not None:
            result["放电功率限制"] = f"{power['discharge_power_kw']:.1f}kW"

        # 估算里程
        if capacity_pct and charge_full and voltage:
            energy_kwh = charge_full * voltage / 1000.0
            available_kwh = energy_kwh * capacity_pct / 100.0
            result["可用电量"] = f"{available_kwh:.2f}kWh"
            result["总电量"] = f"{energy_kwh:.2f}kWh"

        # 错误信息
        if self.errors:
            result["数据读取警告"] = str(len(self.errors))

        result["_errors"] = self.errors
        result["_raw_data"] = self.data
        result["_cells"] = cells

        return result