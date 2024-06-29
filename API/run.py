from flask import Flask, request, jsonify, session
from flask_socketio import SocketIO, join_room, leave_room, emit
from datetime import datetime
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*")

user_requests = {}
messages = {}
approved_requests = {}
active_users = set()

@app.route('/session', methods=['GET'])
def session_data():
    return jsonify(dict(session))

@app.route('/get_user_details', methods=['GET', 'POST'])
def get_user_details():
    if request.method == 'GET':
        return jsonify({'message': 'Please enter your username:'})
    
    elif request.method == 'POST':
        data = request.get_json()
        username = data.get('username')
        phone_number = data.get('phone_number')
        
        if 'username' not in data:
            return jsonify({'error': 'Username is required'}), 400
        
        if 'phone_number' not in data:
            return jsonify({'message': 'Please enter your phone_number'}), 400
        
        else:
            return jsonify({
                'message': f'Thank you {username}, your phone number {phone_number} has been recorded.',
                'username': username,
                'phone_number': phone_number
            })

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    userid = data.get('userid')
    userrole = data.get('userrole')
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if not username or not userid or not userrole:
        return jsonify({'error': 'Missing required fields'}), 400

    if userrole.lower() == 'liveagent':
        return jsonify({'redirect': '/liveagent','username':username,'userrole':userrole,'userid':userid})
    elif userrole.lower() == 'user':    
        if username and userid and userrole and timestamp:
            user_requests[userid] = {'username': username, 'userrole': userrole, 'timestamp': timestamp}
            return jsonify({'redirect': f'/waiting/{username}'})
        print("user request added")
    else:
        return jsonify({'error': 'User role invalid'}), 400

    return jsonify({'redirect': '/'})

@app.route('/liveagent', methods=['GET'])
def liveagent_dashboard():
    print("[DASHBOARD] Live agent dashboard accessed.")
    return jsonify({"user_requests": user_requests})
    

@app.route('/active_users', methods=['GET'])
def active_users_route():
    users = [
        {
            'userid': userid, 
            'username': details['username'],
            'timestamp': details['timestamp']
        } 
        for userid, details in approved_requests.items()
    ]
    print(len(users))
    print("[ACTIVE USERS] Active users fetched.")
    return jsonify({'active_users': users, 'length': len(users)})

@app.route('/approve_request/<userid>', methods=['POST'])
def approve_request(userid):
    if userid in user_requests:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        approved_requests[userid] = user_requests.pop(userid)
        username = approved_requests[userid]['username']
        active_users.add(userid)  
        socketio.emit('request_approved', {'userid': userid, 'username': username, 'timestamp': timestamp}, room=userid)
        print(f"[APPROVE] User {userid} approved and moved to approved requests.")
        return jsonify({'message': 'User approved successfully', 'timestamp': timestamp}), 200
    else:
        print(f"[APPROVE ERROR] User {userid} not found.")
        return jsonify({'error': 'User not found', 'timestamp': timestamp}), 404

@app.route('/approved_request/<userid>', methods=['GET'])
def approved_request(userid):
    if userid in approved_requests:
        username = approved_requests[userid]['username']
        print(f"[APPROVE] User {userid} approved and moved to approved requests.")
        return jsonify({'message': 'User approved successfully', 'userid': userid, 'username': username}), 200
    else:
        print(f"[APPROVE ERROR] User {userid} not found.")
        return jsonify({'error': 'User not found'}), 404

@app.route('/get_user_requests', methods=['GET'])
def get_user_requests():
    requests = [
        {
            'userid': userid,
            'username': details['username'],
            'userrole': details['userrole'],
            'timestamp': details['timestamp'],
            'url': f'/approve_request/{userid}'
        }
        for userid, details in user_requests.items()
    ]
    print("[USER REQUESTS] User requests fetched.")
    return jsonify({'user_requests': requests, 'length': len(requests)})

@app.route('/waiting/<username>', methods=['GET'])
def waiting(username):
    user_found = any(details['username'] == username for details in user_requests.values())
    if user_found:
        print(f"[WAITING] User {username} is waiting for approval.")
        return jsonify({'message': f'User {username} is waiting for approval'})
    else:
        print(f"[WAITING ERROR] Invalid username: {username}")
        return jsonify({'message': 'Username is invalid'}), 404

@app.route('/chat', methods=['GET'])
def chat():
    username = request.args.get('username')
    chat_with = request.args.get('chat_with')
    timestamp = request.args.get('timestamp')
    room_name = f"{username}-{chat_with}" if username == "liveagent" else f"{chat_with}-{username}"
    chat_history_for_user = messages.get(room_name, [])
    print(f"[CHAT] Chat history fetched for user {username} in room {room_name}.")
    return jsonify({
        'username': username,
        'chat_history': chat_history_for_user,
        'room_name': room_name,
        'chat_with': chat_with,
        'timestamp': timestamp
    })

@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('join')
def handle_join(data):
    room_name = data['room_name']
    userid = data['userid']
    userrole = data.get('userrole', 'user')
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    join_room(room_name, sid=request.sid) 
    print("joined")
    if userrole.lower() == 'user':
        active_users.add(userid)
    emit('notification_join', {'username': 'System', 'text': f'{userid} has joined the room.', 'timestamp': timestamp}, room=room_name)

@socketio.on('leave')
def handle_leave(data):
    try:
        room_name = data['room_name']
        userid = data['userid']
        userrole = data.get('userrole', 'user')
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        leave_room(room_name)
        print("leave")
        if userrole.lower() == 'user':
            active_users.discard(userid)
            print('active users discared')
        emit('notification_leave', {'username': 'System', 'text': f'{userid} has left the room.', 'timestamp': timestamp}, room=room_name)
    except KeyError as e:
        print(f"KeyError: {e}")

@socketio.on('send_message')
def handle_message(data):
    room_name = data['room_name']
    message = data['message']
    print(message)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_message = f"{data['username']}: {message} ({timestamp})"
    messages.setdefault(room_name, []).append(formatted_message)
    emit('message', {'username': data['username'], 'text': message, 'timestamp': timestamp}, room=room_name)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
