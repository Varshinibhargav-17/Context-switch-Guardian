from flask import Flask, request, jsonify
from datetime import datetime
import os
import requests  # ← ADDED THIS

# Initialize Flask app
app = Flask(__name__)

# In-memory storage (simple arrays for MVP)
interruptions = []
user_state = {
    'focus_mode_active': False,
    'focus_start_time': None
}

# ============================================
# ROUTE 1: Health Check
# ============================================
@app.route('/')
def home():
    """Health check endpoint"""
    return jsonify({
        'status': 'running',
        'app': 'Context Switch Guardian',
        'timestamp': datetime.now().isoformat(),
        'interruptions_today': len(interruptions),
        'focus_mode_active': user_state['focus_mode_active']
    })


# ============================================
# ROUTE 2: Webhook Receiver (Omi sends data here)
# ============================================
@app.route('/webhook/omi', methods=['POST'])
def webhook_omi():
    """Receive and process webhooks from Omi"""
    try:
        # Get data from Omi
        data = request.json
        
        # Log what we received
        print(f"\n📥 WEBHOOK RECEIVED:")
        print(f"Data: {data}")
        
        # Extract transcript from Omi's format
        transcript = ''
        
        # Try different possible transcript formats
        if 'transcript' in data:
            transcript = data.get('transcript', '')
        elif 'transcript_segments' in data:
            # Omi sends transcript in segments
            segments = data.get('transcript_segments', [])
            transcript = ' '.join([seg.get('text', '') for seg in segments])
        elif 'structured' in data:
            # Fallback to structured overview
            transcript = data.get('structured', {}).get('overview', '')
        
        # Get timestamp
        timestamp = data.get('created_at') or data.get('timestamp') or datetime.now().isoformat()
        
        print(f"📝 Extracted transcript: {transcript}")
        
        # Process the transcript
        result = process_conversation(transcript, timestamp)
        
        return jsonify({
            'success': True,
            'processed': result
        })
    
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================
# ROUTE 3: Daily Report Generator
# ============================================
@app.route('/report/daily', methods=['GET'])
def daily_report():
    """Generate and return daily report"""
    try:
        report = generate_daily_report()
        print(f"\n📊 REPORT GENERATED:")
        print(report)
        
        # Send report to Slack
        send_daily_report_to_slack(report)
        
        return jsonify(report)
    
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================
# HELPER FUNCTIONS
# ============================================

def process_conversation(transcript, timestamp):
    """Process incoming conversation"""
    print(f"\n🔍 PROCESSING: {transcript}")
    
    # Check if user is activating focus mode
    if detect_focus_mode(transcript):
        print("🎯 Focus mode detected!")
        activate_focus_mode()
        return 'focus_mode_activated'
    
    # Check if this is an interruption
    interruption = detect_interruption(transcript)
    if interruption:
        print(f"⚠️  Interruption detected: {interruption['type']}")
        save_interruption(transcript, timestamp, interruption['type'])
        return f"interruption_{interruption['type']}"
    
    return 'no_action_needed'


def detect_focus_mode(transcript):
    """Check if user is activating focus mode"""
    text = transcript.lower()
    triggers = [
        'focus mode',
        'entering focus mode',
        'deep work',
        'do not disturb',
        'dnd'
    ]
    
    return any(trigger in text for trigger in triggers)


def detect_interruption(transcript):
    """Detect if conversation is an interruption"""
    text = transcript.lower()
    
    # Patterns for different interruption types
    patterns = {
        'casual_chat': ['lunch', 'coffee', 'how are you', 'hey', 'what\'s up'],
        'work_request': ['can you', 'quick question', 'need help', 'could you'],
        'meeting': ['meeting', 'call', 'zoom', 'schedule', 'calendar'],
        'urgent': ['urgent', 'asap', 'emergency', 'now', 'immediately']
    }
    
    # Check each pattern
    for int_type, keywords in patterns.items():
        if any(keyword in text for keyword in keywords):
            return {'type': int_type}
    
    return None


