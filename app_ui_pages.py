import datetime
from kivy.config import Config
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.textfield import MDTextField
from kivymd.uix.button import MDIconButton
from kivy.metrics import dp
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle
from kivy.uix.image import Image
from kivy.uix.scrollview import ScrollView
from kivymd.uix.scrollview import MDScrollView
from ui_utils import NoBorderButton
import json
from kivymd.toast import toast
# 新增数据库相关导入（核心）
import sqlite3
import os
import sys
from kivy.utils import platform  # 关键：Kivy官方的平台判断工具

# ========== 数据库工具函数（完整适配PC/安卓） ==========
def get_db_path():
    """
    获取数据库路径（兼容PC/安卓，优先使用应用私有目录）
    安卓端：使用应用私有存储（无需额外权限），避免读写外部存储的权限问题
    """
    try:
        if platform == 'android':
            # 安卓端：获取应用私有目录（推荐），比app_storage_path更稳定
            from android import mActivity
            # 获取应用内部存储目录（/data/data/esp32app/files/）
            app_files_dir = mActivity.getApplicationContext().getFilesDir().getPath()
            db_path = os.path.join(app_files_dir, "sensor_data.db")
        else:
            # PC端（Windows/Linux/Mac）：当前目录
            db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sensor_data.db")
        
        # 确保数据库目录存在（避免创建数据库时报错）
        db_dir = os.path.dirname(db_path)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir)
        
        return db_path
    except Exception as e:
        # 容错：返回当前目录（避免完全崩溃）
        toast(f"获取数据库路径失败：{str(e)}")
        return "sensor_data.db"

def init_db_if_not_exists():
    """初始化数据库表（增加延迟容错）"""
    try:
        # 延迟0.1秒执行，确保安卓路径就绪
        from kivy.clock import Clock
        Clock.schedule_once(_real_init_db, 0.1)
    except:
        # 同步执行（备用）
        _real_init_db()

def _real_init_db(*args):
    """实际初始化逻辑（内部函数）"""
    try:
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sensor_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_date TEXT,  -- 日期（YYYY-MM-DD）
                record_time TEXT,  -- 时间（YYYY-MM-DD HH:MM:SS）
                do_value REAL,     -- 溶解氧
                ph_value REAL,     -- PH值
                temp_value REAL    -- 温度
            )
        ''')
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"数据库初始化失败：{e}")
        if platform == 'android':
            from kivymd.toast import toast
            toast("数据库初始化失败，APP可继续使用")
def insert_sensor_record_to_db(do, ph, temp):
    """插入传感器数据到数据库"""
    init_db_if_not_exists()
    now = datetime.datetime.now()
    record_date = now.strftime("%Y-%m-%d")
    record_time = now.strftime("%Y-%m-%d %H:%M:%S")
    
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO sensor_records (record_date, record_time, do_value, ph_value, temp_value)
        VALUES (?, ?, ?, ?, ?)
    ''', (record_date, record_time, do, ph, temp))
    conn.commit()
    conn.close()
    # 插入后立即清理过期数据（仅保留今日+昨日）
    clean_expired_sensor_data()

def query_sensor_data_by_date(date_type="today"):
    """查询今日/昨日传感器数据"""
    init_db_if_not_exists()
    # 计算目标日期
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    target_date = today if date_type == "today" else yesterday

    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute('''
        SELECT record_time, do_value, ph_value, temp_value
        FROM sensor_records
        WHERE record_date = ?
        ORDER BY record_time DESC
    ''', (target_date,))
    records = cursor.fetchall()
    conn.close()

    # 格式化数据（和原有GLOBAL_HISTORY_DATA格式一致）
    display_data = []
    for record in records:
        time_str, do, ph, temp = record
        display_str = f"{time_str}: 溶解氧{round(do,2)}mg/L | PH{round(ph,1)} | 温度{round(temp,1)}℃"
        display_data.append(display_str)
    return display_data, target_date

