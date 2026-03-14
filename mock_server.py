from http.server import BaseHTTPRequestHandler, HTTPServer
import json

class MockWebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/webhook':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            payload = json.loads(post_data.decode('utf-8'))
            
            print("\n" + "="*50)
            print("RECEIVED MOCK WEBHOOK")
            print("="*50)
            print(f"Symbol: {payload.get('symbol')}")
            print(f"Direction: {payload.get('direction')}")
            print(f"Entry: {payload.get('entry')}")
            print(f"Stop: {payload.get('stop')}")
            print(f"Target: {payload.get('target')}")
            print("="*50 + "\n")
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "received"}).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

if __name__ == '__main__':
    server_address = ('', 8000)
    httpd = HTTPServer(server_address, MockWebhookHandler)
    print("Mock Webhook Server running on port 8000...")
    httpd.serve_forever()
