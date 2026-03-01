import paho.mqtt.client as mqtt
from threading import Thread
import json
import time
import ssl
from kivy.clock import Clock

class Esp32MqttClient:
    def __init__(self, broker, port, username, password, data_callback):
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        self.data_callback = data_callback
        self.mqtt_client = None
        self.mqtt_thread = None
        self.connected = False
        self.parsed_data_callback = None
        self.latest_data = {}

    def set_parsed_data_callback(self, callback):
        self.parsed_data_callback = callback

    def init_mqtt_client(self):
        """初始化MQTT客户端（核心：修复TLS配置）"""
        # 1. 创建客户端（增加client_id避免重复连接）
        self.mqtt_client = mqtt.Client(client_id=f"esp32_android_{int(time.time())}")
        self.mqtt_client.username_pw_set(self.username, self.password)
        
        # 2. 关键修复：跳过TLS证书校验（适配测试服务器）
        context = ssl.create_default_context()
        context.check_hostname = False  # 关闭主机名校验
        context.verify_mode = ssl.CERT_NONE  # 跳过证书验证
        self.mqtt_client.tls_set_context(context)
        
        # 3. 缩短超时时间（适配手机网络）
        self.mqtt_client.connect_timeout = 10
        
        # 4. 绑定回调
        self.mqtt_client.on_connect = self._on_connect
        self.mqtt_client.on_message = self._on_message
        self.mqtt_client.on_disconnect = self._on_disconnect

    def start_mqtt(self):
        """启动MQTT（增加异常捕获）"""
        if self.mqtt_thread and self.mqtt_thread.is_alive():
            try:
                from app_ui_pages import add_global_log
                add_global_log("⚠️ MQTT线程已在运行")
            except ImportError:
                pass
            self.data_callback("⚠️ MQTT线程已在运行")
            return
        try:
            self.init_mqtt_client()
            self.mqtt_thread = Thread(target=self._mqtt_loop, daemon=True)
            self.mqtt_thread.start()
            try:
                from app_ui_pages import add_global_log
                add_global_log("📌 MQTT线程启动，开始连接服务器...")
            except ImportError:
                pass
            self.data_callback("📌 MQTT线程启动，开始连接服务器...")
        except Exception as e:
            error_msg = f"❌ 启动MQTT失败：{str(e)}"
            try:
                from app_ui_pages import add_global_log
                add_global_log(error_msg)
            except ImportError:
                pass
            self.data_callback(error_msg)

    def _on_connect(self, client, userdata, flags, rc):
        """连接回调（详细错误码说明）"""
        rc_msg = {
            0: "连接成功",
            1: "协议版本错误",
            2: "客户端ID无效",
            3: "服务器不可用",
            4: "用户名/密码错误",
            5: "未授权连接",
            6: "服务器忙",
            7: "连接超时"
        }
        if rc == 0:
            self.connected = True
            success_msg = f"✅ MQTT{rc_msg[rc]}，已进入稳定连接状态"
            try:
                from app_ui_pages import add_global_log
                add_global_log(success_msg)
            except ImportError:
                pass
            self.data_callback(success_msg)
            # 订阅主题
            client.subscribe("esp32/sensor", qos=0)
            client.subscribe("esp32/threshold_response", qos=0)
        else:
            self.connected = False
            error_msg = f"❌ MQTT连接失败：{rc_msg.get(rc, f'未知错误({rc})')}"
            try:
                from app_ui_pages import add_global_log
                add_global_log(error_msg)
            except ImportError:
                pass
            self.data_callback(error_msg)

    def _on_disconnect(self, client, userdata, rc):
        """断开连接回调（仅异常断开时重连）"""
        self.connected = False
        # 只有 rc != 0 时才是「异常断开」，才触发重连
        if rc != 0:
            error_msg = f"⚠️ MQTT意外断开（错误码{rc}），5秒后重连"
            try:
                from app_ui_pages import add_global_log
                add_global_log(error_msg)
            except ImportError:
                pass
            self.data_callback(error_msg)
            # 自动重连（仅异常断开时执行）
            Clock.schedule_once(lambda dt: self.start_mqtt(), 5)
        else:
            info_msg = "📌 MQTT正常断开连接，不触发重连"
            try:
                from app_ui_pages import add_global_log
                add_global_log(info_msg)
            except ImportError:
                pass
            self.data_callback(info_msg)

    def _on_message(self, client, userdata, msg):
        """消息接收回调"""
        try:
            # 解析原始消息
            topic = msg.topic
            payload = msg.payload.decode("utf-8")
            recv_msg = f"📥 [{topic}] {payload}"
            try:
                from app_ui_pages import add_global_log
                add_global_log(recv_msg)
            except ImportError:
                pass
            self.data_callback(recv_msg)

            # 解析传感器数据（JSON格式）
            if topic == "esp32/sensor":
                parsed_data = json.loads(payload)
                self.latest_data = parsed_data
                # 转发解析后的数据到UI（主线程）
                if self.parsed_data_callback:
                    Clock.schedule_once(lambda dt: self.parsed_data_callback(parsed_data))

        except json.JSONDecodeError:
            error_msg = f"❌ 数据格式错误：{payload}"
            try:
                from app_ui_pages import add_global_log
                add_global_log(error_msg)
            except ImportError:
                pass
            self.data_callback(error_msg)
        except Exception as e:
            error_msg = f"❌ 接收数据失败：{str(e)}"
            try:
                from app_ui_pages import add_global_log
                add_global_log(error_msg)
            except ImportError:
                pass
            self.data_callback(error_msg)

    def _mqtt_loop(self):
        """MQTT循环（连接成功后稳定运行，仅首次失败时重试）"""
        reconnect_count = 0
        max_retry = 15  # 仅首次连接失败时的重试次数
        connected_successfully = False  # 标记是否成功连接过

        while reconnect_count < max_retry and not connected_successfully:
            try:
                self.mqtt_client.connect(self.broker, self.port, 60)
                self.connected = True
                connected_successfully = True  # 标记为已成功连接
                success_msg = "✅ MQTT连接成功，进入稳定运行模式"
                try:
                    from app_ui_pages import add_global_log
                    add_global_log(success_msg)
                except ImportError:
                    pass
                # loop_forever：连接成功后持续运行，直到主动断开
                self.mqtt_client.loop_forever(retry_first_connection=True)
                break  # 正常断开后退出循环，不重试
            except ConnectionRefusedError:
                reconnect_count += 1
                error_msg = f"❌ 连接被拒绝（第{reconnect_count}/{max_retry}次）：请检查服务器地址/端口/账号密码"
                try:
                    from app_ui_pages import add_global_log
                    add_global_log(error_msg)
                except ImportError:
                    pass
                self.data_callback(error_msg)
            except TimeoutError:
                reconnect_count += 1
                error_msg = f"❌ 连接超时（第{reconnect_count}/{max_retry}次）：请检查手机网络/服务器是否在线"
                try:
                    from app_ui_pages import add_global_log
                    add_global_log(error_msg)
                except ImportError:
                    pass
                self.data_callback(error_msg)
            except ssl.SSLError:
                reconnect_count += 1
                error_msg = f"❌ TLS加密失败（第{reconnect_count}/{max_retry}次）：服务器可能未开启TLS"
                try:
                    from app_ui_pages import add_global_log
                    add_global_log(error_msg)
                except ImportError:
                    pass
                self.data_callback(error_msg)
            except Exception as e:
                reconnect_count += 1
                error_msg = f"❌ 连接失败（第{reconnect_count}/{max_retry}次）：{str(e)}"
                try:
                    from app_ui_pages import add_global_log
                    add_global_log(error_msg)
                except ImportError:
                    pass
                self.data_callback(error_msg)
            
            if reconnect_count < max_retry:
                time.sleep(5)  # 重试间隔5秒
        
        # 仅首次连接失败且达到最大次数时提示
        if not connected_successfully and reconnect_count >= max_retry:
            error_msg = "❌ 达到最大重连次数，请检查：\n1. 服务器地址/端口/账号密码\n2. 手机网络是否能访问服务器\n3. 服务器是否开启8883端口"
            try:
                from app_ui_pages import add_global_log
                add_global_log(error_msg)
            except ImportError:
                pass
            self.data_callback(error_msg)

    def publish_command(self, topic, command):
        """发布指令（增加空值保护）"""
        if not self.mqtt_client:
            error_msg = "❌ MQTT客户端未初始化"
            try:
                from app_ui_pages import add_global_log
                add_global_log(error_msg)
            except ImportError:
                pass
            self.data_callback(error_msg)
            return False
        if not self.connected:
            error_msg = "❌ MQTT未连接，无法发送指令"
            try:
                from app_ui_pages import add_global_log
                add_global_log(error_msg)
            except ImportError:
                pass
            self.data_callback(error_msg)
            return False
        try:
            result = self.mqtt_client.publish(topic, command, qos=0)
            result.wait_for_publish()
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                success_msg = f"📤 已发送：{command}"
                try:
                    from app_ui_pages import add_global_log
                    add_global_log(success_msg)
                except ImportError:
                    pass
                self.data_callback(success_msg)
                return True
            else:
                error_msg = f"❌ 发布失败（错误码{result.rc}）"
                try:
                    from app_ui_pages import add_global_log
                    add_global_log(error_msg)
                except ImportError:
                    pass
                self.data_callback(error_msg)
                return False
        except Exception as e:
            error_msg = f"❌ 发送指令失败：{str(e)}"
            try:
                from app_ui_pages import add_global_log
                add_global_log(error_msg)
            except ImportError:
                pass
            self.data_callback(error_msg)
            return False