def clean_expired_sensor_data():
    """清理今日/昨日之外的过期数据"""
    init_db_if_not_exists()
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute('''
        DELETE FROM sensor_records
        WHERE record_date NOT IN (?, ?)
    ''', (today, yesterday))
    conn.commit()
    conn.close()

# ========== 全局日志存储（所有页面共享） ==========
GLOBAL_LOGS = []  # 存储所有日志
MAX_LOG_LINES = 50  # 最多保留50条日志，避免内存溢出

def add_global_log(log_content):
    """添加日志到全局存储，并触发UI更新"""
    global GLOBAL_LOGS
    # 加上时间戳，方便排查
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    log_with_time = f"[{timestamp}] {log_content}"
    
    GLOBAL_LOGS.append(log_with_time)
    # 限制日志条数
    if len(GLOBAL_LOGS) > MAX_LOG_LINES:
        GLOBAL_LOGS = GLOBAL_LOGS[-MAX_LOG_LINES:]
    
    # 触发所有日志UI更新（如果有）
    if hasattr(add_global_log, 'update_callbacks'):
        for callback in add_global_log.update_callbacks:
            callback()

# 初始化日志更新回调列表
add_global_log.update_callbacks = []

# 全局变量：存储历史数据
GLOBAL_HISTORY_DATA = []
HISTORY_UPDATE_CALLBACKS = []

def register_history_callback(callback):
    if callback not in HISTORY_UPDATE_CALLBACKS:
        HISTORY_UPDATE_CALLBACKS.append(callback)

def unregister_history_callback(callback):
    if callback in HISTORY_UPDATE_CALLBACKS:
        HISTORY_UPDATE_CALLBACKS.remove(callback)

def update_history_data(new_record):
    """统一更新历史数据，并触发UI刷新"""
    GLOBAL_HISTORY_DATA.insert(0, new_record)
    if len(GLOBAL_HISTORY_DATA) > 20:
        GLOBAL_HISTORY_DATA.pop()
    for cb in HISTORY_UPDATE_CALLBACKS:
        cb()

# ========== 日志页面 ==========
def create_log_page(app_instance):
    """创建独立的日志页面（手机上可直接查看）"""
    log_layout = MDBoxLayout(
        orientation="vertical",
        padding=dp(10),
        spacing=dp(10),
        size_hint=(1, 1)
    )

    # 日志页面标题
    log_title = MDLabel(
        text="运行日志",
        font_size=dp(20),
        font_name="CustomChinese",
        halign="center",
        bold=True,
        size_hint_y=None,
        height=dp(50)
    )
    log_layout.add_widget(log_title)

    # 日志滚动视图（核心：可上下滑动查看所有日志）
    log_scroll = MDScrollView(
        size_hint=(1, 1),
        do_scroll_x=False,  # 禁止横向滚动
        bar_width=dp(3),  # 滚动条宽度（手机上更易点击）
        bar_color=(0.2, 0.5, 0.8, 1),  # 滚动条颜色
        bar_inactive_color=(0.8, 0.8, 0.8, 1)
    )

    # 日志内容容器
    log_content = MDLabel(
        text="",
        font_name="CustomChinese",
        font_size=dp(14),
        size_hint_y=None,
        valign="top",
        halign="left"
    )
    # 自动适配高度
    log_content.bind(texture_size=lambda instance, size: setattr(instance, 'size', size))

    # 更新日志UI的函数
    def update_log_ui(*args):
        # 拼接所有日志，换行分隔
        log_text = "\n\n".join(GLOBAL_LOGS) if GLOBAL_LOGS else "暂无日志，等待MQTT连接..."
        log_content.text = log_text
        # 自动滚动到最新日志（底部）
        Clock.schedule_once(lambda dt: setattr(log_scroll, 'scroll_y', 0), 0.1)

    # 初始化时更新一次
    update_log_ui()
    # 注册到全局日志回调（有新日志时自动更新）
    add_global_log.update_callbacks.append(update_log_ui)

    log_scroll.add_widget(log_content)
    log_layout.add_widget(log_scroll)

    # 页面销毁时移除回调（避免内存泄漏）
    def on_remove(instance, parent):
        if update_log_ui in add_global_log.update_callbacks:
            add_global_log.update_callbacks.remove(update_log_ui)
    log_layout.bind(on_remove=on_remove)

    return log_layout

