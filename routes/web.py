from flask import Blueprint, render_template
from infrastructure.logger import get_logger

web_bp = Blueprint('web_bp', __name__)

logger = get_logger(__name__)

@web_bp.route('/')
def index():
    logger.info("Rendering index page")
    return render_template('index.html')
