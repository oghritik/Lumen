import os

import base64
from flask import Flask, redirect, url_for, session, render_template, request, send_file, flash, jsonify
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from dotenv import load_dotenv
from io import BytesIO
from datetime import timedelta
import json
from werkzeug.middleware.proxy_fix import ProxyFix

# Import ONE database instance
from modules.database.db import db
from modules.database.models import Transaction, Receipt
from modules.database.repository import TransactionRepository
from modules.database.transaction_repo import ReceiptRepository
from modules.database.wishlist_repo import WishlistRepository
from modules.gmail_sync import sync_all_gmail_data

# Import analytics module
from modules.analytics.analyzer import generate_analytics_report
from modules.analytics.cache import analytics_cache

# Import NVIDIA OCR module
from modules.services.receipt_upload_service import process_receipt_upload
from modules.services.dashboard_service import build_dashboard_payload, build_dashboard_error_payload
from modules.services.wishlist_service import categorize_item, serialize_wishlist_items
from modules.web.access import require_auth
from modules.web.user_context import get_or_cache_user_email

# Import MCP server for secure LLM-backend communication
from modules.mcp.server import mcp_server

load_dotenv()

APP_ENV = os.getenv("APP_ENV", os.getenv("FLASK_ENV", "development")).lower()
IS_PRODUCTION = APP_ENV == "production"

# Allow OAuth callbacks over HTTP only for local development.
if not IS_PRODUCTION and os.getenv("OAUTHLIB_INSECURE_TRANSPORT") is None:
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

app = Flask(__name__)

flask_secret_key = os.getenv("FLASK_SECRET_KEY")
if IS_PRODUCTION and not flask_secret_key:
    raise RuntimeError("FLASK_SECRET_KEY is required when APP_ENV=production")
if not flask_secret_key:
    flask_secret_key = "dev-only-change-me"
app.secret_key = flask_secret_key

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE=os.getenv("SESSION_COOKIE_SAMESITE", "Lax"),
    SESSION_COOKIE_SECURE=IS_PRODUCTION,
    PERMANENT_SESSION_LIFETIME=timedelta(hours=int(os.getenv("SESSION_LIFETIME_HOURS", "12"))),
)

# Trust one reverse proxy hop in production-style deployments.
if os.getenv("TRUST_PROXY", "1") == "1":
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# Configure SQLite database with ABSOLUTE PATH
# This prevents Flask from creating it in the instance/ folder
project_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(project_dir, 'lumen_transactions.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize ONE database instance
db.init_app(app)

# Auto-initialize database on startup
print("\n" + "="*80)
print("🚀 INITIALIZING DATABASE")
print("="*80)
print(f">>>> USING DB: {app.config['SQLALCHEMY_DATABASE_URI']}")
print(f">>>> ABSOLUTE PATH: {db_path}")
print("="*80)

with app.app_context():
    # Create tables if they don't exist (PRESERVES existing data)
    db.create_all()
    print("✅ Database initialized: lumen_transactions.db")
    print("📊 Table: transactions")
    print("📊 Table: receipts")
    print("📊 Table: wishlist")
    
    # Verify database file exists
    if os.path.exists(db_path):
        size_kb = os.path.getsize(db_path) / 1024
        print(f"✅ Database file verified: {size_kb:.2f} KB")
    else:
        print("❌ WARNING: Database file not found at expected location!")

print("="*80 + "\n")

# Register custom Jinja2 filter for JSON parsing
@app.template_filter('from_json')
def from_json_filter(s):
    return json.loads(s)


# ---------------------- ERROR HANDLERS ----------------------
@app.errorhandler(400)
def bad_request_error(error):
    print(f"❌ 400 Bad Request: {error}")
    print(f"Request URL: {request.url}")
    print(f"Request method: {request.method}")
    if request.is_json:
        print(f"Request JSON: {request.get_json()}")
    return jsonify({
        "success": False,
        "error": "Bad Request",
        "message": str(error)
    }), 400


@app.errorhandler(500)
def internal_error(error):
    print(f"❌ 500 Internal Server Error: {error}")
    print(f"Request URL: {request.url}")
    print(f"Request method: {request.method}")
    import traceback
    traceback.print_exc()
    db.session.rollback()
    return jsonify({
        "success": False,
        "error": "Internal Server Error",
        "message": "An unexpected error occurred"
    }), 500

CLIENT_SECRET_FILE = os.getenv("GOOGLE_CLIENT_SECRET_FILE")
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid"
]

