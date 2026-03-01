# ui_utils.py 完整代码
from kivymd.uix.label import MDLabel
from kivy.uix.button import ButtonBehavior
from kivy.core.text import LabelBase
from kivy.metrics import dp
from kivy.clock import Clock

# 自定义无边界按钮（彻底修复canvas为空问题）
class NoBorderButton(ButtonBehavior, MDLabel):
    def __init__(self, **kwargs):
        # 1. 强制移除kwargs中的md_bg_color/text_color，避免初始化触发回调
        kwargs.pop("md_bg_color", None)
        kwargs.pop("text_color", None)
        self.button_type = kwargs.pop("button_type", "normal")
        
        # 2. 先执行父类初始化（必须先做，否则canvas永远为空）
        super().__init__(**kwargs)
        
        # 3. 基础属性设置（不涉及canvas）
        self.font_name = "CustomChinese"
        self.halign = "center"
        self.valign = "middle"
        self.font_size = dp(16)
        self.is_disabled = False

        # 4. 颜色配置初始化（仅存数据，不设置属性）
        if self.button_type == "switch":
            self.state_colors = {
                "关": {"bg": (0.8, 0.8, 0.8, 1), "text": (0, 0, 0, 1)},
                "开": {"bg": (0.8, 0.2, 0.2, 1), "text": (1, 1, 1, 1)}
            }
            self.current_state = "关"
        else:
            # 新增：默认颜色（可通过set_button_colors手动设置）
            self.custom_bg_color = (0.8, 0.8, 0.8, 1)
            self.custom_text_color = (0, 0, 0, 1)
            self.pressed_colors = {"bg": (0.2, 0.5, 0.8, 1), "text": (1, 1, 1, 1)}
            self.is_pressed = False

        # 5. 延迟2帧执行（确保canvas完全初始化）
        Clock.schedule_once(self._init_colors, 0.01)

    def _init_colors(self, *args):
        """延迟初始化颜色（此时canvas已存在）"""
        self.update_button_colors()

    def set_button_colors(self, bg_color, text_color):
        """手动设置按钮颜色（安全封装）"""
        if not hasattr(self, 'canvas') or self.canvas is None:
            # 若canvas未初始化，先缓存颜色，等待_init_colors执行
            self.custom_bg_color = bg_color
            self.custom_text_color = text_color
            return
        # 安全设置颜色
        self.md_bg_color = bg_color
        self.text_color = text_color

    def update_button_colors(self):
        """安全更新颜色（增加多层判空）"""
        # 双重判空：确保canvas和remove_group方法都存在
        if not hasattr(self, 'canvas') or self.canvas is None:
            return
        if not hasattr(self.canvas, 'remove_group'):
            return

        if self.is_disabled:
            self.md_bg_color = (0.9, 0.9, 0.9, 1)
            self.text_color = (0.5, 0.5, 0.5, 1)
            self.disabled = True
        else:
            if self.button_type == "switch":
                self.md_bg_color = self.state_colors[self.current_state]["bg"]
                self.text_color = self.state_colors[self.current_state]["text"]
            else:
                if self.is_pressed:
                    self.md_bg_color = self.pressed_colors["bg"]
                    self.text_color = self.pressed_colors["text"]
                else:
                    # 使用自定义默认颜色
                    self.md_bg_color = self.custom_bg_color
                    self.text_color = self.custom_text_color
            self.disabled = False

    def reset_button_state(self):
        """重置按钮状态（延迟执行）"""
        if self.button_type != "switch":
            self.is_pressed = False
            Clock.schedule_once(lambda dt: self.update_button_colors(), 0.01)

# 注册中文字体
def register_chinese_font():
    LabelBase.register(
        name="CustomChinese",
        fn_regular="Font_0.ttf"  # 替换为你的中文字体文件
    )

# ui_utils.py 中的 switch_page 函数完整修复版
def switch_page(app_instance, page_name):
    from app_ui_pages import create_home_page, create_me_page, create_history_page, create_log_page
    from app_ui_pages import unregister_history_callback, HISTORY_UPDATE_CALLBACKS
    
    # 清理历史页面回调（关键修复：增加方法存在性判断）
    if hasattr(app_instance, 'current_page') and app_instance.current_page:
        # 只对有 update_history_ui 方法的页面（历史数据页）执行注销
        if hasattr(app_instance.current_page, 'update_history_ui'):
            unregister_history_callback(app_instance.current_page.update_history_ui)
        # 额外防护：也可以通过页面特征判断（比如包含"设备历史数据"文本）
        # page_texts = [child.text for child in app_instance.current_page.children if hasattr(child, 'text')]
        # if "设备历史数据" in page_texts and hasattr(app_instance.current_page, 'update_history_ui'):
        #     unregister_history_callback(app_instance.current_page.update_history_ui)
    
    # 切换页面逻辑
    if hasattr(app_instance, 'page_container'):
        app_instance.page_container.clear_widgets()
        if page_name == "home":
            app_instance.current_page = create_home_page(app_instance)
        elif page_name == "me":
            app_instance.current_page = create_me_page(app_instance)
        elif page_name == "history":
            app_instance.current_page = create_history_page(app_instance)
        elif page_name == "log":
            app_instance.current_page = create_log_page(app_instance)
        app_instance.page_container.add_widget(app_instance.current_page)