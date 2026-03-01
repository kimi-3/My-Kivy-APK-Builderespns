import sqlite3
import datetime
import os

def get_db_path():
    """获取数据库路径（兼容PC/手机）"""
    if os.name == 'nt':  # Windows
        return "sensor_data.db"
    else:  # Android
        from android.storage import app_storage_path
        return os.path.join(app_storage_path(), "sensor_data.db")

def init_db():
    """初始化数据库表"""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    # 创建传感器数据表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sensor_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_date TEXT,  # 日期（YYYY-MM-DD）
            record_time TEXT,  # 时间（YYYY-MM-DD HH:MM:SS）
            do_value REAL,     # 溶解氧
            ph_value REAL,     # PH值
            temp_value REAL    # 温度
        )
    ''')
    conn.commit()
    conn.close()

def insert_sensor_record(do_value, ph_value, temp_value):
    """插入传感器数据"""
    now = datetime.datetime.now()
    record_date = now.strftime("%Y-%m-%d")
    record_time = now.strftime("%Y-%m-%d %H:%M:%S")
    
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO sensor_records (record_date, record_time, do_value, ph_value, temp_value)
        VALUES (?, ?, ?, ?, ?)
    ''', (record_date, record_time, do_value, ph_value, temp_value))
    conn.commit()
    conn.close()

def query_records_by_date(date_type="today"):
    """查询今日/昨日数据"""
    # 计算目标日期
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    target_date = today if date_type == "today" else yesterday

    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    # 查询指定日期数据（按时间倒序）
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
    
    return display_data, target_date

def clean_expired_data():
    """清理今日/昨日之外的过期数据"""
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    # 删除非今日/昨日的数据
    cursor.execute('''
        DELETE FROM sensor_records
        WHERE record_date NOT IN (?, ?)
    ''', (today, yesterday))
    conn.commit()
    conn.close()