# Initialize repository
repo = TransactionRepository()


# ---------------------- HOME ----------------------
@app.route("/")
def index():
    # Keep authenticated users in MCP setup flow until they explicitly continue.
    if "credentials" in session and session.get("mcp_setup_required"):
        return redirect(url_for("mcp_setup"))

    # Show landing page for unauthenticated users
    if "credentials" in session or session.get("guest_access"):
        return redirect(url_for("dashboard_analytics"))
    else:
        return render_template("landing.html")


# ---------------------- LOGIN PAGE ----------------------
@app.route("/login")
def login_page():
    """Alternative login page route"""
    if "credentials" in session and session.get("mcp_setup_required"):
        return redirect(url_for("mcp_setup"))

    if "credentials" in session or session.get("guest_access"):
        return redirect(url_for("dashboard_analytics"))
    else:
        return render_template("login.html")

@app.route("/login-with-google")
def login_with_google():
    """Route for the Google login button"""
    return redirect(url_for("auth_google"))


@app.route("/mcp/skip")
def mcp_skip():
    """Allow user to skip MCP phone setup and continue to dashboard."""
    session.pop("mcp_setup_required", None)

    # Keep guest mode only for users who skipped without Google auth.
    if "credentials" not in session:
        session["guest_access"] = True

    return redirect(url_for("dashboard_analytics"))


@app.route("/mcp/setup")
@require_auth()
def mcp_setup():
    """Post-login MCP options page shown immediately after Google auth."""
    return render_template("landing.html", show_mcp_panel=True)


# ---------------------- GOOGLE LOGIN ----------------------
@app.route("/auth/google")
def auth_google():
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRET_FILE,
        scopes=SCOPES,
        redirect_uri=url_for("oauth2callback", _external=True)
    )

    auth_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true"
    )

    session["state"] = state
    session.permanent = True

    return redirect(auth_url)


# ---------------------- GOOGLE CALLBACK ----------------------
@app.route("/oauth2callback")
def oauth2callback():
    try:
        state = session.get("state")

        if not state:
            flash("Authentication session expired. Please login again.", "error")
            return redirect(url_for("auth_google"))

        flow = Flow.from_client_secrets_file(
            CLIENT_SECRET_FILE,
            scopes=SCOPES,
            state=state,
            redirect_uri=url_for("oauth2callback", _external=True)
        )

        flow.fetch_token(authorization_response=request.url)
    
    except Exception as e:
        print(f"❌ OAuth Error: {str(e)}")
        # Check if it's a scope warning that we can handle
        if "Scope has changed" in str(e):
            print("⚠️  Gmail scope was not granted. App will work with limited functionality.")
            # Still try to get basic credentials if possible
            try:
                flow = Flow.from_client_secrets_file(
                    CLIENT_SECRET_FILE,
                    scopes=["https://www.googleapis.com/auth/userinfo.profile", "https://www.googleapis.com/auth/userinfo.email", "openid"],
                    state=state,
                    redirect_uri=url_for("oauth2callback", _external=True)
                )

                flow.fetch_token(authorization_response=request.url)
            except:
                flash("Authentication failed. Please check your Google Cloud Console setup.", "error")
                return redirect(url_for("index"))
        else:
            flash(f"Authentication failed: {str(e)}", "error")
            return redirect(url_for("index"))

    creds = flow.credentials

    session["credentials"] = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes
    }

    session.pop("state", None)

    # Authenticated users should not remain in guest mode.
    session.pop("guest_access", None)
    
    # Fetch user profile info from Google
    try:
        from googleapiclient.discovery import build
        credentials = Credentials(
            token=creds.token,
            refresh_token=creds.refresh_token,
            token_uri=creds.token_uri,
            client_id=creds.client_id,
            client_secret=creds.client_secret
        )
        
        # Get user info from People API or userinfo endpoint
        oauth2_service = build('oauth2', 'v2', credentials=credentials)
        user_info = oauth2_service.userinfo().get().execute()
        
        # Store user info in session
        session['user_name'] = user_info.get('name', 'LUMEN User')
        session['user_email'] = user_info.get('email', '')
        session['user_picture'] = user_info.get('picture', '')
        
        print(f"✅ User logged in: {session['user_name']} ({session['user_email']})")
    except Exception as e:
        print(f"⚠️ Could not fetch user profile: {e}")
        session['user_name'] = 'LUMEN User'
        session['user_email'] = ''

    session["mcp_setup_required"] = True
    return redirect(url_for("mcp_setup"))


