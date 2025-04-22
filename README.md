# AI Gmail Assistant

A Linux‑based automation system that drafts replies to Gmail messages using OpenAI Assistants and indexes your sent messages into a vector store so the assistant learns your voice and tone.

Works on Raspberry Pi, Debian, Ubuntu, LMDE, or any headless Linux server with Python 3.

---

## ✨ Features

- Uploads “AI_Sent”‑labeled sent emails to an OpenAI vector store  
- Generates AI‑powered reply drafts for inbox messages (skips existing drafts)  
- Saves replies as Gmail drafts (never auto‑sends)  
- Learns from your past emails in the vector store  
- Fully configurable via `.env`  
- Runs in a Python venv and scheduled via `cron`  
- Optional Slack/email failure alerts  

---

## 🚀 Requirements

- Python 3.8 or newer  
- `git`, `cron`  
- A Gmail account (Workspace or personal)  
- [OpenAI API key](https://platform.openai.com/account/api-keys)  
- An OpenAI Assistant with your vector store attached  
- Gmail OAuth credentials (`credentials.json`)  

---

## 🔧 Initial Setup

1. **Clone the repo**  
   ```bash
   git clone https://github.com/YOUR_USERNAME/ai-email-assistant.git
   cd ai-email-assistant
   ```

2. **Create a virtual environment & install**  
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. **Configure your environment**  
   ```bash
   cp env-example .env
   nano .env
   ```  
   Edit `.env` with your own values. See **`.env.example`** below.

4. **Place your `credentials.json`**  
   Download your Gmail OAuth client credentials from Google Cloud Console and save as `credentials.json` in this folder.

5. **Authenticate Gmail access**  
   ```bash
   source venv/bin/activate
   python upload_ai_sent.py
   ```  
   Follow the prompt (visit URL, grant access, paste the code) to generate `token.json`.

6. **Test reply drafting**  
   ```bash
   python draft_replies.py
   ```  
   You should see draft‑creation logs and drafts in Gmail.

---

## 📄 `.env.example`

```dotenv
# === OpenAI Configuration ===
OPENAI_API_KEY=your-openai-api-key
ASSISTANT_ID=your-assistant-id
VECTOR_STORE_ID=your-vector-store-id

# === Gmail Label Configuration ===
GMAIL_LABEL_ID=Label_XXXXXXXXXXXXXXXX

# === Signature Stripping ===
SIGNATURE_MARKER=--
EMAIL_SIGNATURE="-- \nYour Name\nyourwebsite.com\nYour Title"

# === Google OAuth2 Configuration ===
GOOGLE_CREDENTIALS_PATH=credentials.json
REDIRECT_URI=http://localhost:8888/
```

---

## 📂 File Structure

```
ai-email-assistant/
├── upload_ai_sent.py       # Indexes sent emails into OpenAI vector store
├── draft_replies.py        # Drafts AI replies for inbox messages
├── credentials.json        # OAuth client secrets (gitignored)
├── token.json              # Gmail access token (auto‑generated, gitignored)
├── .env                    # Your local config (gitignored)
├── env-example             # Template for .env
├── requirements.txt        # Python dependencies
├── venv/                   # Python virtual environment
├── last_run.json           # Tracks last run for reply script (gitignored)
├── upload.log              # Cron log for upload (gitignored)
└── draft.log               # Cron log for drafts (gitignored)
```

> **Note:** `.gitignore` excludes `venv/`, `.env`, `token.json`, `upload.log`, `draft.log`, and other local artifacts.

---

## ⏱️ Scheduling with Cron

Edit your crontab:

```bash
crontab -e
```

Add these lines (replace `eric` with your username):

```cron
# Upload "AI_Sent" labeled emails every hour
0 * * * * cd /home/eric/ai-email-assistant && /home/eric/ai-email-assistant/venv/bin/python upload_ai_sent.py >> /home/eric/ai-email-assistant/upload.log 2>&1

# Draft replies for inbox messages every 15 minutes
*/15 * * * * cd /home/eric/ai-email-assistant && /home/eric/ai-email-assistant/venv/bin/python draft_replies.py >> /home/eric/ai-email-assistant/draft.log 2>&1
```

---

## 🔐 Security

- **Draft‑only**: No emails are ever sent automatically  
- **.env** holds all secrets—never commit it  
- **token.json** stores Gmail auth—keep it private  

---

## 🛠 Future Enhancement Ideas

- Slack or email alerts on cron failures  
- Custom labels for processed threads  
- Web dashboard or stats page  
- Integration with SMS providers (Twilio, Plivo)  
- GitHub Actions for CI and linting  

---

## 🧑‍💻 Maintainer

**Your Name** – yourwebsite.com – [@YourHandle](https://twitter.com/YourHandle)  

---

## 📄 License

**MIT License** — see [LICENSE](LICENSE) for details.
