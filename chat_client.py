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
from PyQt6.QtGui import QPixmap, QImage, QFont, QAction, QDesktopServices
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
    update_group_picture_signal = pyqtSignal(bytes, str)  # New signal for group picture updates

class ChatClient(QMainWindow):
    def __init__(self):
        super().__init__()
        self.channel = self.stub = self.username = self.server_ip = None
        self.running = False
        self.messages_to_send = []
        self.profile_picture_data = None
        self.video_players = []
        self.image_windows = []  # Store image viewer windows
        self.signal_handler = SignalHandler()
        self.signal_handler.add_message_signal.connect(self.create_message_bubble)
        self.signal_handler.system_message_signal.connect(self.create_system_message)
        self.signal_handler.update_group_picture_signal.connect(self.update_group_picture)  # Connect new signal
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
        filepath, _ = QFileDialog.getOpenFileName(self, "Select group picture", "", "Images (*.png *.jpg *.jpeg *.gif)")
        if not filepath:
            return
        image = Image.open(filepath).resize((46, 46))
        mask = Image.new('L', (46, 46), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, 46, 46), fill=255)
        image.putalpha(mask)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        self.profile_picture_data = buffer.getvalue()
        
        # Update local profile picture immediately
        qimage = QImage.fromData(self.profile_picture_data)
        self.profile_label.setPixmap(QPixmap.fromImage(qimage).scaled(50, 50, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        
        # Send group picture update to all users
        self.messages_to_send.append({
            "media_data": self.profile_picture_data, 
            "media_type": "group_picture_update",
            "filename": "group_picture_update"
        })
        
        # Show system message about the update
        self.signal_handler.system_message_signal.emit(f"{self.username} updated the group picture")

    def update_group_picture(self, picture_data, username):
        """Update the group picture for all users"""
        if picture_data:
            self.profile_picture_data = picture_data
            qimage = QImage.fromData(picture_data)
            self.profile_label.setPixmap(QPixmap.fromImage(qimage).scaled(50, 50, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def process_hd_image(self, filepath):
        """Process image to maintain HD quality while optimizing for transmission"""
        try:
            # Open the original image
            with Image.open(filepath) as img:
                # Convert to RGB if necessary (for JPEG compatibility)
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')
                
                # Get original dimensions
                original_width, original_height = img.size
                
                # Define maximum dimensions for HD quality (adjust as needed)
                MAX_HD_SIZE = 2048  # 2K resolution
                
                # Only resize if image is larger than MAX_HD_SIZE
                if max(original_width, original_height) > MAX_HD_SIZE:
                    # Calculate new dimensions maintaining aspect ratio
                    if original_width > original_height:
                        new_width = MAX_HD_SIZE
                        new_height = int((original_height * MAX_HD_SIZE) / original_width)
                    else:
                        new_height = MAX_HD_SIZE
                        new_width = int((original_width * MAX_HD_SIZE) / original_height)
                    
                    # Resize with high quality algorithm
                    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # Save with high quality settings
                buffer = io.BytesIO()
                
                # Determine optimal format and quality
                ext = filepath.split('.')[-1].lower()
                if ext in ['jpg', 'jpeg']:
                    img.save(buffer, format='JPEG', quality=95, optimize=True)
                elif ext == 'png':
                    img.save(buffer, format='PNG', optimize=True, compress_level=6)
                else:
                    # Default to PNG for other formats
                    img.save(buffer, format='PNG', optimize=True, compress_level=6)
                
                return buffer.getvalue()
                
        except Exception as e:
            print(f"Error processing HD image: {e}")
            # Fallback to original file data
            with open(filepath, "rb") as f:
                return f.read()

    def select_media(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Select file", "", "All Files (*)")
        if not filepath:
            return
        file_size = os.path.getsize(filepath)
        if file_size > MAX_FILE_SIZE:
            QMessageBox.warning(self, "File Too Large", "The selected file exceeds 100 MB limit.")
            return
        try:
            filename = os.path.basename(filepath)
            ext = filename.split('.')[-1].lower()
            
            # Determine media type
            if ext in ["png", "jpg", "jpeg", "gif", "bmp", "tiff"]:
                media_type = f"image/{ext}"
                # Process image for HD quality
                media_data = self.process_hd_image(filepath)
            elif ext in ["mp4", "avi", "mov", "mkv", "webm"]:
                media_type = f"video/{ext}"
                # Keep video files as-is
                with open(filepath, "rb") as f:
                    media_data = f.read()
            else:
                media_type = f"application/{ext}"
                # Keep other files as-is
                with open(filepath, "rb") as f:
                    media_data = f.read()
            
            # Check processed file size
            if len(media_data) > MAX_FILE_SIZE:
                QMessageBox.warning(self, "File Too Large", "The processed file still exceeds 100 MB limit.")
                return
                
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
                
                # Handle group picture updates
                if response.media_type == "group_picture_update":
                    if response.username != self.username:  # Only update if it's from someone else
                        self.signal_handler.update_group_picture_signal.emit(response.media_data, response.username)
                        self.signal_handler.system_message_signal.emit(f"{response.username} updated the group picture")
                    continue
                
                # Skip own messages for regular chat
                if response.username == self.username:
                    continue
                    
                self.signal_handler.add_message_signal.emit(
                    response.message, False, timestamp,
                    response.media_data, response.media_type, response.username
                )
                self.play_notification_sound()
        except grpc.RpcError as e:
            QMessageBox.critical(self, "Disconnected", f"Lost connection to server:\n{e}")
            self.signal_handler.system_message_signal.emit("Disconnected from server.")

    def show_full_image(self, image_data, filename):
        """Display full-size HD image in a new window"""
        try:
            full_image_window = QWidget()
            full_image_window.setWindowTitle(f"Full Image - {filename}")
            full_image_window.setStyleSheet("background-color: #1f2937;")
            
            layout = QVBoxLayout(full_image_window)
            
            # Create scroll area for large images
            scroll_area = QScrollArea()
            scroll_area.setWidgetResizable(True)
            
            # Create image label
            image_label = QLabel()
            qimage = QImage.fromData(image_data)
            pixmap = QPixmap.fromImage(qimage)  # Full resolution, no scaling
            image_label.setPixmap(pixmap)
            image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            scroll_area.setWidget(image_label)
            layout.addWidget(scroll_area)
            
            # Add close button
            close_btn = QPushButton("Close")
            close_btn.setStyleSheet("background-color: #10b981; color: white; padding: 10px;")
            close_btn.clicked.connect(full_image_window.close)
            layout.addWidget(close_btn)
            
            # Set window size (but not larger than screen)
            screen_geometry = QApplication.primaryScreen().geometry()
            window_width = min(pixmap.width() + 50, screen_geometry.width() - 100)
            window_height = min(pixmap.height() + 100, screen_geometry.height() - 100)
            
            full_image_window.resize(window_width, window_height)
            full_image_window.show()
            
            # Store reference to prevent garbage collection
            self.image_windows.append(full_image_window)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to display full image: {e}")

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
            
            # Calculate display size while maintaining HD quality
            original_size = qimage.size()
            display_width = min(600, original_size.width())  # Max display width
            display_height = min(600, original_size.height())  # Max display height
            
            # Maintain aspect ratio
            if original_size.width() > original_size.height():
                if original_size.width() > display_width:
                    display_height = int((original_size.height() * display_width) / original_size.width())
                else:
                    display_width = original_size.width()
                    display_height = original_size.height()
            else:
                if original_size.height() > display_height:
                    display_width = int((original_size.width() * display_height) / original_size.height())
                else:
                    display_width = original_size.width()
                    display_height = original_size.height()
            
            # Create high-quality scaled pixmap
            pixmap = QPixmap.fromImage(qimage).scaled(
                display_width, 
                display_height, 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            )
            
            img_label = QLabel()
            img_label.setPixmap(pixmap)
            img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            # Make image clickable to view full size
            def view_full_image():
                self.show_full_image(media_data, text)
            
            img_label.mousePressEvent = lambda event: view_full_image()
            img_label.setStyleSheet("border: 1px solid #555; cursor: pointer;")
            bubble_layout.addWidget(img_label)

        elif media_data and media_type and media_type.startswith("application/"):
            file_label = QLabel(f"{username} sent a file: {text}")
            file_label.setStyleSheet("color: white;")
            bubble_layout.addWidget(file_label)

            open_btn = QPushButton("Open File")
            def open_file_direct():
                path = f"temp_file_{time.time()}_{text}"
                with open(path, "wb") as f:
                    f.write(media_data)
                    QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            open_btn.clicked.connect(open_file_direct)
            bubble_layout.addWidget(open_btn)

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

if __name__ == "__main__":
    app = QApplication(sys.argv)
    client = ChatClient()
    sys.exit(app.exec())