# ========== 首页构建 ==========
def create_home_page(app_instance):
    home_layout = MDBoxLayout(
        orientation="vertical",
        padding=dp(20),
        spacing=dp(20),
        size_hint_y=None,
    )
    home_layout.bind(minimum_height=home_layout.setter('height'))
    
    # 注册MQTT回调（增加重试机制，解决初始化时序问题）
    def register_mqtt_callback(dt):
        if app_instance and hasattr(app_instance, 'mqtt_client') and app_instance.mqtt_client:
            app_instance.mqtt_client.set_parsed_data_callback(update_sensor_ui_and_record_history)
            add_global_log("✅ MQTT回调注册成功")
        else:
            # 延迟1秒重试（最多重试5次）
            if not hasattr(register_mqtt_callback, 'retry_count'):
                register_mqtt_callback.retry_count = 0
            register_mqtt_callback.retry_count += 1
            if register_mqtt_callback.retry_count <= 5:
                add_global_log(f"⚠️ MQTT客户端未初始化，{register_mqtt_callback.retry_count}秒后重试...")
                Clock.schedule_once(register_mqtt_callback, 1)
            else:
                add_global_log("❌ MQTT回调注册失败：达到最大重试次数")
    # 初始延迟1秒（给MQTT更多初始化时间）
    Clock.schedule_once(register_mqtt_callback, 1)

    # 顶部栏：溶解氧 + 手动开关
    top_bar = MDBoxLayout(
        orientation="horizontal",
        spacing=dp(20),
        size_hint_y=None,
        height=dp(30)
    )
    do_label = MDLabel(
        text="溶解氧: 7.25mg/L",
        font_size=dp(18),
        font_name="CustomChinese",
        halign="left",
        valign="middle",
        theme_text_color="Custom",
        text_color=(0, 0, 1, 1)
    )
    
    # PH值和温度标签
    ph_label = MDLabel(
        text="PH值: 7.0",
        font_size=dp(18),
        font_name="CustomChinese",
        theme_text_color="Custom",
        text_color=(0, 0, 1, 1)
    )
    temp_label = MDLabel(
        text="温度: 25.5℃",
        font_size=dp(18),
        font_name="CustomChinese",
        theme_text_color="Custom",
        text_color=(0, 0, 1, 1)
    )

    def update_sensor_ui_and_record_history(parsed_data):
        """更新UI标签 + 记录历史数据 + 入库（新增）"""
        try:
            # 更新溶解氧/PH/温度UI
            if "do" in parsed_data and parsed_data["do"] is not None:
                do_value = round(float(parsed_data["do"]), 2)
                do_label.text = f"溶解氧: {do_value}mg/L"
            if "ph" in parsed_data and parsed_data["ph"] is not None:
                ph_value = round(float(parsed_data["ph"]), 1)
                ph_label.text = f"PH值: {ph_value}"
            if "temp" in parsed_data and parsed_data["temp"] is not None:
                temp_value = round(float(parsed_data["temp"]), 1)
                temp_label.text = f"温度: {temp_value}℃"

            # 记录历史数据
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            do_val = do_label.text.replace("溶解氧: ", "").replace("mg/L", "")
            ph_val = ph_label.text.replace("PH值: ", "")
            temp_val = temp_label.text.replace("温度: ", "").replace("℃", "")
            history_record = f"{current_time}: 溶解氧{do_val}mg/L | PH{ph_val} | 温度{temp_val}℃"
            
            update_history_data(history_record)
            add_global_log(f"📊 传感器数据更新：{history_record}")

            # 新增：将数据插入数据库（仅保留今日/昨日）
            try:
                do_num = float(do_val) if do_val.replace('.','').isdigit() else 0.0
                ph_num = float(ph_val) if ph_val.replace('.','').isdigit() else 0.0
                temp_num = float(temp_val) if temp_val.replace('.','').isdigit() else 0.0
                insert_sensor_record_to_db(do_num, ph_num, temp_num)
            except Exception as e:
                add_global_log(f"❌ 数据入库失败：{str(e)}")

        except (ValueError, TypeError):
            error_msg = "❌ 传感器数据格式异常"
            add_global_log(error_msg)
            do_label.text = "溶解氧: 数据异常mg/L"
            ph_label.text = "PH值: 数据异常"
            temp_label.text = "温度: 数据异常℃"

    # 手动开关
    switch_label = MDLabel(
        text="手动开关",
        font_size=dp(16),
        halign="right",
        valign="middle",
        font_name="CustomChinese",
        size_hint_x=None,
        width=dp(80)
    )
    switch_btn = NoBorderButton(
        text="关",
        button_type="switch",
        size_hint_x=None,
        width=dp(60),
        size_hint_y=None,
        height=dp(30)
    )
    switch_btn.app_instance = app_instance

    def toggle_switch(instance):
        # 切换开关状态
        instance.current_state = "开" if instance.current_state == "关" else "关"
        instance.text = instance.current_state
        instance.update_button_colors()
        
        # 发送数据到MQTT服务器
        send_data = "yes" if instance.current_state == "开" else "no"
        cmd_desc = "启动" if instance.current_state == "开" else "停止"
        
        try:
            if not hasattr(instance, 'app_instance') or not instance.app_instance:
                raise Exception("未获取到APP实例")
            
            mqtt_client = instance.app_instance.mqtt_client
            if not mqtt_client:
                raise Exception("MQTT客户端未初始化")
            
            send_result = mqtt_client.publish_command("esp32/switch", send_data)
            if send_result:
                toast(f"设备{cmd_desc}成功")
                add_global_log(f"📱 手动开关操作：设备{cmd_desc}")
            else:
                raise Exception("MQTT未连接")
        
        except Exception as e:
            error_msg = f"❌ 开关操作失败：{str(e)}"
            add_global_log(error_msg)
            toast(error_msg)

    switch_btn.bind(on_press=toggle_switch)
    top_bar.add_widget(do_label)
    top_bar.add_widget(switch_label)
    top_bar.add_widget(switch_btn)
    home_layout.add_widget(top_bar)

    # 中间区域：阈值输入框 + 按钮列
    middle_layout = MDBoxLayout(
        orientation="horizontal",
        spacing=dp(20),
        size_hint_y=None,
        height=dp(100)
    )
    input_container = MDBoxLayout(
        orientation="vertical",
        spacing=dp(10),
        size_hint_x=1,
        size_hint_y=None,
        height=dp(120)
    )
    max_input = MDBoxLayout(
        orientation="horizontal",
        spacing=dp(10),
        size_hint_y=None,
        height=dp(40)
    )
    max_label = MDLabel(text="设置最高值:", font_size=dp(16), font_name="CustomChinese")
    max_textfield = MDTextField(hint_text="例如：8.0（溶解氧上限）", size_hint_x=1)
    max_input.add_widget(max_label)
    max_input.add_widget(max_textfield)

    min_input = MDBoxLayout(
        orientation="horizontal",
        spacing=dp(10),
        size_hint_y=None,
        height=dp(40)
    )
    min_label = MDLabel(text="设置最低值:", font_size=dp(16), font_name="CustomChinese")
    min_textfield = MDTextField(hint_text="例如：6.0（溶解氧下限）", size_hint_x=1)
    min_input.add_widget(min_label)
    min_input.add_widget(min_textfield)

    input_container.add_widget(max_input)
    input_container.add_widget(min_input)

    # 确认按钮
    button_container = MDBoxLayout(
        orientation="vertical",
        spacing=dp(10),
        size_hint_x=None,
        width=dp(90),
        size_hint_y=None,
        height=dp(120)
    )
    confirm_btn = NoBorderButton(
        text="确认",
        size_hint_x=None,
        width=dp(90),
        size_hint_y=None,
        height=dp(40)
    )
    def check_input_validity(*args):
        max_val = max_textfield.text.strip()
        min_val = min_textfield.text.strip()
        confirm_btn.is_disabled = (not max_val) or (not min_val)
        confirm_btn.update_button_colors()
    max_textfield.bind(text=check_input_validity)
    min_textfield.bind(text=check_input_validity)
    check_input_validity()

    # 确认按钮点击事件
    def on_confirm_click(instance):
        if instance.is_disabled:
            return
        
        instance.is_pressed = True
        instance.update_button_colors()
        
        max_val = max_textfield.text.strip()
        min_val = min_textfield.text.strip()
        
        # 校验输入是否为数字
        try:
            float(max_val)
            float(min_val)
        except ValueError:
            error_msg = f"❌ 阈值输入无效：请输入数字"
            add_global_log(error_msg)
            app_instance._update_recv_data(error_msg)
            Clock.schedule_once(lambda x: instance.reset_button_state(), 2)
            return
        
        # 构造JSON数据
        try:
            threshold_data = json.dumps({
                "max_do": max_val,
                "min_do": min_val,
                "timestamp": str(datetime.datetime.now())
            }, ensure_ascii=False)
        except Exception as e:
            error_msg = f"❌ 构造JSON失败：{str(e)}"
            add_global_log(error_msg)
            app_instance._update_recv_data(error_msg)
            Clock.schedule_once(lambda x: instance.reset_button_state(), 2)
            return
        
        # 发送数据到服务器
        try:
            if not app_instance or not app_instance.mqtt_client:
                raise Exception("MQTT客户端未初始化")
            
            send_result = app_instance.mqtt_client.publish_command("esp32/threshold", threshold_data)
            if send_result:
                success_msg = f"✅ 阈值已发送：最高{max_val} | 最低{min_val}"
                add_global_log(success_msg)
                app_instance._update_recv_data(success_msg)
            else:
                raise Exception("MQTT未连接")
        
        except Exception as e:
            error_msg = f"❌ 发送阈值失败：{str(e)}"
            add_global_log(error_msg)
            app_instance._update_recv_data(error_msg)
        
        Clock.schedule_once(lambda x: instance.reset_button_state(), 2)
    
    confirm_btn.app_instance = app_instance
    confirm_btn.bind(on_press=on_confirm_click)

    # 历史数据按钮
    history_btn = NoBorderButton(
        text="历史数据",
        size_hint_x=None,
        width=dp(90),
        size_hint_y=None,
        height=dp(40)
    )
    def on_history_click(instance):
        instance.is_pressed = True
        instance.update_button_colors()
        from ui_utils import switch_page
        switch_page(app_instance, "history")
        add_global_log("📱 切换到历史数据页面")
        Clock.schedule_once(lambda x: instance.reset_button_state(), 2)
    history_btn.bind(on_press=on_history_click)

    button_container.add_widget(confirm_btn)
    button_container.add_widget(history_btn)
    middle_layout.add_widget(input_container)
    middle_layout.add_widget(button_container)
    home_layout.add_widget(middle_layout)

    # 底部：PH值 + 温度展示
    sensor_layout = MDBoxLayout(
        orientation="horizontal",
        spacing=dp(40),
        size_hint_y=None,
        height=dp(50)
    )
    sensor_layout.add_widget(ph_label)
    sensor_layout.add_widget(temp_label)
    home_layout.add_widget(sensor_layout)

    # PH安全范围图片（取消注释需放置ph_safe_table.jpg到根目录）
    ph_table_layout = MDBoxLayout(
        orientation="horizontal",
        size_hint_y=None,
        height=dp(230),
        pos_hint={"center_x": 0.55}
    )
    ph_table_image = Image(
        source="ph_safe_table.jpg",
        size_hint=(None, None),
        size=(dp(280), dp(280)),
        allow_stretch=True,
        keep_ratio=True
    )
    ph_table_layout.add_widget(ph_table_image)
    home_layout.add_widget(ph_table_layout)

    ph_note_layout = MDBoxLayout(
        orientation="horizontal",
        size_hint_y=None,
        height=dp(40)
    )
    ph_note_label = MDLabel(
        text="PH值安全范围在6~9",
        font_size=dp(16),
        font_name="CustomChinese",
        halign="center",
        bold=True
    )
    ph_note_layout.add_widget(ph_note_label)
    home_layout.add_widget(ph_note_layout)

    return home_layout

