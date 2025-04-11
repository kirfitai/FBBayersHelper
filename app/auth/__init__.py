from flask import Blueprint, redirect, url_for

bp = Blueprint('auth', __name__)

# Редирект со старой страницы настроек на управление токенами
@bp.route('/fb_settings')
def old_fb_settings_redirect():
    return redirect(url_for('auth.manage_tokens'))

from app.auth import routes