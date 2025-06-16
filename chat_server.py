import grpc
from concurrent import futures
import threading
import time
import socket
import signal

import chat_pb2
import chat_pb2_grpc

# Store connected clients as a set of objects (we'll use a custom Client class)
clients_lock = threading.Lock()
connected_clients = set()

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

class Client:
    def __init__(self):
        self.messages = []
        self.condition = threading.Condition()

class ChatService(chat_pb2_grpc.ChatServiceServicer):

    def Chat(self, request_iterator, context):
        client = Client()

        # Add client to connected clients
        with clients_lock:
            connected_clients.add(client)

        def send_messages():
            while True:
                with client.condition:
                    while not client.messages:
                        client.condition.wait()
                    # Pop and yield one message at a time
                    msg = client.messages.pop(0)
                    yield msg

        def receive_messages():
            try:
                for chat_message in request_iterator:
                    # Broadcast to all connected clients
                    with clients_lock:
                        for c in connected_clients:
                            with c.condition:
                                c.messages.append(chat_message)
                                c.condition.notify()
            except Exception as e:
                print(f"Receive error: {e}")
            finally:
                # Remove client on disconnect
                with clients_lock:
                    connected_clients.remove(client)

        # Start receiving in separate thread
        threading.Thread(target=receive_messages, daemon=True).start()

        # Yield messages from send_messages generator
        yield from send_messages()


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    chat_pb2_grpc.add_ChatServiceServicer_to_server(ChatService(), server)
    server.add_insecure_port('0.0.0.0:50051')

    local_ip = get_local_ip()
    print(f"Starting gRPC chat server on {local_ip}:50051")
    print(f"Invite your friends with this IP: {local_ip}")

    server.start()

    # Graceful shutdown handler
    def shutdown_handler(signum, frame):
        print("\nServer stopping gracefully...")
        server.stop(0)
        exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    try:
        while True:
            time.sleep(86400)
    except KeyboardInterrupt:
        # fallback, should rarely reach here due to signal handler
        print("Server stopping...")
        server.stop(0)


if __name__ == '__main__':
    serve()