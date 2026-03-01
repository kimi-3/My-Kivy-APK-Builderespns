# -*- coding: utf-8 -*-
import os
import sys
import sqlite3
import datetime
import threading
from kivy.utils import platform
from kivy.clock import Clock, mainthread
from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDRaisedButton
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.boxlayout import MDBoxLayout
from kivy.metrics import dp
from kivymd.toast import toast

# -------------------------- 全局配置 & 数据库核心（防闪退）--------------------------
# 数据库初始化标记
DB_INITIALIZED = False
# 数据库锁（避免多线程冲突）
DB_LOCK = threading.Lock()

def get_db_path():
    """适配安卓/电脑的数据库路径，安全获取"""
    try:
        if platform == 'android':
            # 安卓私有目录（无需权限，绝对安全）
            from android import mActivity
            app_files_dir = mActivity.getApplicationContext().getFilesDir().getAbsolutePath()
            db_path = os.path.join(app_files_dir, "sensor_data.db")
        else:
            # 电脑端路径
            db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sensor_data.db")
        
        # 确保目录存在
        db_dir = os.path.dirname(db_path)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        print(f"✅ 数据库路径：{db_path}")
        return db_path
    except Exception as e:
        print(f"❌ 获取数据库路径失败：{str(e)}")
        return None

def init_database():
    """强制初始化数据库，确保表存在（带锁）"""
    global DB_INITIALIZED
    with DB_LOCK:
        if DB_INITIALIZED:
            return True
        
        db_path = get_db_path()
        if not db_path:
            return False
        
        try:
            conn = sqlite3.connect(db_path, timeout=15)
            cursor = conn.cursor()
            # 强制创建表（不存在则创建，存在则不修改）
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sensor_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    record_date TEXT NOT NULL,
                    record_time TEXT NOT NULL,
                    do_value REAL,
                    ph_value REAL,
                    temp_value REAL
                )
            ''')
            conn.commit()
            conn.close()
            DB_INITIALIZED = True
            print("✅ 数据库表 sensor_records 创建/验证成功")
            return True
        except Exception as e:
            print(f"❌ 初始化数据库失败：{str(e)}")
            return False

# -------------------------- 安全的数据库查询函数 --------------------------
def query_sensor_data(date_type="today"):
    """查询指定日期数据，返回格式化结果"""
    if not DB_INITIALIZED:
        if not init_database():
            return ["数据库初始化失败，无法查询"]
    
    try:
        # 计算目标日期
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        target_date = today if date_type == "today" else yesterday

        # 数据库查询（带锁）
        with DB_LOCK:
            conn = sqlite3.connect(get_db_path(), timeout=15)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT record_time, do_value, ph_value, temp_value
                FROM sensor_records
                WHERE record_date = ?
                ORDER BY record_time DESC
            ''', (target_date,))
            records = cursor.fetchall()
            conn.close()

        # 格式化结果
        if not records:
            return [f"{target_date} 暂无传感器数据"]
        
        result = [f"📊 {target_date} 数据列表"]
        for time_str, do, ph, temp in records:
            result.append(
                f"{time_str} | 溶解氧：{round(do,2)}mg/L | "
                f"PH值：{round(ph,1)} | 温度：{round(temp,1)}℃"
            )
        return result
    except Exception as e:
        return [f"查询失败：{str(e)}"]

# -------------------------- UI界面（极简稳定版）--------------------------
class WaterQualityApp(MDApp):
    def build(self):
        # 主屏幕
        self.screen = MDScreen()
        
        # 主布局（垂直）
        self.main_layout = MDBoxLayout(
            orientation="vertical",
            padding=dp(20),
            spacing=dp(15),
            size_hint=(1, 1)
        )
        
        # 标题
        title = MDLabel(
            text="水质监控系统",
            font_size=dp(22),
            halign="center",
            size_hint_y=None,
            height=dp(60)
        )
        self.main_layout.add_widget(title)
        
        # 按钮布局
        btn_layout = MDBoxLayout(
            orientation="horizontal",
            spacing=dp(10),
            size_hint_y=None,
            height=dp(50)
        )
        # 今日数据按钮
        btn_today = MDRaisedButton(
            text="今日数据",
            on_release=lambda x: self.load_data("today")
        )
        # 昨日数据按钮
        btn_yesterday = MDRaisedButton(
            text="昨日数据",
            on_release=lambda x: self.load_data("yesterday")
        )
        btn_layout.add_widget(btn_today)
        btn_layout.add_widget(btn_yesterday)
        self.main_layout.add_widget(btn_layout)
        
        # 数据显示区域（滚动）
        self.scroll_view = MDScrollView(size_hint=(1, 1))
        self.data_layout = MDBoxLayout(
            orientation="vertical",
            spacing=dp(8),
            size_hint_y=None
        )
        self.data_layout.bind(minimum_height=self.data_layout.setter('height'))
        self.scroll_view.add_widget(self.data_layout)
        self.main_layout.add_widget(self.scroll_view)
        
        # 初始提示
        self.show_initial_text()
        
        self.screen.add_widget(self.main_layout)
        return self.screen

    def on_start(self):
        """APP启动后执行（延迟初始化数据库，避免阻塞）"""
        Clock.schedule_once(lambda dt: self.init_db_safe(), 0.5)

    @mainthread
    def show_initial_text(self):
        """显示初始提示"""
        self.data_layout.clear_widgets()
        initial_label = MDLabel(
            text="点击按钮查看传感器数据",
            font_size=dp(16),
            halign="center",
            size_hint_y=None,
            height=dp(40)
        )
        self.data_layout.add_widget(initial_label)

    def init_db_safe(self):
        """安全初始化数据库（子线程执行）"""
        def _init_task():
            success = init_database()
            @mainthread
            def _notify():
                if success:
                    toast("数据库初始化成功")
                else:
                    toast("数据库初始化失败，但APP仍可使用")
            _notify()
        
        # 子线程执行，不阻塞UI
        threading.Thread(target=_init_task, daemon=True).start()

    def load_data(self, date_type):
        """加载指定日期数据（子线程执行，避免UI卡顿）"""
        # 显示加载中
        self.data_layout.clear_widgets()
        loading_label = MDLabel(
            text="加载中...",
            font_size=dp(16),
            halign="center",
            size_hint_y=None,
            height=dp(40)
        )
        self.data_layout.add_widget(loading_label)

        # 子线程查询数据
        def _load_task():
            data = query_sensor_data(date_type)
            # 主线程更新UI
            @mainthread
            def _update_ui():
                self.data_layout.clear_widgets()
                for line in data:
                    label = MDLabel(
                        text=line,
                        font_size=dp(15),
                        halign="left",
                        size_hint_y=None,
                        height=dp(35)
                    )
                    self.data_layout.add_widget(label)
            
            _update_ui()
        
        threading.Thread(target=_load_task, daemon=True).start()

# -------------------------- 启动APP --------------------------
if __name__ == "__main__":
    try:
        WaterQualityApp().run()
    except Exception as e:
        print(f"❌ APP启动异常：{str(e)}")
        # 捕获所有异常，避免直接闪退
        import traceback
        traceback.print_exc()