# ---------------------- OLD DASHBOARD (REMOVED) ----------------------
# This dashboard page has been replaced by dashboard_analytics
# Kept as commented code in case needed for reference
# @app.route("/dashboard")
# def dashboard():
#     if "credentials" not in session:
#         return redirect(url_for("index"))
#     # ... (rest of old dashboard code removed)


# ---------------------- RECEIPTS PAGE ----------------------
@app.route("/receipts")
@require_auth(allow_guest=True)
def receipts_page():
    # Load receipts from SQLite
    receipts_data = ReceiptRepository.get_recent(limit=40)

    receipts = []
    for receipt in receipts_data:
        # Determine receipt type: Gmail or OCR
        is_gmail = receipt.attachment_message_id is not None and receipt.attachment_id is not None
        
        receipt_dict = {
            "receipt_id": receipt.receipt_id,
            "vendor": receipt.merchant_name,
            "date": receipt.issue_date,
            "total": receipt.total_amount,
            "snippet": receipt.raw_snippet or f"{receipt.merchant_name} - ₹{receipt.total_amount}",
            "type": "gmail" if is_gmail else "ocr",
            "filename": receipt.attachment_filename,
            "attachmentId": receipt.attachment_id if is_gmail else None,
            "messageId": receipt.attachment_message_id if is_gmail else None
        }
        
        receipts.append(receipt_dict)

    return render_template("receipts.html", receipts=receipts)


# ---------------------- VIEW OCR RECEIPT ----------------------
@app.route("/receipt/<receipt_id>")
@require_auth(allow_guest=True)
def view_receipt(receipt_id):
    """View detailed information for an OCR-uploaded receipt."""
    # Get receipt from database
    receipt = Receipt.query.filter_by(receipt_id=receipt_id).first()
    
    if not receipt:
        return "Receipt not found", 404
    
    # Parse raw_snippet if it contains JSON
    extracted_json = None
    if receipt.raw_snippet:
        try:
            # Try to extract JSON from raw_snippet
            cleaned = receipt.raw_snippet.strip()
            if cleaned.startswith('{') and cleaned.endswith('}'):
                extracted_json = json.loads(cleaned)
        except:
            pass
    
    return render_template("receipt_view.html", receipt=receipt, extracted_json=extracted_json)


# ---------------------- TRANSACTIONS PAGE ----------------------
@app.route("/transactions")
@require_auth(allow_guest=True)
def transactions_page():
    # Load transactions from SQLite
    transactions = repo.get_all()[:40]  # Get first 40

    tx_list = []
    for tx in transactions:
        tx_list.append({
            "txn_id": tx.txn_id,
            "amount": tx.amount,
            "type": tx.type,  # credit or debit
            "merchant": tx.merchant_name,
            "date": tx.date,
            "category": tx.category
        })

    return render_template("transactions.html", txns=tx_list)


@app.route("/transaction/<txn_id>")
@require_auth(allow_guest=True)
def transaction_detail(txn_id):
    """View detailed transaction information"""
    # Get transaction from database
    transaction = Transaction.query.filter_by(txn_id=txn_id).first()
    
    if not transaction:
        return "Transaction not found", 404
    
    return render_template("transaction_detail.html", txn=transaction)


# ---------------------- DOWNLOAD ATTACHMENT ----------------------
@app.route("/download/<message_id>/<attachment_id>/<filename>")
def download(message_id, attachment_id, filename):
    if "credentials" not in session:
        flash("Google login required to download Gmail attachments.", "error")
        return redirect(url_for("receipts_page"))

    creds = Credentials(**session["credentials"])
    gmail = build("gmail", "v1", credentials=creds)

    attachment = gmail.users().messages().attachments().get(
        userId="me",
        messageId=message_id,
        id=attachment_id
    ).execute()

    file_data = base64.urlsafe_b64decode(attachment["data"])

    return send_file(
        BytesIO(file_data),
        as_attachment=True,
        download_name=filename,
        mimetype="application/pdf"
    )


# ---------------------- SYNC GMAIL DATA ----------------------
@app.route("/sync")
@require_auth()
def sync_gmail():
    try:
        # Run Gmail sync with LLM extraction
        result = sync_all_gmail_data(session["credentials"])
        
        # Format success message
        tx_result = result.get('transactions', {})
        receipt_result = result.get('receipts', {})
        
        message = f"Sync completed! "
        message += f"Transactions: {tx_result.get('new_transactions', 0)} new, {tx_result.get('skipped', 0)} skipped. "
        message += f"Receipts: {receipt_result.get('new_receipts', 0)} new, {receipt_result.get('skipped', 0)} skipped."
        
        flash(message, 'success')
    except Exception as e:
        flash(f"Sync error: {str(e)}", 'error')
    
    return redirect(url_for("dashboard_analytics"))