# ========== 历史数据页面（仅修改此函数，新增今日/昨日按钮） ==========
# app_ui_pages.py 中 create_history_page 函数修改部分
def create_history_page(app_instance):
    history_layout = MDBoxLayout(
        orientation="vertical",
        padding=dp(20),
        spacing=dp(10),
        size_hint=(1, 1),
    )

    history_title = MDLabel(
        text="设备历史数据",
        font_size=dp(22),
        font_name="CustomChinese",
        halign="center",
        bold=True,
        size_hint_y=None,
        height=dp(60)
    )
    history_layout.add_widget(history_title)

    # ========== 今日/昨日按钮区域（修复核心） ==========
    btn_layout = MDBoxLayout(
        orientation="horizontal",
        spacing=dp(20),
        size_hint_y=None,
        height=dp(50),
        pos_hint={"center_x": 0.5}
    )
    # 今日数据按钮（移除md_bg_color/text_color传参）
    today_btn = NoBorderButton(
        text="今日数据",
        size_hint_x=None,
        width=dp(120),
        height=dp(40)
    )
    # 昨日数据按钮（移除md_bg_color/text_color传参）
    yesterday_btn = NoBorderButton(
        text="昨日数据",
        size_hint_x=None,
        width=dp(120),
        height=dp(40)
    )
    
    # 延迟设置按钮颜色（关键：等canvas初始化完成）
    Clock.schedule_once(lambda dt: today_btn.set_button_colors((0.2, 0.5, 0.8, 1), (1, 1, 1, 1)), 0.02)
    Clock.schedule_once(lambda dt: yesterday_btn.set_button_colors((0.8, 0.8, 0.8, 1), (0, 0, 0, 1)), 0.02)

    btn_layout.add_widget(today_btn)
    btn_layout.add_widget(yesterday_btn)
    history_layout.add_widget(btn_layout)

    scroll_view = ScrollView(
        size_hint=(1, 1),
        do_scroll_x=False,
        scroll_type=['content', 'bars'],
        bar_width=dp(1),
        bar_color=(0.3, 0.3, 0.3, 1),
        bar_inactive_color=(0.8, 0.8, 0.8, 1),
        always_overscroll=True,
        scroll_wheel_distance=dp(20)
    )

    scroll_content = MDBoxLayout(
        orientation="vertical",
        spacing=dp(10),
        size_hint=(1, None),
        padding=dp(5)
    )
    scroll_content.bind(minimum_height=scroll_content.setter('height'))
    
    # 重构刷新函数：支持按日期类型刷新
    def refresh_history_ui(date_type="today"):
        scroll_content.clear_widgets()
        # 从数据库查询对应日期数据
        display_data, target_date = query_sensor_data_by_date(date_type)
        
        # 无数据时的默认提示
        if not display_data:
            display_data = [f"{target_date} 暂无传感器数据"]
        
        # 重新添加数据标签
        for idx, data in enumerate(display_data):
            data_label = MDLabel(
                text=data,
                font_size=dp(16),
                font_name="CustomChinese",
                halign="left",
                size_hint_y=None,
                height=dp(40),
                theme_text_color="Custom",
                text_color=(0.2, 0.2, 0.2, 1) if idx != 0 or len(display_data) > 1 else (0.8, 0, 0, 1),
                valign="middle",
            )
            scroll_content.add_widget(data_label)

    # 按钮点击事件：切换数据+更新按钮样式（改用set_button_colors）
    def show_today(*args):
        today_btn.set_button_colors((0.2, 0.5, 0.8, 1), (1, 1, 1, 1))
        yesterday_btn.set_button_colors((0.8, 0.8, 0.8, 1), (0, 0, 0, 1))
        refresh_history_ui("today")
        toast("已切换到今日数据")

    def show_yesterday(*args):
        yesterday_btn.set_button_colors((0.2, 0.5, 0.8, 1), (1, 1, 1, 1))
        today_btn.set_button_colors((0.8, 0.8, 0.8, 1), (0, 0, 0, 1))
        refresh_history_ui("yesterday")
        toast("已切换到昨日数据")

    # 绑定按钮事件
    today_btn.bind(on_press=show_today)
    yesterday_btn.bind(on_press=show_yesterday)

    # 初始化时加载今日数据
    refresh_history_ui("today")
    # 注册回调（切换页面时自动刷新）
    register_history_callback(lambda: refresh_history_ui("today"))
    add_global_log("📱 进入历史数据页面")

    scroll_view.add_widget(scroll_content)
    history_layout.add_widget(scroll_view)

    # 页面销毁时注销回调
    def on_remove(instance, parent):
        unregister_history_callback(refresh_history_ui)
        add_global_log("📱 退出历史数据页面")
    history_layout.bind(on_remove=on_remove)

    return history_layout


