[app]

# 应用包名 (必须唯一)
package.name = byd_battery_detection
package.domain = com.byd.battery

# 应用名称
title = 比亚迪电池检测

# 源代码目录
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json

# Python版本
requirements = python3,kivy==2.2.1,pyjnius,android

# 应用版本
version = 1.0.0
version.code = 1

# 应用方向
orientation = portrait

# 全屏模式
fullscreen = 1

# 状态栏
android.statusbar_visible = 0

# 窗口权限
android.window_soft_input_mode = adjustResize

# 日志级别
log_level = 2

# 启用日志
logcat_filters = *:V

# Android API级别
android.api = 33
android.minapi = 29
android.ndk = 27c

# 架构支持 (车机通常是arm64-v8a)
android.archs = arm64-v8a

# 权限配置
android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,\
    READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,\
    ACCESS_FINE_LOCATION,ACCESS_COARSE_LOCATION,\
    READ_PHONE_STATE,FOREGROUND_SERVICE,\
    RECEIVE_BOOT_COMPLETED,WAKE_LOCK,\
    REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,\
    PACKAGE_USAGE_STATS,\
    MANAGE_EXTERNAL_STORAGE,READ_MEDIA_IMAGES,READ_MEDIA_VIDEO,READ_MEDIA_AUDIO,\
    ACCESS_MEDIA_LOCATION

# Android 10+ 存储兼容
android.allow_backup = True
android.manifest.request_legacy_external_storage = True

# 特性
android.features = android.hardware.screen.portrait

# 预设
android.presplash_color = #141820
android.splash_color = #141820

# 资源
android.icon = icon.png
android.presplash = presplash.png

# 编译为APK
android.release_artifact = apk
android.debug_artifact = apk

# 启动类
p4a.bootstrap = sdl2

# 窗口背景
android.window_background = #141820

# 允许屏幕常亮
android.wakelock = 1


[buildozer]

# 构建目录
build_dir = .buildozer

# 日志级别
log_level = 2

# 警告级别
warn_on_root = 1

# 超时时间
build_timeout = 7200
