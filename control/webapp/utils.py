from functools import partial

import flask
import jinja2
import sqlalchemy.orm
import raven.flask_glue
import raven.demoserver as raven_demoserver

import srcf.database
import srcf.database.queries
import srcf.mail

from ..utils import *


__all__ = ["email_re", "raven", "srcf_db_sess", "get_member", "get_society",
           "temp_mysql_conn", "setup_app", "ldapsearch", "admin_auth"]


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
        if getattr(app, "deploy_config", {}).get("test_raven", False):
            raven.request_class = raven_demoserver.Request
            raven.response_class = raven_demoserver.Response

    app.before_request(raven.before_request)

    @app.after_request
    def after_request(res):
        srcf_db_sess.commit()
        return res

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


def create_job_maybe_email_and_redirect(cls, *args, **kwargs):
    j = cls.new(*args, **kwargs)
    srcf_db_sess.add(j.row)
    srcf_db_sess.flush() # so that job_id is filled out

    if j.state == "unapproved":
        body = "You can approve or reject the job here: {0}" \
                .format(url_for("admin.view_jobs", state="unapproved", _external=True))
        subject = "[Control Panel] Job #{0.job_id} {0.state} -- {0}".format(j)
        srcf.mail.mail_sysadmins(subject, body)

    return flask.redirect(flask.url_for('jobs.status', id=j.job_id))

def find_member():
    """ Gets a CRSID and member object from the Raven authentication data """
    crsid = raven.principal
    try:
        mem = get_member(crsid)
    except KeyError:
        raise NotFound

    return crsid, mem

def find_mem_society(society):
    crsid = raven.principal

    try:
        mem = get_member(crsid)
        soc = get_society(society)
    except KeyError:
        raise NotFound

    if mem not in soc.admins:
        auth_admin()

    return mem, soc

def auth_admin():
    # I think the order before_request fns are run in is undefined.
    assert raven.principal

    mem = get_member(raven.principal)
    for soc in mem.societies:
        if soc.society == "srcf-admin":
            return None
    else:
        raise Forbidden