# ========== 个人中心页面 ==========
def create_me_page(app_instance):
    me_layout = MDBoxLayout(
        orientation="vertical",
        padding=dp(20),
        spacing=dp(15),
        size_hint_y=None,
    )
    me_layout.bind(minimum_height=me_layout.setter('height'))
    me_layout.add_widget(MDLabel(
        text="我的个人中心",
        font_size=dp(20),
        halign="center",
        font_name="CustomChinese",
        bold=True
    ))
    
    # 显示MQTT连接状态
    if hasattr(app_instance, 'mqtt_client') and app_instance.mqtt_client:
        connect_status = "已连接" if app_instance.mqtt_client.connected else "未连接"
        status_color = (0, 0.8, 0, 1) if app_instance.mqtt_client.connected else (0.8, 0, 0, 1)
    else:
        connect_status = "未初始化"
        status_color = (0.5, 0.5, 0.5, 1)
    
    status_label = MDLabel(
        text=f"服务器连接状态: {connect_status}",
        font_size=dp(16),
        font_name="CustomChinese",
        theme_text_color="Custom",
        text_color=status_color
    )
    me_layout.add_widget(status_label)
    
    # 设备信息
    me_layout.add_widget(MDLabel(
        text="设备编号：DEV-20260111",
        font_size=dp(16),
        font_name="CustomChinese"
    ))
    me_layout.add_widget(MDLabel(
        text="当前在线：是",
        font_size=dp(16),
        font_name="CustomChinese"
    ))
    # 日志滚动视图
    log_scroll_view = ScrollView(
        size_hint=(1, None),
        height=dp(200),
        do_scroll_x=False
    )
    # 日志标签
    log_label = MDLabel(
        text="", 
        font_name="CustomChinese", 
        size_hint_y=None,
        valign="top",
        halign="left"
    )
    log_label.is_log_label = True  # 标记为日志标签
    log_label.bind(texture_size=log_label.setter('size'))
    # 初始化日志内容
    from main import recv_data_list
    log_label.text = "\n".join(recv_data_list) + "\n"
    log_scroll_view.add_widget(log_label)
    me_layout.add_widget(log_scroll_view)
    add_global_log("📱 进入个人中心页面")

    return me_layout

