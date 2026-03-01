# main.py：主运行文件，程序入口，整合UI、MQTT和业务逻辑
import kivy
kivy.require('2.2.1')  # 固定Kivy版本，避免兼容问题

from kivy.config import Config

# 全局变量：存储接收的数据（用于UI展示）
recv_data_list = []

# 配置手机端窗口（竖屏，适配手机分辨率）
Config.set('graphics', 'width', '360')   # 手机宽度
Config.set('graphics', 'height', '640')  # 手机高度
Config.set('graphics', 'resizable', False)  # 禁止缩放
Config.set('graphics', 'fullscreen', '0')   # 非全屏（测试用，发布可改1）

# 核心导入（按顺序，避免冲突）
from kivy.utils import platform
from kivymd.app import MDApp
from kivy.clock import Clock

# ========== 安卓权限申请（放在最前面，确保优先执行） ==========
if platform == 'android':
    from android.permissions import request_permissions, Permission, check_permission
    # 定义需要的权限
    REQUIRED_PERMISSIONS = [
        Permission.INTERNET,          # MQTT联网
        Permission.WRITE_EXTERNAL_STORAGE,  # 外部存储（备用）
        Permission.READ_EXTERNAL_STORAGE    # 外部存储（备用）
    ]
    
    # 申请权限（异步，避免阻塞启动）
    def request_app_permissions(*args):
        request_permissions(REQUIRED_PERMISSIONS, on_permissions_granted)
    
    def on_permissions_granted(permissions, grants):
        try:
            from app_ui_pages import init_db_if_not_exists
            init_db_if_not_exists()
            ...
        except Exception as e:
            print(f"权限授予后初始化数据库失败：{e}")

# ========== APP主类 ==========
class Esp32MobileApp(MDApp):
    def __init__(self,** kwargs):
        super().__init__(**kwargs)
        # MQTT服务器配置（替换为你的服务器信息）
        self.mqtt_config = {
            "broker": "iaa16ebf.ala.cn-hangzhou.emqxsl.cn",
            "port": 8883,
            "username": "esp32",
            "password": "123456"
        }
        # 初始化属性
        self.mqtt_client = None
        self.page_container = None  # 页面容器
        self.current_page = None    # 当前页面

    def build(self):
        """程序构建入口：先创建UI，再分步初始化"""
        self.title = "水质监控APP"  # 手机端标题栏
        
        # 延迟加载业务模块（避免启动时加载过重）
        from app_ui_pages import create_app_ui
        main_layout = create_app_ui(self)
        
        # 分步初始化（按优先级，避免闪退）
        if platform == 'android':
            try:
                from android import mActivity
                app_files_dir = mActivity.getApplicationContext().getFilesDir().getPath()
                db_path = os.path.join(app_files_dir, "sensor_data.db")
            except Exception as e:
                # fallback 或提示
                db_path = "sensor_data.db"
                from kivymd.toast import toast
                toast(f"数据库路径获取失败：{e}")
        else:
            # PC端：直接初始化数据库和MQTT
            try:
                from app_ui_pages import init_db_if_not_exists
                init_db_if_not_exists()
                Clock.schedule_once(lambda dt: self._init_mqtt_client(), 0.5)
            except Exception as e:
                print(f"PC端初始化失败：{e}")
        
        return main_layout

    def _init_mqtt_client(self):
        """初始化MQTT客户端（增加全量容错）"""
        try:
            # 延迟导入MQTT模块，避免启动时冲突
            from esp32_mqtt_utils import Esp32MqttClient
            from app_ui_pages import add_global_log
            
            self.mqtt_client = Esp32MqttClient(
                broker=self.mqtt_config["broker"],
                port=self.mqtt_config["port"],
                username=self.mqtt_config["username"],
                password=self.mqtt_config["password"],
                data_callback=self._update_recv_data
            )
            # MQTT启动失败不影响APP运行
            self.mqtt_client.start_mqtt()
            add_global_log("✅ MQTT客户端初始化完成")  # 写入全局日志
        except Exception as e:
            error_msg = f"❌ MQTT初始化失败：{str(e)}"
            # 容错：即使MQTT失败，也要写入日志，不崩溃
            try:
                from app_ui_pages import add_global_log
                add_global_log(error_msg)
                self._update_recv_data(error_msg)
            except:
                print(error_msg)  # 最低级容错：打印到控制台

    def _update_recv_data(self, content):
        """更新日志数据（线程安全+全量容错）"""
        try:
            # 1. 写入全局日志（手机日志页面可见）
            from app_ui_pages import add_global_log
            add_global_log(content)
            
            # 2. 原有逻辑：更新个人中心日志
            global recv_data_list
            recv_data_list.append(content)
            # 限制日志条数，避免内存溢出
            if len(recv_data_list) > 20:
                recv_data_list = recv_data_list[-20:]
            
            # 更新个人中心的日志显示（增加多层判空）
            if hasattr(self, 'current_page') and self.current_page:
                for child in self.current_page.walk():
                    if hasattr(child, 'is_log_label') and child.is_log_label:
                        child.text = "\n".join(recv_data_list) + "\n"
                        # 自动滚动到最新日志（判空）
                        if child.parent and hasattr(child.parent, 'scroll_y'):
                            child.parent.scroll_y = 0

            # 更新个人中心连接状态（容错）
            if any(keyword in content for keyword in ["MQTT连接成功", "MQTT连接失败", "连接异常"]):
                self.update_me_page_status()
        except Exception as e:
            print(f"更新日志失败：{e}")  # 容错：不崩溃

    def update_me_page_status(self):
        """更新个人中心的连接状态（增加容错）"""
        try:
            if not hasattr(self, 'current_page'):
                return
            # 检查是否在个人中心页面（判空）
            page_texts = []
            for child in self.current_page.children:
                if hasattr(child, 'text'):
                    page_texts.append(child.text)
            if "我的个人中心" in page_texts:
                from app_ui_pages import create_me_page
                if hasattr(self, 'page_container') and self.page_container:
                    self.page_container.clear_widgets()
                    self.current_page = create_me_page(self)
                    self.page_container.add_widget(self.current_page)
        except Exception as e:
            print(f"更新个人中心状态失败：{e}")

if __name__ == "__main__":
    """程序入口：启动APP主循环（增加容错）"""
    try:
        Esp32MobileApp().run()
    except Exception as e:
        print(f"APP启动失败：{e}")
        # 安卓端闪退时，用toast提示（最后一道防线）
        if platform == 'android':
            from kivymd.toast import toast
            toast(f"启动失败：{str(e)[:20]}")