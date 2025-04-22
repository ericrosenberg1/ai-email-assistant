#!/usr/bin/env python3
import os
import base64
import json
import time
import logging
from datetime import datetime, timezone
from dotenv import load_dotenv
import openai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.errors import HttpError

# ─── CONFIGURATION ─────────────────────────────────────────────────────────────
load_dotenv()
OPENAI_API_KEY       = os.getenv('OPENAI_API_KEY')
ASSISTANT_ID         = os.getenv('ASSISTANT_ID')
SIGNATURE            = os.getenv(
    'EMAIL_SIGNATURE',
    "-- \nEric Rosenberg\nEricRosenberg.com\nFinancial Writing, Speaking, and Consulting"
)
SCOPES               = ['https://www.googleapis.com/auth/gmail.modify']
CREDENTIALS_PATH     = os.getenv('GOOGLE_CREDENTIALS_PATH', 'credentials.json')
LAST_RUN_FILE        = 'last_run.json'

openai.api_key = OPENAI_API_KEY

# ─── LOGGING SETUP ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# ─── GMAIL / OPENAI HELPERS ────────────────────────────────────────────────────
def get_service():
    """Authenticate (or load token.json) and return a Gmail API service."""
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    else:
        flow = InstalledAppFlow.from_client_secrets_file(
            CREDENTIALS_PATH, SCOPES
        )
        url, _ = flow.authorization_url(prompt='consent')
        logging.info('First‑time auth: visit URL and paste code: %s', url)
        code = input('Enter code> ').strip()
        flow.fetch_token(code=code)
        creds = flow.credentials
        with open('token.json', 'w') as f:
            f.write(creds.to_json())
    return build('gmail', 'v1', credentials=creds)

def get_last_run_time():
    """Load last run ISO timestamp or return None."""
    if os.path.exists(LAST_RUN_FILE):
        with open(LAST_RUN_FILE) as f:
            return json.load(f).get('last_run')
    return None

def update_last_run_time():
    """Write the current UTC time to LAST_RUN_FILE."""
    now = datetime.now(timezone.utc).isoformat()
    with open(LAST_RUN_FILE, 'w') as f:
        json.dump({'last_run': now}, f)

def get_unread_messages(service, last_run):
    """
    Return all messages matching "in:inbox is:unread [after:TIMESTAMP]" via pagination.
    """
    query = 'in:inbox is:unread'
    if last_run:
        ts = int(datetime.fromisoformat(last_run).timestamp())
        query += f' after:{ts}'
    messages = []
    try:
        request = service.users().messages().list(userId='me', q=query)
        while request:
            resp = request.execute()
            messages.extend(resp.get('messages', []))
            request = service.users().messages().list_next(request, resp)
    except HttpError as e:
        logging.error('Gmail list error: %s', e)
    return messages

def get_message_content(service, msg_id):
    """
    Fetch the full message, extract subject, sender, text/plain or fallback to HTML.
    Returns (subject, sender, body, thread_id).
    """
    resp = service.users().messages().get(
        userId='me', id=msg_id, format='full'
    ).execute()
    payload = resp.get('payload', {})
    headers = payload.get('headers', [])
    subject = next((h['value'] for h in headers if h['name']=='Subject'), '(no subject)')
    sender  = next((h['value'] for h in headers if h['name']=='From'), '(unknown)')
    # extract body
    body = ''
    for part in payload.get('parts', []):
        if part.get('mimeType')=='text/plain' and part.get('body',{}).get('data'):
            body = base64.urlsafe_b64decode(part['body']['data']).decode()
            break
    if not body:
        for part in payload.get('parts', []):
            if part.get('mimeType')=='text/html' and part.get('body',{}).get('data'):
                html = base64.urlsafe_b64decode(part['body']['data']).decode()
                body = html.replace('<br>', '\n').replace('<br/>', '\n')
                break
    if not body and payload.get('body',{}).get('data'):
        body = base64.urlsafe_b64decode(payload['body']['data']).decode()
    return subject, sender, body, resp.get('threadId')

def draft_reply(service, thread_id, to_email, subject, text):
    """
    Create a draft in Gmail with the AI reply + signature.
    """
    full = text.strip() + "\n\n" + SIGNATURE
    raw = base64.urlsafe_b64encode(
        f"From: me\nTo: {to_email}\nSubject: Re: {subject}\n\n{full}".encode()
    ).decode()
    body = {'message': {'threadId': thread_id, 'raw': raw, 'labelIds': ['DRAFT']}}
    service.users().drafts().create(userId='me', body=body).execute()

def generate_reply_from_openai(user_msg):
    """
    Send the user message to your Assistant and wait for completion.
    """
    thread = openai.beta.threads.create()
    openai.beta.threads.messages.create(
        thread_id=thread.id, role='user', content=user_msg
    )
    run = openai.beta.threads.runs.create(
        thread_id=thread.id, assistant_id=ASSISTANT_ID
    )
    while run.status not in ('completed','failed'):
        time.sleep(2)
        run = openai.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
    if run.status!='completed':
        raise RuntimeError('OpenAI run failed')
    msgs = openai.beta.threads.messages.list(thread_id=thread.id)
    return msgs.data[0].content[0].text.value

# ─── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    service     = get_service()
    last_run    = get_last_run_time()
    messages    = get_unread_messages(service, last_run)

    total       = len(messages)
    drafted     = 0
    skipped     = 0
    errors      = 0

    if not messages:
        logging.info('No new messages found.')
        update_last_run_time()
        return

    for msg in messages:
        msg_id = msg['id']
        try:
            subj, sender, body, thread_id = get_message_content(service, msg_id)
            if not body.strip():
                logging.warning('Skipped empty message %s', msg_id)
                skipped += 1
                continue

            logging.info('Drafting reply for %s (from %s)', subj, sender)
            reply = generate_reply_from_openai(body)
            draft_reply(service, thread_id, sender, subj, reply)
            logging.info('Draft created for %s', msg_id)
            drafted += 1

            # Mark read
            try:
                service.users().messages().modify(
                    userId='me', id=msg_id,
                    body={'removeLabelIds': ['UNREAD']}
                ).execute()
            except Exception as e:
                logging.warning('Could not mark read %s: %s', msg_id, e)

        except Exception as e:
            logging.error('Error on %s: %s', msg_id, e)
            errors += 1

    # Always update last_run
    update_last_run_time()
    logging.info(
        'Run complete: %d total, %d drafted, %d skipped, %d errors',
        total, drafted, skipped, errors
    )

if __name__ == '__main__':
    main()
