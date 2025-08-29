import os
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, current_app
import uuid
import fitz
from werkzeug.utils import secure_filename
from infrastructure.logger import get_logger
from openai import OpenAI
from docx import Document
from ingestion.extract import extract_docx_text, extract_pdf_text
from .database import get_db, upsert_document

corpus_bp = Blueprint('corpus_bp', __name__, url_prefix='/corpus')

logger = get_logger(__name__)

ALLOWED_EXTENSIONS = {"pdf", "doc", "docx"}

def _get_text(file_path) -> str:
	"""Extract the title from the document."""
	if file_path.endswith(".pdf"):
		return extract_pdf_text(file_path)
	elif file_path.endswith((".doc", ".docx")):
		return extract_docx_text(file_path)
	return "Untitled"

def _get_title(file_path) -> str:
	"""Extract the title from the document."""
	if file_path.endswith(".pdf"):
		return _extract_pdf_title(file_path)
	elif file_path.endswith((".doc", ".docx")):
		return _extract_docx_title(file_path)
	return "Untitled"

def _extract_docx_title(file_path) -> str:
	"""Extract the title from a DOCX (or fallback) document.

	We approximate the *first page* by gathering paragraph text until we hit
	either an explicit page break or a character budget (~8000 chars), then
	ask the OpenAI model (gpt-5) to return ONLY the title or "Unknown".
	For legacy .doc (application/msword) we currently return "Unknown" since
	python-docx cannot parse that binary format.
	"""
	# Reject classic .doc early; python-docx can't parse it.

	try:
		data = Document(file_path)
		if not data:
			return "Unknown"
		doc = data

		# Gather paragraphs until a page break (if detectable) or char limit.
		snippets = []
		char_limit = 8000
		total = 0
		for para in doc.paragraphs:
			txt = (para.text or '').strip()
			if txt:
				snippets.append(txt)
				total += len(txt)
			# Heuristic page break detection: explicit breaks inside runs
			page_break = False
			for run in para.runs:
				# python-docx represents breaks as <w:br w:type="page"/>; we can
				# inspect the XML for 'type="page"'
				if any(br.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}type') == 'page' for br in run._r.findall('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}br')):  # type: ignore[attr-defined]
					page_break = True
					break
			if page_break or total >= char_limit:
				break

		if not snippets:
			return "Unknown"

		snippet = "\n".join(snippets)[:char_limit]
		snippet = snippet.strip()
		if not snippet:
			return "Unknown"

		api_key = current_app.config.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
		if not api_key:
			return "Unknown"
		base_url = current_app.config.get("OPENAI_BASE_URL") or os.getenv("OPENAI_BASE_URL") or None
		client = OpenAI(api_key=api_key, base_url=base_url)

		prompt = (
			"Extract the document's title from the following first page text of a Word (DOCX) document.\n"
			"Return ONLY the title (no quotes, no extra words). If you cannot confidently identify a distinct title, respond exactly with: Unknown\n\n"
			"--- PAGE TEXT START ---\n"
			f"{snippet}\n"
			"--- PAGE TEXT END ---"
		)
		model = "gpt-5"
		try:
			resp = client.chat.completions.create(
				model=model,
				messages=[
					{"role": "system", "content": "You extract concise titles from documents."},
					{"role": "user", "content": prompt},
				],
				temperature=0,
			)
			content = resp.choices[0].message.content if resp.choices else ""
			candidate = (content or "").strip()
			if not candidate:
				return "Unknown"
			title_line = next((ln.strip() for ln in candidate.splitlines() if ln.strip()), "")
			title_line = title_line.strip('"\' ')
			if not title_line or title_line.lower() == "unknown" or len(title_line) > 200:
				return "Unknown"
			return title_line
		except Exception:
			logger.exception("Title extraction model call failed (DOCX)")
			return "Unknown"
	except Exception:
		logger.exception("DOCX title extraction failed")
		return "Unknown"

