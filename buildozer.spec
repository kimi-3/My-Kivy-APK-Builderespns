[app]
title = 水质监控
package.name = esp32app
package.domain = org.test
source.dir = .
source.include_exts = py,png,jpg,kv,ttf
source.include_patterns = ph_safe_table.jpg,Font_0.ttf
version = 0.0.1
orientation = portrait
# 最简依赖（仅保留核心）
requirements = python3,kivy==2.2.1,kivymd==1.2.0,pyjnius==1.4.0
entrypoint = main.py

# 基础配置（降级版本，确保兼容）
android.accept_sdk_license = True
android.api = 31
android.minapi = 21
android.ndk = 24b
android.ndk_api = 21
android.sdk = 31
exclude_patterns = **/test/*, **/tests/*
android.gradle_plugin = 7.2.0
p4a.gradle_dependencies = gradle:7.2.0
p4a.bootstrap = sdl2
p4a.gradle_options = -Dorg.gradle.java.home=/usr/lib/jvm/java-17-openjdk-amd64

# ========== 修复后的权限配置（核心！） ==========
# 完整权限（覆盖MQTT/存储/定位/网络）
android.permissions = INTERNET,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE,ACCESS_WIFI_STATE,CHANGE_WIFI_STATE,ACCESS_NETWORK_STATE,ACCESS_FINE_LOCATION,ACCESS_COARSE_LOCATION
# 安卓11+存储权限适配
android.extra_manifest_headers = <application android:requestLegacyExternalStorage="true"/>
# 启动时主动申请权限
android.request_android_permissions = True

# 关键配置（确保生成APK）
android.add_assets = Font_0.ttf,ph_safe_table.jpg
android.debug = True
android.aab = False  # 强制APK

[buildozer]
log_level = 2
warn_on_root = 1
