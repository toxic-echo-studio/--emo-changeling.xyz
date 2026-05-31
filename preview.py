import sys
import os
import http.server
import socket

# Ustawienie opcji wielokrotnego użycia gniazda portu w Windows
class ReuseAddressServer(http.server.ThreadingHTTPServer):
    def server_bind(self):
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        super().server_bind()

if len(sys.argv) < 3:
    print("Usage: python preview.py <directory> <port>")
    sys.exit(1)

directory = sys.argv[1]
port = int(sys.argv[2])

# Zmiana katalogu roboczego, aby serwować tylko dany moduł
os.chdir(directory)

handler = http.server.SimpleHTTPRequestHandler

print(f"Uruchamianie lokalnego podglądu dla modułu: {directory}")
print(f"Otwórz w przeglądarce: http://localhost:{port}")

try:
    with ReuseAddressServer(("", port), handler) as httpd:
        httpd.serve_forever()
except KeyboardInterrupt:
    print("\nSerwer zatrzymany.")
except Exception as e:
    print(f"Błąd uruchamiania serwera: {e}")
