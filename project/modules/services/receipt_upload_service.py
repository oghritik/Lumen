"""Receipt upload orchestration service (validation, OCR, persistence)."""

import os
from datetime import datetime
from modules.database.transaction_repo import ReceiptRepository
from modules.nvidia_ocr import parse_json_safely, process_uploaded_file

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}
REQUIRED_FIELDS = ["vendor", "date", "total"]


def _error(message: str, status_code: int, **extra):
    payload = {"success": False, "error": message}
    payload.update(extra)
    return payload, status_code


def _validate_file(file_storage):
    if file_storage is None:
        return _error("No file uploaded", 400)

    if file_storage.filename == "":
        return _error("Empty filename", 400)

    file_ext = os.path.splitext(file_storage.filename)[1].lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        allowed_text = ", ".join(sorted(ALLOWED_EXTENSIONS))
        return _error(f"Invalid file type '{file_ext}'. Allowed: {allowed_text}", 400)

    file_storage.seek(0, 2)
    file_size = file_storage.tell()
    file_storage.seek(0)

    if file_size == 0:
        return _error("Uploaded file is empty", 400)

    return None, None


def _save_uploaded_file(file_storage, project_dir: str):
    upload_dir = os.path.join(project_dir, "uploads", "receipts")
    os.makedirs(upload_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_filename = f"{timestamp}_{file_storage.filename}"
    file_path = os.path.join(upload_dir, safe_filename)

    file_storage.save(file_path)
    if not os.path.exists(file_path):
        return None, None, _error("Failed to save uploaded file", 500)

    return safe_filename, file_path, None


def _parse_receipt_json(raw_text_response: str):
    if not raw_text_response:
        return None, _error("Failed to extract data from file - OCR returned no response", 400)

    if len(raw_text_response.strip()) < 10:
        return None, _error("OCR extraction failed - response too short or empty", 400)

    receipt_json = parse_json_safely(raw_text_response)
    if not receipt_json:
        return None, _error(
            "OCR returned invalid JSON. Please try with a clearer image.",
            400,
            raw_output=raw_text_response[:500],
        )

    missing_fields = [field for field in REQUIRED_FIELDS if not receipt_json.get(field)]
    if missing_fields:
        return None, _error(
            f"Missing required fields: {', '.join(missing_fields)}",
            422,
            extracted_json=receipt_json,
        )

    return receipt_json, None


def _build_receipt_data(receipt_json: dict, safe_filename: str, raw_text_response: str):
    try:
        total_amount = float(receipt_json.get("total", 0))
    except (ValueError, TypeError):
        return None, _error(f"Invalid total amount format: {receipt_json.get('total')}", 422)

    if total_amount <= 0:
        return None, _error("Total amount must be greater than 0", 422)

    now = datetime.now()
    confidence = float(receipt_json.get("confidence_score", 0))

    receipt_data = {
        "receipt_id": f"RCP_OCR_{now.strftime('%Y%m%d%H%M%S')}",
        "receipt_type": "uploaded",
        "issue_date": receipt_json.get("date", now.strftime("%Y-%m-%d")),
        "issue_time": "",
        "merchant_name": receipt_json.get("vendor", "Unknown"),
        "merchant_address": "",
        "merchant_gst": "",
        "subtotal_amount": float(receipt_json.get("subtotal", 0)),
        "tax_amount": float(receipt_json.get("tax", 0)),
        "total_amount": total_amount,
        "payment_method": receipt_json.get("payment_method", "Unknown"),
        "extracted_confidence_score": confidence,
        "is_suspicious": float(receipt_json.get("confidence_score", 100)) < 50,
        "embedding_version": 1,
        "attachment_filename": safe_filename,
        "raw_snippet": raw_text_response[:500],
    }

    return receipt_data, None


def process_receipt_upload(file_storage, project_dir: str):
    """
    Validate, OCR-process, and persist an uploaded receipt.

    Returns:
        tuple[dict, int]: Response payload and HTTP status code.
    """
    print("\n🔍 Upload receipt request received")

    error_payload, status_code = _validate_file(file_storage)
    if error_payload:
        print(f"❌ Upload validation failed: {error_payload['error']}")
        return error_payload, status_code

    safe_filename, file_path, save_error = _save_uploaded_file(file_storage, project_dir)
    if save_error:
        print(f"❌ Save failed: {save_error[0]['error']}")
        return save_error

    print(f"✅ File saved: {file_path}")
    print("🔍 Running OCR extraction...")

    raw_text_response = process_uploaded_file(file_path)
    print(f"📝 OCR response length: {len(raw_text_response) if raw_text_response else 0}")

    receipt_json, parse_error = _parse_receipt_json(raw_text_response)
    if parse_error:
        print(f"❌ OCR parse failed: {parse_error[0]['error']}")
        return parse_error

    receipt_data, mapping_error = _build_receipt_data(receipt_json, safe_filename, raw_text_response)
    if mapping_error:
        print(f"❌ Receipt mapping failed: {mapping_error[0]['error']}")
        return mapping_error

    success, message = ReceiptRepository.add_receipt(receipt_data)
    if not success:
        print(f"❌ Database insertion failed: {message}")
        return _error(f"Failed to save receipt to database: {message}", 500)

    print(f"✅ Receipt inserted successfully: {receipt_data['receipt_id']}")
    return {
        "success": True,
        "message": (
            f"Receipt processed successfully! Vendor: {receipt_data['merchant_name']}, "
            f"Total: ₹{receipt_data['total_amount']}"
        ),
        "type": "receipt",
        "data": receipt_data,
        "json_extracted": receipt_json,
    }, 200
