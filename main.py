# 全局初始化数据库（APP启动时就执行，确保表存在）
import os
import sqlite3
from kivy.utils import platform

# 适配安卓/电脑的数据库路径
def get_db_path():
    if platform == 'android':
        # 安卓私有目录（无需权限，不会被系统清理）
        from android import mActivity
        app_dir = mActivity.getApplicationContext().getFilesDir().getPath()
        db_path = os.path.join(app_dir, "sensor_data.db")
    else:
        # 电脑端路径
        db_path = os.path.join(os.path.dirname(__file__), "sensor_data.db")
    # 确保目录存在
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return db_path

# 初始化数据库（APP启动时执行，强制创建表）
def init_db():
    try:
        conn = sqlite3.connect(get_db_path(), timeout=10)
        cursor = conn.cursor()
        # 强制创建sensor_records表（不存在则创建，存在则不修改）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sensor_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_date TEXT,
                record_time TEXT,
                do_value REAL,
                ph_value REAL,
                temp_value REAL
            )
        ''')
        conn.commit()
        conn.close()
        print("数据库初始化成功，表sensor_records已创建")
    except Exception as e:
        print(f"数据库初始化失败：{str(e)}")

# APP启动时立刻执行初始化（关键！）
init_db()

# 修复后的查询函数（带异常处理+主线程更新UI）
def query_sensor_data_by_date(date_type="today", callback=None):
    from threading import Thread
    from kivy.clock import mainthread
    import datetime

    def _query_task():
        try:
            # 再次确认表存在（双重保险）
            init_db()
            
            # 计算目标日期
            today = datetime.datetime.now().strftime("%Y-%m-%d")
            yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
            target_date = today if date_type == "today" else yesterday

            # 数据库查询
            conn = sqlite3.connect(get_db_path(), timeout=10)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT record_time, do_value, ph_value, temp_value
                FROM sensor_records
                WHERE record_date = ?
                ORDER BY record_time DESC
            ''', (target_date,))
            records = cursor.fetchall()
            conn.close()

            # 格式化数据
            display_data = []
            for record in records:
                time_str, do, ph, temp = record
                display_str = f"{time_str}: 溶解氧{round(do,2)}mg/L | PH{round(ph,1)} | 温度{round(temp,1)}℃"
                display_data.append(display_str)

            # 主线程更新UI（避免闪退）
            @mainthread
            def _update_ui():
                if callback:
                    callback(display_data, target_date)
            _update_ui()

        except Exception as e:
            # 异常提示（主线程）
            @mainthread
            def _show_error():
                from kivymd.toast import toast
                toast(f"查询失败：{str(e)}")
                if callback:
                    callback([f"查询错误：{str(e)}"], "")
            _show_error()
    
    # 启动子线程查询
    Thread(target=_query_task, daemon=True).start()

# 历史数据页面刷新函数（调用示例）
def refresh_history_ui(date_type="today"):
    # 假设你的滚动容器是scroll_content（根据你的UI调整）
    from kivymd.uix.label import MDLabel
    from kivy.metrics import dp

    # 清空旧内容，显示加载中
    scroll_content.clear_widgets()
    loading_label = MDLabel(
        text="加载中...", 
        font_size=dp(16), 
        halign="center", 
        size_hint_y=None, 
        height=dp(40)
    )
    scroll_content.add_widget(loading_label)
    
    # 定义回调函数（更新UI）
    def _on_query_finish(display_data, target_date):
        scroll_content.clear_widgets()
        if not display_data:
            display_data = [f"{target_date} 暂无传感器数据"]
        for idx, data in enumerate(display_data):
            data_label = MDLabel(
                text=data, 
                font_size=dp(16), 
                halign="left", 
                size_hint_y=None, 
                height=dp(40),
                theme_text_color="Custom", 
                text_color=(0.2,0.2,0.2,1) if idx !=0 else (0.8,0,0,1)
            )
            scroll_content.add_widget(data_label)
    
    # 调用查询函数
    query_sensor_data_by_date(date_type, _on_query_finish)
