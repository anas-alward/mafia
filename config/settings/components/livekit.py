from ..env import env

## LiveKit (WebRTC media server)
# LIVEKIT_URL is the browser-facing signaling URL, not the backend's.
LIVEKIT_URL = env.str('LIVEKIT_URL', default='ws://localhost:7880')
# Server-side RoomService API (used for voice enforcement); resolves
# inside the compose network.
LIVEKIT_SERVER_URL = env.str('LIVEKIT_SERVER_URL', default='http://livekit:7880')
LIVEKIT_API_KEY = env.str('LIVEKIT_API_KEY', default='devkey')
LIVEKIT_API_SECRET = env.str('LIVEKIT_API_SECRET', default='devsecret')