# ========== 整体UI构建 ==========
def create_app_ui(app_instance):
    # 基础配置
    Window.orientation = 'portrait'
    
    # 注册中文字体
    from ui_utils import register_chinese_font
    register_chinese_font()

    # 主题配置
    app_instance.theme_cls.primary_palette = "Blue"
    app_instance.theme_cls.theme_style = "Light"
    app_instance.theme_cls.font_styles.update({
        "H5": [ "CustomChinese", 24, False, 0.15 ],
        "Body1": [ "CustomChinese", 14, False, 0.15 ]
    })

    # 主容器
    main_container = MDBoxLayout(
        orientation="vertical",
        padding=0,
        spacing=0,
        size_hint=(1, 1)
    )

    # 页面容器（用于切换页面）
    app_instance.page_container = MDScrollView(
        do_scroll_x=False,
        do_scroll_y=True,  # 允许垂直滚动（适配小屏幕）
        size_hint=(1, 1),
        pos_hint={"top": 1.0}
    )
    app_instance.current_page = create_home_page(app_instance)
    app_instance.page_container.add_widget(app_instance.current_page)
    main_container.add_widget(app_instance.page_container)

    # 底部导航栏（首页+日志+我的）
    bottom_nav_bar = MDBoxLayout(
        orientation="horizontal",
        size_hint_y=None,
        height=dp(60),
        padding=[dp(20), dp(5), dp(20), dp(5)],
        spacing=Window.width * 0.1,
        md_bg_color=(1, 1, 1, 1),
        pos_hint={"center_x": 0.5, "y": 0.0}
    )
    # 导航栏阴影
    with bottom_nav_bar.canvas.before:
        Color(0, 0, 0, 0.1)
        Rectangle(
            pos=(bottom_nav_bar.x, bottom_nav_bar.y + bottom_nav_bar.height),
            size=(bottom_nav_bar.width, 2)
        )
    
    # 1. 首页导航项
    nav_item1 = MDBoxLayout(
        orientation="vertical",
        size_hint_x=1,
        spacing=dp(2),
        pos_hint={"center_x": 0.5, "center_y": 0.5}
    )
    nav_item1_icon = MDIconButton(
        icon="home",
        size_hint=(None, None),
        size=(dp(24), dp(24)),
        pos_hint={"center_x": 0.5},
        md_bg_color=(1, 1, 1, 0),
        text_color=(0, 0, 0, 1)
    )
    from ui_utils import switch_page
    nav_item1_icon.bind(on_press=lambda x: switch_page(app_instance, "home"))
    nav_item1_text = MDLabel(
        text="首页",
        font_size=dp(12),
        font_name="CustomChinese",
        halign="center",
        color=(0, 0, 0, 1)
    )
    nav_item1.add_widget(nav_item1_icon)
    nav_item1.add_widget(nav_item1_text)

    # 2. 日志导航项
    nav_item2 = MDBoxLayout(
        orientation="vertical",
        size_hint_x=1,
        spacing=dp(2),
        pos_hint={"center_x": 0.5, "center_y": 0.5}
    )
    nav_item2_icon = MDIconButton(
        icon="file-document-outline",
        size_hint=(None, None),
        size=(dp(24), dp(24)),
        pos_hint={"center_x": 0.5},
        md_bg_color=(1, 1, 1, 0),
        text_color=(0, 0, 0, 1)
    )
    nav_item2_icon.bind(on_press=lambda x: switch_page(app_instance, "log"))
    nav_item2_text = MDLabel(
        text="日志",
        font_size=dp(12),
        font_name="CustomChinese",
        halign="center",
        color=(0, 0, 0, 1)
    )
    nav_item2.add_widget(nav_item2_icon)
    nav_item2.add_widget(nav_item2_text)

    # 3. 个人中心导航项
    nav_item3 = MDBoxLayout(
        orientation="vertical",
        size_hint_x=1,
        spacing=dp(2),
        pos_hint={"center_x": 0.5, "center_y": 0.5}
    )
    nav_item3_icon = MDIconButton(
        icon="account-circle",
        size_hint=(None, None),
        size=(dp(24), dp(24)),
        pos_hint={"center_x": 0.5},
        md_bg_color=(1, 1, 1, 0),
        text_color=(0, 0, 0, 1)
    )
    nav_item3_icon.bind(on_press=lambda x: switch_page(app_instance, "me"))
    nav_item3_text = MDLabel(
        text="我",
        font_size=dp(12),
        font_name="CustomChinese",
        halign="center",
        color=(0, 0, 0, 1)
    )
    nav_item3.add_widget(nav_item3_icon)
    nav_item3.add_widget(nav_item3_text)

    bottom_nav_bar.add_widget(nav_item1)
    bottom_nav_bar.add_widget(nav_item2)
    bottom_nav_bar.add_widget(nav_item3)
    main_container.add_widget(bottom_nav_bar)

    add_global_log("✅ APP UI初始化完成")
    return main_container