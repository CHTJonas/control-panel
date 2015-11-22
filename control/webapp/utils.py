from functools import partial

import flask
import jinja2
import sqlalchemy.orm
import raven.flask_glue
import raven.demoserver as raven_demoserver

import srcf.database
import srcf.database.queries

from ..utils import *


__all__ = ["email_re", "raven", "srcf_db_sess", "get_member", "get_society",
           "temp_mysql_conn", "setup_app", "ldapsearch"]


raven = raven.flask_glue.AuthDecorator(desc="SRCF control panel")


# A session to use with the main srcf admin database (PostGres)
srcf_db_sess = sqlalchemy.orm.scoped_session(
    srcf.database.Session,
    scopefunc=flask._request_ctx_stack.__ident_func__
)

# Use the request session in srcf.database.queries
get_member = partial(srcf.database.queries.get_member,  session=srcf_db_sess)
def get_society(name):
    soc = srcf.database.queries.get_society(name, session=srcf_db_sess)
    # Fix up pending_admins to remove already approved ones
    soc.pending_admins = [x for x in soc.pending_admins if not x.crsid in (y.crsid for y in soc.admins)]
    return soc

# We occasionally need a temporary MySQL connection
def temp_mysql_conn():
    if not hasattr(flask.g, "mysql"):
        # A throwaway connection
        flask.g.mysql = mysql_conn()
    return flask.g.mysql


# Template helpers
def sif(variable, val):
    """"string if": `val` if `variable` is defined and truthy, else ''"""
    if not jinja2.is_undefined(variable) and variable:
        return val
    else:    
        return ""


def setup_app(app):
    @app.before_request
    def before_request():
        if hasattr(app, "deploy_config") and "test_raven" in app.deploy_config and app.deploy_config["test_raven"]:
            raven.request_class = raven_demoserver.Request
            raven.response_class = raven_demoserver.Response

    app.before_request(raven.before_request)

    @app.teardown_request
    def teardown_request(res):
        srcf_db_sess.remove()
        return res

    @app.teardown_request
    def teardown_request(res):
        if hasattr(flask.g, "mysql"):
            flask.g.mysql.close()

    app.jinja_env.globals["sif"] = sif
    app.jinja_env.tests["admin"] = is_admin
    app.jinja_env.undefined = jinja2.StrictUndefined
