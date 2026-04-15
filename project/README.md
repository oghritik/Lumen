# 💡 Project LUMEN

**Smart Personal Finance & Transaction Tracker**

A comprehensive Flask-based web application that automatically syncs and analyzes your financial data from Gmail, providing AI-powered insights, spending analytics, and anomaly detection.

![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.0-green?logo=flask&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-Database-blue?logo=sqlite&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## ✨ Features

### 🔐 **Google OAuth Integration**
- Secure OAuth 2.0 login with Gmail
- Automatic syncing of transaction emails and receipts
- PDF attachment downloading and processing

### 📊 **AI-Powered Analytics Dashboard**
- **Category Pie Charts** - Visualize spending distribution
- **Daily & Monthly Spending Trends** - Track financial patterns over time
- **Top Spending Categories** - Identify where your money goes
- **Net Flow Analysis** - Monitor credits vs debits

### 🤖 **LLM-Powered Insights**
- AI-generated financial summaries using Qwen LLM
- Pattern detection and behavioral analysis
- Personalized savings recommendations
- Risk identification and alerts

### 🔍 **Anomaly Detection**
- Suspicious transaction flagging
- High-value transaction alerts
- Recurring payment detection
- Peak spending day identification

### 📄 **Receipt Management**
- **Gmail Receipts** - Auto-sync PDF attachments from invoices
- **OCR Upload** - Upload receipt images for NVIDIA Vision-powered extraction
- Detailed receipt viewing with extracted metadata

### 📝 **Transaction Tracking**
- Complete transaction history with filtering
- Merchant and category breakdown
- Detailed transaction view with all metadata

### 🎯 **Wishlist**
- Track items you want to purchase
- Organize and manage your spending goals

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend** | Python 3.11+, Flask 3.0 |
| **Database** | SQLite with SQLAlchemy ORM |
| **Authentication** | Google OAuth 2.0 |
| **AI/ML** | Local LLM (Qwen), NVIDIA Vision OCR |
| **Data Analysis** | Pandas, Matplotlib, Seaborn |
| **Frontend** | Jinja2 Templates, HTML5, CSS3, JavaScript |
| **Charts** | Chart.js |

---

## 📁 Project Structure

```
project/
├── app.py                      # Main Flask application
├── requirements.txt            # Python dependencies
├── lumen_transactions.db       # SQLite database
├── .env                        # Environment variables (create from .env.example)
├── client_secret.json          # Google OAuth credentials
│
├── modules/
│   ├── services/               # Business logic layer (route-independent)
│   │   ├── dashboard_service.py
│   │   ├── receipt_upload_service.py
│   │   └── wishlist_service.py
│   │
│   ├── web/                    # Shared web/auth/session helpers
│   │   ├── access.py
│   │   └── user_context.py
│   │
│   ├── database/               # Database models & repositories
│   │   ├── db.py               # SQLAlchemy instance
│   │   ├── models.py           # Transaction, Receipt, Wishlist models
│   │   ├── repository.py       # Transaction repository
│   │   ├── transaction_repo.py # Receipt repository
│   │   └── wishlist_repo.py    # Wishlist repository
│   │
│   ├── analytics/              # AI-powered analytics engine
│   │   ├── analyzer.py         # Chart generation & LLM insights
│   │   └── cache.py            # Analytics caching
│   │
│   ├── llm_extraction/         # LLM-based data extraction
│   │   └── extractor.py        # Transaction/receipt text extraction
│   │
│   ├── gmail_sync.py           # Gmail API integration
│   └── nvidia_ocr.py           # NVIDIA Vision OCR processing
│
├── templates/                  # Jinja2 HTML templates
│   ├── landing.html            # Login/landing page
│   ├── anomalies.html          # Analytics dashboard
│   ├── transactions.html       # Transaction list
│   ├── receipts.html           # Receipt management
│   ├── wishlist.html           # Wishlist page
│   └── ...
│
├── static/
│   ├── css/style.css           # Application styles
│   └── js/charts.js            # Chart.js configurations
│
└── uploads/
    └── receipts/               # Uploaded receipt files
```

See `ARCHITECTURE.md` for backend layering and extension guidelines.

---

## 🚀 Getting Started

### Prerequisites

- Python 3.11 or higher
- Google Cloud Console account (for OAuth credentials)
- Local LLM server (optional, for AI insights)

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/project-lumen.git
cd project-lumen
```

### 2. Install Dependencies

```bash
# Enter the app directory
cd project

pip install -r requirements.txt
pip install -r requirements_analytics.txt  # For analytics features
```

### 3. Configure Environment Variables

Create a `.env` file from the example:

```bash
cp .env.example .env
```

Edit `.env` with your configuration:

```env
# Flask Configuration
FLASK_SECRET_KEY=your_secure_secret_key_here

# Google OAuth
GOOGLE_CLIENT_SECRET_FILE=client_secret.json

# LLM Configuration (optional - for AI insights)
LLM_API_URL=http://localhost:1234/v1/chat/completions
```

### 4. Set Up Google OAuth Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the **Gmail API** and **People API**
4. Configure OAuth consent screen
5. Create OAuth 2.0 credentials (Web application type)
6. Download the JSON and save as `client_secret.json`
7. Add `http://localhost:5000/oauth2callback` as an authorized redirect URI

### 5. Run the Application

```bash
python app.py
```

The application will be available at `http://localhost:5000`

---

## 🚢 Deployment (Production)

### 1. Configure Production Environment

Use `project/.env.example` as reference and set at minimum:

```env
APP_ENV=production
FLASK_DEBUG=0
FLASK_SECRET_KEY=replace_with_long_random_value
GOOGLE_CLIENT_SECRET_FILE=client_secret.json
PORT=5000
```

### 2. Install Production Dependencies

```bash
cd project
pip install -r requirements.txt
```

### 3. Run with Gunicorn

```bash
gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 wsgi:app
```

The project includes `wsgi.py` and a `Procfile` for platform deployment.

### 4. Health Check Endpoint

Use this endpoint for load balancer/container health checks:

```text
GET /healthz
```

---

## 📖 Usage

### Login
1. Navigate to `http://localhost:5000`
2. Click "Login" to authenticate with your Google account
3. Grant the necessary permissions for Gmail access

### Sync Data
- Click the **Sync** button in the dashboard to fetch transactions and receipts from Gmail
- The sync process extracts transaction notifications and invoice PDFs

### View Analytics
- The main dashboard displays AI-powered insights
- View spending charts, category breakdowns, and trend analysis
- Check for suspicious transactions and anomalies

### Upload Receipts
- Navigate to the Receipts page
- Upload receipt images (JPG, PNG, PDF)
- NVIDIA Vision OCR extracts merchant, amount, and date automatically

---

## 🔧 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Landing/login page |
| `/dashboard-analytics` | GET | Main analytics dashboard |
| `/transactions` | GET | Transaction list |
| `/receipts` | GET | Receipt management |
| `/sync` | GET | Trigger Gmail sync |
| `/api/anomalies-data` | GET | Analytics JSON data |
| `/api/dashboard-data` | GET | Dashboard charts data |
| `/upload-receipt` | POST | Upload receipt for OCR |
| `/api/debug/stats` | GET | Database statistics |

---

## 🔒 Security Notes

- OAuth tokens are stored in Flask session (httpOnly cookies)
- Uses secure OAuth 2.0 flow with consent prompt
- No credentials are stored in the database
- Environment variables used for sensitive configuration

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## ⚠️ Disclaimer

This project uses your consented financial data (receipts, bank statements) to analyze spending patterns and suggest potential insights. It is **not professional financial advice** and should not replace consultation with a qualified financial advisor. Always consult a professional for financial planning and decisions.

---

## 📧 Contact

**Project LUMEN** - Smart Finance Tracker

Made with ❤️ for better financial awareness
