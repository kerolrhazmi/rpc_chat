# [1] ===== IMPORTS =====
from argparse import Action
import sys, os, io, time, platform, threading, grpc
from tkinter import Menu
from datetime import datetime
from PyQt6 import QtMultimedia 
from PyQt6.QtWidgets import (
    QApplication, QMenu, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QLineEdit, QFileDialog, QScrollArea, QMainWindow, QMessageBox
)
from PyQt6.QtGui import QPixmap, QImage, QFont, QAction 
from PyQt6.QtCore import Qt, QCoreApplication, pyqtSignal, QObject, QUrl, QTimer 
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PIL import Image, ImageDraw
import chat_pb2, chat_pb2_grpc

try:
    import winsound
except ImportError:
    winsound = None

MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB

class SignalHandler(QObject):
    add_message_signal = pyqtSignal(str, bool, str, bytes, str, str)
    system_message_signal = pyqtSignal(str)

class ChatClient(QMainWindow):
    def __init__(self):  # ✅ fixed __init__
        super().__init__()  # ✅ fixed __init__
        self.channel = self.stub = self.username = self.server_ip = None
        self.running = False
        self.messages_to_send = []
        self.profile_picture_data = None
        self.video_players = []
        self.signal_handler = SignalHandler()
        self.signal_handler.add_message_signal.connect(self.create_message_bubble)
        self.signal_handler.system_message_signal.connect(self.create_system_message)
        self.is_dark_mode = True
        self.show_login_screen()

    def apply_theme(self):
        if self.is_dark_mode:
            self.setStyleSheet("background-color: #0f172a; color: white;")
            self.entry.setStyleSheet("background-color: #374151; color: white; padding: 6px;")
        else:
            self.setStyleSheet("background-color: white; color: black;")
            self.entry.setStyleSheet("background-color: #f1f5f9; color: black; padding: 6px;")

    def toggle_theme(self):
        self.is_dark_mode = not self.is_dark_mode
        self.apply_theme()

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
            options = [('grpc.max_send_message_length', MAX_FILE_SIZE), ('grpc.max_receive_message_length', MAX_FILE_SIZE)]
            self.channel = grpc.insecure_channel(f"{self.server_ip}:50051", options=options)
            grpc.channel_ready_future(self.channel).result(timeout=5)
            self.stub = chat_pb2_grpc.ChatServiceStub(self.channel)
            self.running = True
            self.login_window.close()
            self.build_chat_window()
        except Exception as e:
            QMessageBox.critical(self, "Connection Failed", f"Failed to connect: {e}")

    def build_chat_window(self):
        self.setWindowTitle(f"Chat - {self.username}")
        self.resize(500, 600)
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

        theme_btn = QPushButton("☀" if not self.is_dark_mode else "🌙")
        theme_btn.setFixedSize(30, 30)
        theme_btn.clicked.connect(lambda: [self.toggle_theme(), theme_btn.setText("☀" if not self.is_dark_mode else "🌙")])
        header.addWidget(theme_btn)

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
        self.entry.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.entry)

        emoji_btn = QPushButton("😊")
        emoji_btn.clicked.connect(self.show_emoji_menu)
        input_layout.addWidget(emoji_btn)

        send_btn = QPushButton("▶")
        send_btn.clicked.connect(self.send_message)
        input_layout.addWidget(send_btn)

        layout.addLayout(input_layout)
        self.apply_theme()
        self.show()
        threading.Thread(target=self.receive_messages, daemon=True).start()

    def show_emoji_menu(self):
        menu = QMenu()
        emojis = ["😀", "😂", "😍", "👍", "🙏", "🔥", "❤", "🎉", "😎", "🤖"]
        for emoji in emojis:
            action = QAction(emoji, self)
            action.triggered.connect(lambda _, e=emoji: self.entry.insert(e))
            menu.addAction(action)
        menu.exec(self.mapToGlobal(self.sender().pos()))

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
        self.messages_to_send.append({"media_data": self.profile_picture_data, "media_type": "profile_picture"})

    def select_media(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Select file", "", "All Files (*)")
        if not filepath:
            return
        file_size = os.path.getsize(filepath)
        if file_size > MAX_FILE_SIZE:
            QMessageBox.warning(self, "File Too Large", "The selected file exceeds 100 MB limit.")
            return
        try:
            with open(filepath, "rb") as f:
                media_data = f.read()
                filename = os.path.basename(filepath)
                ext = filename.split('.')[-1].lower()
                media_type = (
                    f"image/{ext}" if ext in ["png", "jpg", "jpeg", "gif"] else
                    f"video/{ext}" if ext in ["mp4", "avi", "mov", "mkv"] else
                    f"application/{ext}"
                )
                self.messages_to_send.append({
                    "media_data": media_data,
                    "media_type": media_type,
                    "filename": filename
                })
                timestamp = datetime.now().strftime("%H:%M")
                self.signal_handler.add_message_signal.emit(
                    filename, True, timestamp, media_data, media_type, self.username
                )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to send media:\n{e}")

    def message_generator(self):
        yield chat_pb2.ChatMessage(username=self.username, message="has joined the chat")
        while self.running:
            if self.messages_to_send:
                msg_obj = self.messages_to_send.pop(0)
                if isinstance(msg_obj, dict):
                    yield chat_pb2.ChatMessage(
                        username=self.username,
                        message=msg_obj.get("filename", ""),
                        media_data=msg_obj.get("media_data", b""),
                        media_type=msg_obj.get("media_type", "")
                    )
                else:
                    yield chat_pb2.ChatMessage(username=self.username, message=msg_obj)
            else:
                time.sleep(0.05)

    def send_message(self):
        msg = self.entry.text().strip()
        if msg:
            self.entry.clear()
            timestamp = datetime.now().strftime("%H:%M")
            self.messages_to_send.append(msg)
            self.signal_handler.add_message_signal.emit(msg, True, timestamp, b"", "", self.username)

    def receive_messages(self):
        try:
            for response in self.stub.Chat(self.message_generator()):
                timestamp = datetime.now().strftime("%H:%M")
                if response.username == self.username or response.media_type == "profile_picture":
                    continue
                self.signal_handler.add_message_signal.emit(
                    response.message, False, timestamp,
                    response.media_data, response.media_type, response.username
                )
                self.play_notification_sound()
        except grpc.RpcError as e:
            QMessageBox.critical(self, "Disconnected", f"Lost connection to server:\n{e}")
            self.signal_handler.system_message_signal.emit("Disconnected from server.")

    def create_message_bubble(self, text, is_self=False, timestamp="", media_data=None, media_type=None, username=""):
        container = QWidget()
        container_layout = QVBoxLayout(container)
        bubble_widget = QWidget()
        bubble_layout = QVBoxLayout(bubble_widget)
        bubble_widget.setStyleSheet(f"background-color: {'#10b981' if is_self else '#374151'}; border-radius: 10px; padding: 6px;")
        bubble_layout.setContentsMargins(10, 5, 10, 5)

        if not is_self and username:
            user_label = QLabel(username)
            user_label.setFont(QFont("Arial", 9, QFont.Weight.Bold))
            bubble_layout.addWidget(user_label)

        if media_data and media_type and media_type.startswith("video/"):
            video_path = f"temp_{time.time()}.mp4"
            with open(video_path, "wb") as f:
                f.write(media_data)
            video_widget = QVideoWidget()
            video_widget.setMinimumSize(300, 200)
            player = QMediaPlayer(self)
            audio = QAudioOutput(self)
            player.setVideoOutput(video_widget)
            player.setAudioOutput(audio)
            player.setSource(QUrl.fromLocalFile(video_path))

            def on_media_status_changed(status):
                if status == QMediaPlayer.MediaStatus.EndOfMedia:
                    player.setPosition(0)

            player.mediaStatusChanged.connect(on_media_status_changed)

            if not is_self:
                player.play()

            self.video_players.append(player)
            bubble_layout.addWidget(video_widget)

            control_layout = QHBoxLayout()
            replay_btn = QPushButton("Replay")
            replay_btn.clicked.connect(lambda: player.setPosition(0))
            control_layout.addWidget(replay_btn)
            pause_btn = QPushButton("Pause")
            pause_btn.clicked.connect(lambda: player.pause() if player.playbackState() == QMediaPlayer.PlaybackState.PlayingState else player.play())
            control_layout.addWidget(pause_btn)
            bubble_layout.addLayout(control_layout)

        elif media_data and media_type and media_type.startswith("image/"):
            qimage = QImage.fromData(media_data)
            pixmap = QPixmap.fromImage(qimage).scaled(400, 400, Qt.AspectRatioMode.KeepAspectRatio)
            img_label = QLabel()
            img_label.setPixmap(pixmap)
            bubble_layout.addWidget(img_label)

        elif text and not media_data:
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
        align = Qt.AlignmentFlag.AlignRight if is_self else Qt.AlignmentFlag.AlignLeft
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, container, alignment=align)
        QCoreApplication.processEvents()
        QTimer.singleShot(0, lambda: self.scroll_area.verticalScrollBar().setValue(
        self.scroll_area.verticalScrollBar().maximum()))

    def create_system_message(self, text):
        label = QLabel(text)
        label.setStyleSheet("color: #9ca3af; background-color: #374151; padding: 4px;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, label)

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

if __name__ == "__main__":  # ✅ Correct main check
    app = QApplication(sys.argv)
    client = ChatClient()
    sys.exit(app.exec())
