import sys, os, io, time, platform, threading, grpc
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QLineEdit, QFileDialog, QScrollArea, QMainWindow
)
from PyQt6.QtGui import QPixmap, QImage, QFont
from PyQt6.QtCore import Qt, QCoreApplication, pyqtSignal, QObject
from PIL import Image, ImageDraw
import chat_pb2, chat_pb2_grpc

try:
    import winsound
except ImportError:
    winsound = None

class SignalHandler(QObject):
    add_message_signal = pyqtSignal(str, bool, str, bytes, str, str)
    system_message_signal = pyqtSignal(str)

class ChatClient(QMainWindow):
    def __init__(self):
        super().__init__()
        self.channel = self.stub = self.username = self.server_ip = None
        self.running = False
        self.messages_to_send = []
        self.profile_picture_data = None
        self.wraplength = 300
        self.signal_handler = SignalHandler()
        self.signal_handler.add_message_signal.connect(self.create_message_bubble)
        self.signal_handler.system_message_signal.connect(self.create_system_message)
        self.show_login_screen()

    def show_login_screen(self):
        self.login_window = QWidget()
        self.login_window.setWindowTitle("Login to Chat")
        self.login_window.setStyleSheet("background-color: #1f2937; color: white;")
        layout = QVBoxLayout()

        title = QLabel("Join Chat")
        title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")
        self.username_input.setStyleSheet("background-color: #374151; color: white; padding: 6px;")
        layout.addWidget(self.username_input)

        self.server_input = QLineEdit()
        self.server_input.setPlaceholderText("Server IP (e.g. localhost)")
        self.server_input.setStyleSheet("background-color: #374151; color: white; padding: 6px;")
        layout.addWidget(self.server_input)

        connect_btn = QPushButton("Connect")
        connect_btn.setStyleSheet("background-color: #10b981; color: white; padding: 10px;")
        connect_btn.clicked.connect(self.connect_to_server)
        layout.addWidget(connect_btn)

        self.login_window.setLayout(layout)
        self.login_window.setFixedSize(300, 200)
        self.login_window.show()

    def connect_to_server(self):
        self.username = self.username_input.text().strip()
        self.server_ip = self.server_input.text().strip()
        if not self.username or not self.server_ip:
            return
        try:
            self.channel = grpc.insecure_channel(f"{self.server_ip}:50051")
            grpc.channel_ready_future(self.channel).result(timeout=5)
            self.stub = chat_pb2_grpc.ChatServiceStub(self.channel)
            self.running = True
            self.login_window.close()
            self.build_chat_window()
        except Exception as e:
            print(f"Failed to connect: {e}")

    def build_chat_window(self):
        self.setWindowTitle(f"Chat - {self.username}")
        self.resize(500, 600)
        self.setStyleSheet("background-color: #0f172a; color: white;")

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        header = QHBoxLayout()
        self.profile_label = QLabel()
        self.profile_label.setFixedSize(50, 50)
        self.profile_label.setStyleSheet("background-color: #6b7280; border-radius: 25px;")
        self.profile_label.mousePressEvent = self.change_profile_picture
        header.addWidget(self.profile_label)

        title = QLabel("Group Chat")
        title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.chat_layout = QVBoxLayout(self.scroll_content)
        self.chat_layout.addStretch()
        self.scroll_area.setWidget(self.scroll_content)
        layout.addWidget(self.scroll_area)

        input_layout = QHBoxLayout()
        attach_btn = QPushButton("📎")
        attach_btn.clicked.connect(self.select_media)
        input_layout.addWidget(attach_btn)

        self.entry = QLineEdit()
        self.entry.setStyleSheet("background-color: #374151; color: white; padding: 6px;")
        self.entry.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.entry)

        send_btn = QPushButton("▶")
        send_btn.clicked.connect(self.send_message)
        input_layout.addWidget(send_btn)

        layout.addLayout(input_layout)

        self.show()
        threading.Thread(target=self.receive_messages, daemon=True).start()

    def update_bubble_wraplength(self):
        self.wraplength = int(self.width() * 0.6)

    def change_profile_picture(self, event=None):
        filepath, _ = QFileDialog.getOpenFileName(self, "Select profile picture", "", "Images (*.png *.jpg *.jpeg *.gif)")
        if not filepath:
            return
        image = Image.open(filepath).resize((46, 46))
        mask = Image.new('L', (46, 46), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, 46, 46), fill=255)
        image.putalpha(mask)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        self.profile_picture_data = buffer.getvalue()
        qimage = QImage.fromData(self.profile_picture_data)
        self.profile_label.setPixmap(QPixmap.fromImage(qimage).scaled(50, 50, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.messages_to_send.append({"type": "profile_update", "media_data": self.profile_picture_data, "media_type": "profile_picture"})

    def create_message_bubble(self, text, is_self=False, timestamp="", media_data=None, media_type=None, username=""):
        self.update_bubble_wraplength()
        bubble = QVBoxLayout()
        container = QWidget()
        container_layout = QVBoxLayout(container)

        bubble_widget = QWidget()
        bubble_layout = QVBoxLayout(bubble_widget)
        bubble_widget.setStyleSheet(f"background-color: {'#10b981' if is_self else '#374151'}; border-radius: 10px; padding: 6px;")
        bubble_layout.setContentsMargins(10, 5, 10, 5)

        if not is_self and username:
            label = QLabel(username)
            label.setFont(QFont("Arial", 9, QFont.Weight.Bold))
            bubble_layout.addWidget(label)

        if media_data and media_type and media_type.startswith("image/"):
            qimage = QImage.fromData(media_data)
            pixmap = QPixmap.fromImage(qimage).scaled(200, 200, Qt.AspectRatioMode.KeepAspectRatio)
            img_label = QLabel()
            img_label.setPixmap(pixmap)
            bubble_layout.addWidget(img_label)

        if text:
            msg = QLabel(text)
            msg.setWordWrap(True)
            msg.setStyleSheet("color: white;")
            bubble_layout.addWidget(msg)

        if timestamp:
            time_label = QLabel(timestamp)
            time_label.setAlignment(Qt.AlignmentFlag.AlignRight)
            time_label.setStyleSheet("color: gray; font-size: 9px;")
            bubble_layout.addWidget(time_label)

        container_layout.addWidget(bubble_widget)
        container.setLayout(container_layout)
        align = Qt.AlignmentFlag.AlignRight if is_self else Qt.AlignmentFlag.AlignLeft
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, container, alignment=align)
        QCoreApplication.processEvents()
        self.scroll_area.verticalScrollBar().setValue(self.scroll_area.verticalScrollBar().maximum())

    def create_system_message(self, text):
        label = QLabel(text)
        label.setStyleSheet("color: #9ca3af; background-color: #374151; padding: 4px;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, label)

    def message_generator(self):
        yield chat_pb2.ChatMessage(username=self.username, message="has joined the chat")
        while self.running:
            if self.messages_to_send:
                msg_obj = self.messages_to_send.pop(0)
                if isinstance(msg_obj, dict):
                    yield chat_pb2.ChatMessage(username=self.username, media_data=msg_obj['media_data'], media_type=msg_obj['media_type'])
                else:
                    yield chat_pb2.ChatMessage(username=self.username, message=msg_obj)
            else:
                time.sleep(0.1)

    def send_message(self):
        msg = self.entry.text().strip()
        if msg:
            self.entry.clear()
            timestamp = datetime.now().strftime("%H:%M")
            self.messages_to_send.append(msg)
            self.signal_handler.add_message_signal.emit(msg, True, timestamp, b"", "", "")

    def select_media(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Select media file", "", "Images (*.png *.jpg *.jpeg *.gif);;Videos (*.mp4 *.avi *.mov)")
        if not filepath:
            return
        with open(filepath, "rb") as f:
            media_data = f.read()
        ext = filepath.split('.')[-1].lower()
        media_type = f"image/{ext}" if ext in ["png", "jpg", "jpeg", "gif"] else f"video/{ext}"
        self.messages_to_send.append({"media_data": media_data, "media_type": media_type})
        timestamp = datetime.now().strftime("%H:%M")
        if media_type.startswith("image/"):
            self.signal_handler.add_message_signal.emit("", True, timestamp, media_data, media_type, "")
        else:
            self.signal_handler.add_message_signal.emit(f"📎 {media_type} file", True, timestamp, b"", "", "")

    def receive_messages(self):
        try:
            for response in self.stub.Chat(self.message_generator()):
                timestamp = datetime.now().strftime("%H:%M")
                if response.media_type == "profile_picture" and response.username != self.username:
                    continue
                if response.username == self.username:
                    continue
                if response.media_data and response.media_type != "profile_picture":
                    if response.media_type.startswith("image/"):
                        self.signal_handler.add_message_signal.emit("", False, timestamp, response.media_data, response.media_type, response.username)
                    else:
                        self.signal_handler.add_message_signal.emit(f"📎 {response.media_type} file", False, timestamp, b"", "", response.username)
                elif response.message == "has joined the chat":
                    self.signal_handler.system_message_signal.emit(f"{response.username} has joined the chat")
                elif response.message:
                    self.signal_handler.add_message_signal.emit(response.message, False, timestamp, b"", "", response.username)
                self.play_notification_sound()
        except grpc.RpcError:
            self.signal_handler.system_message_signal.emit("Disconnected from server.")

    def play_notification_sound(self):
        try:
            if platform.system() == "Windows" and winsound:
                winsound.MessageBeep()
            elif platform.system() == "Darwin":
                os.system("afplay /System/Library/Sounds/Glass.aiff")
            else:
                os.system("paplay /usr/share/sounds/freedesktop/stereo/message.oga")
        except:
            pass

    def closeEvent(self, event):
        self.running = False
        if self.channel:
            self.channel.close()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    client = ChatClient()
    sys.exit(app.exec())