@app.route("/sync/api")
@require_auth(api=True)
def sync_gmail_api():
    """API endpoint for AJAX sync requests"""
    try:
        result = sync_all_gmail_data(session["credentials"])
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ---------------------- DEBUG/ADMIN ROUTES ----------------------
@app.route("/api/debug/transactions")
def debug_transactions():
    """View all transactions in database (JSON)"""
    transactions = repo.get_all()
    return jsonify({
        "count": len(transactions),
        "transactions": [t.to_dict() for t in transactions]
    })


@app.route("/api/debug/receipts")
def debug_receipts():
    """View all receipts in database (JSON)"""
    receipts = ReceiptRepository.get_all() if hasattr(ReceiptRepository, 'get_all') else []
    return jsonify({
        "count": len(receipts),
        "receipts": [r.to_dict() for r in receipts]
    })


@app.route("/api/debug/stats")
def debug_stats():
    """View database statistics"""
    transactions = repo.get_all()
    receipts = ReceiptRepository.get_all() if hasattr(ReceiptRepository, 'get_all') else []
    
    credit_txns = [t for t in transactions if t.type == 'credit']
    debit_txns = [t for t in transactions if t.type == 'debit']
    
    return jsonify({
        "database_file": "lumen_transactions.db",
        "transactions": {
            "total": len(transactions),
            "credit": len(credit_txns),
            "debit": len(debit_txns),
            "total_credit_amount": sum(t.amount or 0 for t in credit_txns),
            "total_debit_amount": sum(t.amount or 0 for t in debit_txns)
        },
        "receipts": {
            "total": len(receipts),
            "total_amount": sum(r.total_amount or 0 for r in receipts) if receipts else 0
        }
    })


# ---------------------- NEW TRANSACTION DB ROUTES ----------------------
@app.route("/init-db")
def init_db_route():
    """
    Initialize/reinitialize the transaction database.
    Creates tables if they don't exist.
    """
    try:
        print("\n" + "="*80)
        print("🔧 Manual database initialization requested")
        print("="*80)
        
        with app.app_context():
            db.create_all()
            
            db_file_path = os.path.join(os.getcwd(), 'lumen_transactions.db')
            if os.path.exists(db_file_path):
                print("✅ Database tables created/verified: lumen_transactions.db")
                print("📊 Table: transactions")
                
                return "✔ Database initialized"
            else:
                return jsonify({
                    "success": False,
                    "message": "Database file was not created"
                }), 500
                
    except Exception as e:
        error_msg = f"Database initialization error: {str(e)}"
        print(f"❌ {error_msg}")
        return jsonify({
            "success": False,
            "error": error_msg
        }), 500


@app.route("/save-transaction", methods=['POST'])
def save_transaction():
    """
    Save a transaction to the database via JSON POST.
    
    Expected JSON fields (matching schema):
    {
        "txn_id": "TXN_...",
        "description": "...",
        "clean_description": "...",
        "merchant_name": "...",
        "payment_channel": "...",
        "amount": 100.0,
        "type": "debit",
        "date": "2025-11-15",
        "weekday": "Friday",
        "time_of_day": "14:30",
        "balance_after_txn": 5000.0,
        "category": "Food",
        "subcategory": "Restaurant",
        "is_recurring": false,
        "recurrence_interval": null,
        "confidence_score": 0.95,
        "is_suspicious": false,
        "embedding_version": 1,
        "raw_email_snippet": "..."
    }
    """
    data = request.json

    if not data:
        return jsonify({"success": False, "error": "No JSON received"}), 400

    if repo.exists(data["txn_id"]):
        return jsonify({"success": False, "duplicate": True})

    repo.add(data)
    return jsonify({"success": True})