def _extract_pdf_title(file) -> str:
	"""Extract the title from a PDF document."""
	# We read the uploaded FileStorage stream into memory (first page only) and
	# ask the OpenAI model (gpt-5) to identify a title. Falls back to "Unknown".
	try:
		pos = file.stream.tell()
		data = file.read()
		if not data:
			return "Unknown"
		pdf = fitz.open(stream=data, filetype="pdf")  # type: ignore
		if len(pdf) == 0:
			return "Unknown"
		page = pdf[0]
		text = (page.get_text() or "").strip()
		pdf.close()
		if not text:
			return "Unknown"
		snippet = text[:8000]
		api_key = current_app.config.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
		if not api_key:
			return "Unknown"
		base_url = current_app.config.get("OPENAI_BASE_URL") or os.getenv("OPENAI_BASE_URL") or None
		client = OpenAI(api_key=api_key, base_url=base_url)
		prompt = (
			"Extract the document's title from the following first PDF page text.\n"
			"Return ONLY the title (no quotes, no extra words). If you cannot confidently identify a distinct title, respond exactly with: Unknown\n\n"
			"--- PAGE TEXT START ---\n"
			f"{snippet}\n"
			"--- PAGE TEXT END ---"
		)
		model = "gpt-5"
		try:
			resp = client.chat.completions.create(
				model=model,
				messages=[
					{"role": "system", "content": "You extract concise titles from documents."},
					{"role": "user", "content": prompt},
				],
				temperature=0,
			)
			content = resp.choices[0].message.content if resp.choices else ""
			candidate = (content or "").strip()
			if not candidate:
				return "Unknown"
			title_line = next((ln.strip() for ln in candidate.splitlines() if ln.strip()), "")
			title_line = title_line.strip('"\' ')
			if not title_line or title_line.lower() == "unknown" or len(title_line) > 200:
				return "Unknown"
			return title_line
		except Exception:
			logger.exception("Title extraction model call failed")
			return "Unknown"
	finally:
		try:
			file.stream.seek(pos)  # type: ignore[attr-defined]
		except Exception:
			pass

def allowed_file(filename: str) -> bool:
	return "." in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@corpus_bp.route('/add-doc', methods=['POST'])
def add_doc():
	"""Accept a single PDF/Word document upload and store it locally.

	Request: multipart/form-data with field name 'file'.
	Response: JSON { message, filename }
	"""
	if 'file' not in request.files:
		logger.warning("Upload attempted without 'file' in form data")
		return jsonify({"error": "No file part"}), 400

	file = request.files['file']

	if not file.filename:
		logger.warning("Upload attempted with empty filename")
		return jsonify({"error": "No selected file"}), 400

	# mypy/pyright: filename can be Optional[str]; guard above ensures truthy
	filename_value = file.filename  # type: ignore[assignment]
	if not allowed_file(filename_value):
		logger.warning("Rejected file with disallowed extension: %s", file.filename)
		return jsonify({"error": "Unsupported file type. Allowed: PDF, DOC, DOCX"}), 400

	# Ensure uploads directory exists (configurable via UPLOAD_FOLDER or default to ./uploads)
	upload_folder = os.getenv('UPLOAD_FOLDER', None) or os.path.join(current_app.root_path, 'uploads')
	os.makedirs(upload_folder, exist_ok=True)

	doc_id = str(uuid.uuid4())
	base_name = secure_filename(filename_value)
	formatted_ts = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')  # for unique names
	mtime_epoch = int(datetime.now(timezone.utc).timestamp())  # seconds since epoch fits in 64-bit
	name, ext = os.path.splitext(base_name)
	stored_filename = f"{name}_{formatted_ts}{ext.lower()}"  # noqa: F841 (may be used later)
	file_path = os.path.join(upload_folder, doc_id)


	try:
		file.save(file_path)
	except Exception as e:
		logger.exception("Failed to save uploaded file: %s", e)
		return jsonify({"error": "Failed to save file"}), 500

	logger.info("Stored uploaded document: %s", doc_id)

	text = _get_text(file_path)

	upsert_document(db=get_db(), doc_id=doc_id, source_path=file_path, norm_text=text, mtime=mtime_epoch)

	return jsonify({
		"message": "Document uploaded successfully.",
		"filename": doc_id
	}), 201