def save_interruption(transcript, timestamp, int_type):
    """Save interruption to storage"""
    interruptions.append({
        'transcript': transcript,
        'timestamp': timestamp,
        'type': int_type,
        'time_lost_minutes': 23
    })
    print(f"💾 Saved: {len(interruptions)} interruptions total")


def activate_focus_mode():
    """Activate focus mode and notify Slack"""
    user_state['focus_mode_active'] = True
    user_state['focus_start_time'] = datetime.now().isoformat()
    
    print("🔴 FOCUS MODE ACTIVATED")
    
    # Send Slack notification
    send_slack_notification({
        'text': '🔴 Focus Mode Activated',
        'blocks': [
            {
                'type': 'section',
                'text': {
                    'type': 'mrkdwn',
                    'text': '*Focus Mode Active* 🎯\n\nYou are in deep work mode for the next 90 minutes.\nPlease hold non-urgent messages.'
                }
            }
        ]
    })


def generate_daily_report():
    """Generate daily statistics"""
    total_interruptions = len(interruptions)
    hours_lost = round((total_interruptions * 23) / 60, 1)
    focus_score = round(max(1, min(10, 10 - total_interruptions / 3)), 1)
    
    # Count interruptions by type
    by_type = {}
    for interruption in interruptions:
        int_type = interruption['type']
        by_type[int_type] = by_type.get(int_type, 0) + 1
    
    report = {
        'total_interruptions': total_interruptions,
        'hours_lost': hours_lost,
        'focus_score': focus_score,
        'interruptions_by_type': by_type,
        'tip': get_tip(total_interruptions)
    }
    
    return report


def send_daily_report_to_slack(report):
    """Send daily report to Slack"""
    # Format interruptions by type
    by_type_text = '\n'.join([f'• {k}: {v}' for k, v in report.get('interruptions_by_type', {}).items()])
    if not by_type_text:
        by_type_text = '• None'
    
    send_slack_notification({
        'text': '📊 Daily Focus Report',
        'blocks': [
            {
                'type': 'header',
                'text': {
                    'type': 'plain_text',
                    'text': '📊 Your Daily Focus Report'
                }
            },
            {
                'type': 'section',
                'fields': [
                    {
                        'type': 'mrkdwn',
                        'text': f"*Total Interruptions:*\n{report['total_interruptions']}"
                    },
                    {
                        'type': 'mrkdwn',
                        'text': f"*Time Lost:*\n{report['hours_lost']} hours"
                    },
                    {
                        'type': 'mrkdwn',
                        'text': f"*Focus Score:*\n{report['focus_score']}/10"
                    },
                    {
                        'type': 'mrkdwn',
                        'text': f"*By Type:*\n{by_type_text}"
                    }
                ]
            },
            {
                'type': 'section',
                'text': {
                    'type': 'mrkdwn',
                    'text': f"💡 *Tip:* {report['tip']}"
                }
            }
        ]
    })


def get_tip(count):
    """Generate personalized tip"""
    if count > 15:
        return "High interruption day! Try blocking focus time tomorrow."
    elif count < 5:
        return "Great focus day! Keep it up."
    else:
        return "Moderate interruptions. Use focus mode for deep work."


def send_slack_notification(payload):
    """Send notification to Slack"""
    webhook_url = os.environ.get('SLACK_WEBHOOK_URL')
    
    if not webhook_url:
        print('⚠️ Slack webhook not configured. Skipping notification.')
        print('Would have sent:', payload)
        return
    
    try:
        response = requests.post(webhook_url, json=payload)
        if response.status_code == 200:
            print('✅ Slack notification sent successfully')
        else:
            print(f'❌ Slack error: {response.status_code} - {response.text}')
    except Exception as e:
        print(f'❌ Error sending Slack notification: {e}')


# ============================================
# START SERVER
# ============================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"\n🚀 Starting Context Switch Guardian Server...")
    print(f"📡 Server will run on port {port}")
    print(f"🔗 Health check: http://localhost:{port}/")
    print(f"🪝 Webhook endpoint: http://localhost:{port}/webhook/omi")
    print(f"📊 Report endpoint: http://localhost:{port}/report/daily")
    print(f"\n✨ Server starting...\n")
    
    app.run(host='0.0.0.0', port=port, debug=True)