@app.route("/api/transactions/all", methods=['GET'])
def get_all_transactions():
    """Get all transactions from the database"""
    try:
        transactions = repo.get_all()
        return jsonify({
            "success": True,
            "count": len(transactions),
            "transactions": [t.to_dict() for t in transactions]
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ---------------------- DASHBOARD (ANALYTICS) PAGE ----------------------
@app.route("/dashboard-analytics")
@require_auth(allow_guest=True)
def dashboard_analytics():
    """Dashboard - Anomalies and Analytics page"""
    return render_template("anomalies.html")


@app.route("/api/dashboard-data")
def dashboard_data():
    """
    API endpoint for dashboard data (charts.js compatibility).
    Returns basic chart data for dashboard.
    """
    try:
        print("📊 Dashboard data requested")
        return jsonify(build_dashboard_payload(repo.get_all()))
        
    except Exception as e:
        print(f"❌ Dashboard data error: {str(e)}")
        import traceback
        traceback.print_exc()

        return jsonify(build_dashboard_error_payload(str(e))), 500


@app.route("/api/anomalies-data")
def anomalies_data():
    """
    API endpoint for analytics data with caching.
    Returns charts, insights, and anomalies.
    Supports ?month=2&year=2026 for monthly distribution data.
    """
    try:
        # Get filters from query params
        month = request.args.get('month')
        year = request.args.get('year')
        
        # Use a parameterized cache key
        cache_key = f"analytics_report_{month or 'latest'}_{year or 'latest'}"
        
        # Check cache first
        cached_data = analytics_cache.get(cache_key)
        
        if cached_data:
            return jsonify({
                "success": True,
                "cached": True,
                **cached_data
            })
        
        # Generate fresh analytics report
        report = generate_analytics_report(app, month=month, year=year)
        
        # Cache the result (for example, for 1 hour)
        analytics_cache.set(cache_key, report)
        
        return jsonify({
            "success": True,
            "cached": False,
            **report
        })
        
    except Exception as e:
        print(f"❌ Analytics error: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            "success": False,
            "error": str(e),
            "ai_summary": "Unable to load AI insights. Showing basic analytics.",
            "pie_chart": None,
            "top4_chart": None,
            "daily_chart": None,
            "monthly_chart": None,
            "debit_total": 0,
            "credit_total": 0,
            "net_flow": 0,
            "patterns": [],
            "suspicious": [],
            "recommendations": ["Please check system logs for errors"]
        }), 500


# ---------------------- UPLOAD RECEIPT (OCR) ----------------------
@app.route("/upload-receipt", methods=["POST"])
def upload_receipt():
    """
    Handle receipt uploads by delegating orchestration to the service layer.
    """
    payload, status_code = process_receipt_upload(request.files.get("file"), project_dir)
    return jsonify(payload), status_code


# ---------------------- WISHLIST SYSTEM ----------------------
@app.route("/wishlist")
@require_auth()
def wishlist_page():
    """Wishlist & Smart Advisor page"""
    user_email = get_or_cache_user_email()
    if not user_email:
        return redirect(url_for("index"))
    
    # Get wishlist items for user
    wishlist_items = WishlistRepository.get_by_user(user_email)
    items = serialize_wishlist_items(wishlist_items)
    
    # Count for navbar badge
    wishlist_count = len(items)
    
    return render_template("wishlist.html", wishlist_items=items, wishlist_count=wishlist_count)


@app.route("/wishlist/add", methods=["POST"])
@require_auth(api=True)
def add_wishlist_item():
    """Add item to wishlist with auto-categorization"""
    try:
        user_email = get_or_cache_user_email()
        if not user_email:
            return jsonify({"success": False, "error": "Not authenticated"}), 401
        
        # Get form data
        data = request.get_json() if request.is_json else request.form
        item_name = data.get("item_name", "").strip()
        expected_price = float(data.get("expected_price", 0))
        notes = data.get("notes", "").strip()
        
        if not item_name or expected_price <= 0:
            return jsonify({"success": False, "error": "Invalid item name or price"}), 400
        
        # Auto-categorize using AI (simple keyword matching for now)
        category = categorize_item(item_name)
        
        # Add to database
        success, wishlist_id = WishlistRepository.add_item(
            user_email=user_email,
            item_name=item_name,
            expected_price=expected_price,
            category=category,
            notes=notes
        )
        
        if success:
            return jsonify({
                "success": True,
                "message": f"Added {item_name} to wishlist",
                "wishlist_id": wishlist_id,
                "category": category
            })
        else:
            return jsonify({"success": False, "error": "Failed to add item"}), 500
            
    except ValueError:
        return jsonify({"success": False, "error": "Invalid price format"}), 400
    except Exception as e:
        print(f"❌ Error adding wishlist item: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/wishlist/delete/<wishlist_id>", methods=["POST"])
@require_auth(api=True)
def delete_wishlist_item(wishlist_id):
    """Delete wishlist item"""
    try:
        success, message = WishlistRepository.delete_item(wishlist_id)
        
        if success:
            return jsonify({"success": True, "message": message})
        else:
            return jsonify({"success": False, "error": message}), 404
            
    except Exception as e:
        print(f"❌ Error deleting wishlist item: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/wishlist/advice/<wishlist_id>")
@require_auth(api=True)
def get_wishlist_advice(wishlist_id):
    """Get AI-powered purchase advice for a wishlist item"""
    try:
        # Get wishlist item
        item = WishlistRepository.get_by_id(wishlist_id)
        
        if not item:
            return jsonify({"success": False, "error": "Item not found"}), 404
        
        # Get user's transactions for analytics
        transactions = repo.get_all()
        
        # Import AI advisor
        from modules.wishlist.ai_advisor import get_purchase_advice, build_analytics_summary
        
        # Build analytics summary
        analytics_summary = build_analytics_summary(transactions, item.category or "uncategorized")
        
        # Get AI advice
        advice = get_purchase_advice(
            item_name=item.item_name,
            expected_price=item.expected_price,
            category=item.category or "uncategorized",
            user_analytics=analytics_summary
        )
        
        return jsonify({
            "success": True,
            "item": {
                "name": item.item_name,
                "price": item.expected_price,
                "category": item.category
            },
            "advice": advice
        })
        
    except Exception as e:
        print(f"❌ Error getting wishlist advice: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


# ---------------------- MCP API ENDPOINTS ----------------------
# Model Context Protocol - Secure control layer between LLM and backend

@app.route("/api/mcp/tools")
def mcp_tools():
    """
    MCP Tool Discovery Endpoint.
    Returns list of available tools and their schemas.
    The LLM uses this to know what actions it can take.
    """
    try:
        tools = mcp_server.get_available_tools()
        return jsonify({
            "success": True,
            "tool_count": len(tools),
            "tools": tools,
            "info": {
                "description": "MCP tools for Project LUMEN financial assistant",
                "security": "All tools are read-only. LLM cannot access database or tokens directly."
            }
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/api/mcp/execute", methods=["POST"])
def mcp_execute():
    """
    MCP Tool Execution Endpoint.
    Executes a specific tool with given arguments.
    Useful for testing tools without LLM.
    """
    try:
        data = request.get_json()
        
        if not data or "tool" not in data:
            return jsonify({
                "success": False,
                "error": "Missing 'tool' in request body"
            }), 400
        
        tool_name = data["tool"]
        arguments = data.get("arguments", {})
        
        result = mcp_server.execute_tool(tool_name, arguments)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/api/mcp/chat", methods=["POST"])
@require_auth(api=True)
def mcp_chat():
    """
    MCP Chat Endpoint.
    Handles natural language questions via MCP → LLM flow.
    
    Request:
        {"message": "Why did I overspend this month?"}
    
    Response:
        {
            "success": true,
            "response": "Looking at your spending data...",
            "tools_used": ["get_monthly_spending_summary", "get_top_spending_categories"]
        }
    """
    try:
        data = request.get_json()
        
        if not data or "message" not in data:
            return jsonify({
                "success": False,
                "error": "Missing 'message' in request body"
            }), 400
        
        user_message = data["message"]
        
        # Route through MCP server
        result = mcp_server.chat(user_message)
        
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ MCP Chat error: {str(e)}")
        return jsonify({
            "success": False,
            "response": "An error occurred while processing your request.",
            "tools_used": [],
            "error": str(e)
        }), 500


@app.route("/api/llm/status")
def llm_status():
    """
    LLM Status Endpoint.
    Returns current LLM provider configuration and availability.
    
    Response:
        {
            "provider": "auto",
            "local": {"available": true, "model": "..."},
            "groq": {"available": true, "model": "..."}
        }
    """
    try:
        status = mcp_server.get_llm_status()
        return jsonify({
            "success": True,
            **status
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ---------------------- LOGOUT ----------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# ---------------------- HEALTH CHECK ----------------------
@app.route("/healthz")
def healthz():
    db_exists = os.path.exists(db_path)
    status = 200 if db_exists else 503
    return jsonify({
        "status": "ok" if db_exists else "degraded",
        "environment": APP_ENV,
        "database_file": db_path,
        "database_available": db_exists
    }), status


# ---------------------- RUN ----------------------
if __name__ == "__main__":
    app.run(
        host=os.getenv("FLASK_HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "0") == "1"
    )