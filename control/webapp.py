import os
import glob
import re
import functools
import operator
import ConfigParser

import flask
from flask import Flask, Request, render_template, redirect, url_for, request
import jinja2
import sqlalchemy.orm
import MySQLdb
from raven.flask_glue import AuthDecorator

import srcf.database.queries
from srcf.database.queries import get_member, get_society

from . import jobs


## App setup
app = Flask(__name__)

auth_decorator = AuthDecorator(desc="SRCF control panel")
app.before_request(auth_decorator.before_request)

# Most database is done with postgres; see `srcf.database`
# This snippet is adapted from Flask-SQLAlchemy
sess = sqlalchemy.orm.scoped_session(
    srcf.database.Session,
    scopefunc=flask._request_ctx_stack.__ident_func__
)
@app.teardown_request
def teardown_request(res):
    sess.remove()
    return res

# We occasionally need to interrogate the list of MySQL databases
my_cnf = ConfigParser.ConfigParser()
my_cnf.read("/societies/srcf-admin/.my.cnf")
mysql_passwd = my_cnf.get('client', 'password')
def mysql_connection():
    if not hasattr(flask.g, "mysql"):
        # A throwaway connection
        flask.g.mysql = \
            MySQLdb.connect(user="srcf_admin", db="srcf_admin",
                            passwd=mysql_passwd)
        flask.g.mysql.autocommit = True
    return flask.g.mysql

@app.teardown_request
def teardown_request(res):
    if hasattr(flask.g, "mysql"):
        flask.g.mysql.close()


## Template helpers
def sif(variable, val):
    """"string if": `val` if `variable` is defined and truthy, else ''"""
    if not jinja2.is_undefined(variable) and variable:
        return val
    else:    
        return ""

app.jinja_env.globals["sif"] = sif


## Helpers
def lookup_pgdbs(prefix):
    params = {'prefix': prefix, 'prefixfilter': '%s-%%' % prefix}
    # we can borrow the postgres connection we already have
    q = sess.execute('SELECT datname FROM pg_database ' \
                     'JOIN pg_roles ON datdba=pg_roles.oid ' \
                     'WHERE rolname=:prefix OR rolname LIKE :prefixfilter',
                      params)
    return [row[0] for row in q.fetchall()]

def lookup_mysqldbs(prefix):
    cur = mysql_connection().cursor()
    perfix = prefix.replace("-", "_")
    q = "SELECT SCHEMA_NAME FROM information_schema.schemata WHERE " \
        "SCHEMA_NAME = %s OR SCHEMA_NAME LIKE %s"
    cur.execute(q, (prefix, prefix + '/%'))
    return [row[0] for row in cur]


def lookup_lists(prefix):
    patterns = "/var/lib/mailman/lists/%s-*" % prefix
    return [os.path.basename(ldir) for ldir in glob.iglob(patterns)]

@app.route('/')
def home():
    crsid = auth_decorator.principal

    try:
        mem = get_member(crsid)
    except KeyError:
        return redirect(url_for('signup'))

    mem.mysqldbs = lookup_mysqldbs(crsid)
    mem.pgdbs = lookup_pgdbs(crsid)
    mem.lists = lookup_lists(crsid)
    for soc in mem.societies:
        soc.mysqldbs = lookup_mysqldbs(soc.society)
        soc.pgdbs = lookup_pgdbs(soc.society)
        soc.lists = lookup_lists(soc.society)

    return render_template("home.html", member=mem)


# yeah whatever.
email_re = re.compile(b"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z][A-Za-z]+$")

@app.route("/signup", methods=["get", "post"])
def signup():
    crsid = auth_decorator.principal

    try:
        mem = get_member(crsid)
    except KeyError:
        pass
    else:
#        return redirect(url_for('home'))
        pass

    if request.method == 'POST':
        values = {}
        for key in ("preferred_name", "surname", "email"):
            values[key] = request.form.get(key, "")
        for key in ("dpa", "tos", "social"):
            values[key] = bool(request.form.get(key, False))

        errors = {
            "preferred_name": values["preferred_name"] == "",
            "surname": values["surname"] == "",
            "email": not email_re.match(values["email"]),
            "dpa": not values["dpa"],
            "tos": not values["tos"],
            "social": False
        }

        any_error = functools.reduce(operator.or_, errors.values())

        if any_error:
            return render_template("signup.html", crsid=crsid, errors=errors, **values)
        else:
            del values["dpa"], values["tos"]
            j = jobs.Signup.new(crsid=crsid, **values)
            sess.add(j.row)
            sess.commit()

    else:
        # defaults
        values = {
            "preferred_name": "",
            "surname": "",
            "email": crsid + "@cam.ac.uk",
            "dpa": False,
            "tos": False,
            "social": True
        }

        return render_template("signup.html", crsid=crsid, errors={}, **values)
