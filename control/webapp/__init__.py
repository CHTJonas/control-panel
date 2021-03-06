import logging

from flask import Flask

from . import utils, home, member, society, signup, jobs, admin
from .flask_seasurf import SeaSurf
from flask_talisman import Talisman


app = Flask(__name__,
            template_folder="../templates",
            static_folder="../static")

app.config['CSRF_CHECK_REFERER'] = False
csrf = SeaSurf(app)
Talisman(app)

logging.basicConfig(level=logging.DEBUG if app.debug else logging.INFO)

utils.setup_app(app)

app.register_blueprint(home.bp)
app.register_blueprint(member.bp)
app.register_blueprint(society.bp)
app.register_blueprint(signup.bp)
app.register_blueprint(jobs.bp)
app.register_blueprint(admin.bp)
