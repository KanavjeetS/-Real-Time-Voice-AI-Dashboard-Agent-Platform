#!/bin/bash
# ─────────────────────────────────────────────
#  AI Calling Agent — Local Dev Setup Script
#  Starts ngrok and updates TWILIO_WEBHOOK_BASE_URL in .env
# ─────────────────────────────────────────────

set -e

if ! command -v ngrok &> /dev/null; then
    echo "❌ ngrok not found. Install from https://ngrok.com/download"
    exit 1
fi

echo "🚀 Starting ngrok tunnel on port 8000..."
ngrok http 8000 &
NGROK_PID=$!
sleep 2

# Get the HTTPS URL from ngrok API
NGROK_URL=$(curl -s http://localhost:4040/api/tunnels | python3 -c "
import sys, json
data = json.load(sys.stdin)
for t in data['tunnels']:
    if t['proto'] == 'https':
        print(t['public_url'])
        break
")

if [ -z "$NGROK_URL" ]; then
    echo "❌ Could not get ngrok URL"
    kill $NGROK_PID 2>/dev/null
    exit 1
fi

echo "✅ ngrok URL: $NGROK_URL"

# Update .env
if [ -f .env ]; then
    sed -i "s|TWILIO_WEBHOOK_BASE_URL=.*|TWILIO_WEBHOOK_BASE_URL=$NGROK_URL|" .env
    echo "✅ Updated TWILIO_WEBHOOK_BASE_URL in .env"
else
    echo "⚠️  No .env file found. Copy .env.example to .env first."
fi

echo ""
echo "📋 Summary:"
echo "  Dashboard: http://localhost:3000"
echo "  API:       http://localhost:8000"
echo "  ngrok:     $NGROK_URL"
echo "  ngrok UI:  http://localhost:4040"
echo ""
echo "Press Ctrl+C to stop ngrok"
wait $NGROK_PID
