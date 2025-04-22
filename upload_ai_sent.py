#!/usr/bin/env python3
import os
import base64
import tempfile
import logging
from dotenv import load_dotenv
import openai
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ─── CONFIGURATION ─────────────────────────────────────────────────────────────
load_dotenv()
OPENAI_API_KEY   = os.getenv('OPENAI_API_KEY')
VECTOR_STORE_ID  = os.getenv('VECTOR_STORE_ID')
GMAIL_LABEL      = os.getenv('GMAIL_LABEL_ID')
SIGNATURE_MARKER = os.getenv('SIGNATURE_MARKER', '--')
CREDENTIALS_PATH = os.getenv('GOOGLE_CREDENTIALS_PATH', 'credentials.json')
REDIRECT_URI     = os.getenv('REDIRECT_URI', 'http://localhost:8888/')
SCOPES           = ['https://www.googleapis.com/auth/gmail.modify']

openai.api_key = OPENAI_API_KEY

# ─── LOGGING SETUP ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ─── HELPERS ────────────────────────────────────────────────────────────────────
def get_service():
    """Authenticate to Gmail and return a service object."""
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    else:
        flow = InstalledAppFlow.from_client_secrets_file(
            CREDENTIALS_PATH, SCOPES, redirect_uri=REDIRECT_URI
        )
        auth_url, _ = flow.authorization_url(prompt='consent')
        logger.info('Authorize this app by visiting: %s', auth_url)
        code = input('Enter the authorization code here: ').strip()
        flow.fetch_token(code=code)
        creds = flow.credentials
        with open('token.json', 'w') as f:
            f.write(creds.to_json())
    return build('gmail', 'v1', credentials=creds)

def get_labeled_messages(service):
    """Return all messages with the configured label, handling pagination."""
    messages = []
    try:
        request = service.users().messages().list(
            userId='me', labelIds=[GMAIL_LABEL]
        )
        while request:
            response = request.execute()
            messages.extend(response.get('messages', []))
            request = service.users().messages().list_next(request, response)
    except HttpError as e:
        logger.error('Failed to list labeled messages: %s', e)
    return messages

def strip_signature(body):
    """Remove everything after the signature marker."""
    return body.split(SIGNATURE_MARKER)[0].strip()

def upload_to_openai_file(filepath):
    """Upload a temp file to OpenAI and return its file ID."""
    with open(filepath, 'rb') as f:
        resp = openai.files.create(file=f, purpose='assistants')
    return resp.id

def add_to_vector_store(file_id):
    """Add an uploaded file to the configured vector store."""
    openai.vector_stores.files.create(
        vector_store_id=VECTOR_STORE_ID, file_id=file_id
    )

# ─── PROCESSING ────────────────────────────────────────────────────────────────
def process_message(service, msg_id):
    """
    Process a single Gmail message:
    - Fetch body (plain text or HTML)
    - Strip signature
    - Upload to OpenAI and index
    - Always remove the Gmail label
    Returns:
      1 if successfully processed,
      0 if skipped (empty body),
     -1 on error.
    """
    try:
        # Fetch the full message
        msg = service.users().messages().get(
            userId='me', id=msg_id, format='full'
        ).execute()
        payload = msg.get('payload', {})
        body = ''

        # Try plain text part
        for part in payload.get('parts', []):
            if part.get('mimeType') == 'text/plain' and part.get('body', {}).get('data'):
                body = base64.urlsafe_b64decode(part['body']['data']).decode()
                break

        # Fallback to HTML if no plain text
        if not body:
            for part in payload.get('parts', []):
                if part.get('mimeType') == 'text/html' and part.get('body', {}).get('data'):
                    html = base64.urlsafe_b64decode(part['body']['data']).decode()
                    body = html.replace('<br>', '\n').replace('<br/>', '\n')
                    break

        # Single-part message fallback
        if not body and payload.get('body', {}).get('data'):
            body = base64.urlsafe_b64decode(payload['body']['data']).decode()

        if not body.strip():
            logger.warning('Skipped empty message %s', msg_id)
            return 0

        cleaned = strip_signature(body)

        # Write to temp file and upload/index
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt') as tmp:
            tmp.write(cleaned)
            tmp.flush()
            logger.info('Uploading message %s to OpenAI...', msg_id)
            file_id = upload_to_openai_file(tmp.name)
            logger.info('Uploaded file ID %s', file_id)

        logger.info('Attaching file to vector store: %s', VECTOR_STORE_ID)
        add_to_vector_store(file_id)
        logger.info('Indexed message %s successfully', msg_id)
        return 1

    except Exception as e:
        logger.error('Error processing message %s: %s', msg_id, e)
        return -1

    finally:
        # Always remove the label, even on errors or skips
        try:
            service.users().messages().modify(
                userId='me', id=msg_id,
                body={'removeLabelIds': [GMAIL_LABEL]}
            ).execute()
            logger.info('Removed label from message %s', msg_id)
        except Exception as exc:
            logger.warning('Failed to remove label from %s: %s', msg_id, exc)

def main():
    service = get_service()
    messages = get_labeled_messages(service)

    total = len(messages)
    processed = skipped = errors = 0

    if total == 0:
        logger.info('No messages found with label %s', GMAIL_LABEL)
        return

    for msg in messages:
        result = process_message(service, msg['id'])
        if result == 1:
            processed += 1
        elif result == 0:
            skipped += 1
        else:
            errors += 1

    logger.info(
        'Run complete: total=%d, processed=%d, skipped=%d, errors=%d',
        total, processed, skipped, errors
    )

if __name__ == '__main__':
    main()
