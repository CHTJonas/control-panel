from urllib.parse import urlparse

from flask import Blueprint, render_template, request, redirect, url_for
from werkzeug.exceptions import NotFound, Forbidden

from .utils import srcf_db_sess as sess
from .utils import parse_domain_name, create_job_maybe_email_and_redirect, find_member
from . import utils, inspect_services
from srcf.controllib import jobs
from srcf.database import Domain
from srcf import domains

import re

import string

bp = Blueprint("member", __name__)


@bp.route('/member')
def home():
    crsid, mem = find_member(allow_inactive=True)
    if not mem.user:
        return redirect(url_for('member.reactivate'))

    inspect_services.lookup_all(mem)

    return render_template("member/home.html", member=mem)

@bp.route("/reactivate", methods=["GET", "POST"])
def reactivate():
    crsid, mem = find_member(allow_inactive=True)
    if mem.user:
        raise NotFound

    email = None
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        error = utils.validate_member_email(crsid, email)

    if request.method == "POST" and not error:
        return create_job_maybe_email_and_redirect(
                    jobs.Reactivate, member=mem, email=email)
    else:
        return render_template("member/reactivate.html", member=mem, email=email, error=error)

@bp.route("/member/email", methods=["GET", "POST"])
def update_email_address():
    crsid, mem = find_member()

    email = mem.email
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        if mem.email == email:
            error = "That's the address we have already."
        else:
            error = utils.validate_member_email(crsid, email)

    if request.method == "POST" and not error:
        return create_job_maybe_email_and_redirect(
                    jobs.UpdateEmailAddress, member=mem, email=email)
    else:
        return render_template("member/update_email_address.html", member=mem, email=email, error=error)

@bp.route("/member/srcf-email", methods=["GET", "POST"])
def update_email_handler():
    crsid, mem = find_member()

    mail_handler = mem.mail_handler
    if request.method == "POST":
        mail_handler = request.form.get("mail_handler", "").strip()
        if mem.mail_handler == mail_handler:
            # No change requested
            return redirect(url_for("member.home"))

    if request.method == "POST":
        if not request.form.get("confirm", ""):
            return render_template("member/update_email_handler_confirm.html", member=mem,
                        old_mail_handler=mem.mail_handler, mail_handler=mail_handler)
        else:
            return create_job_maybe_email_and_redirect(
                        jobs.UpdateMailHandler, member=mem, mail_handler=mail_handler)
    else:
        return render_template("member/update_email_handler.html", member=mem, mail_handler=mail_handler)

@bp.route("/member/mailinglist", methods=["GET", "POST"])
def create_mailing_list():
    crsid, mem = find_member()

    listname = ""
    error = None
    if request.method == "POST":
        listname = request.form.get("listname", "").strip()
        if not listname:
            error = "Please enter a list name."
        elif re.search(r"[^a-z0-9_-]", listname):
            error = "List names can only contain letters, numbers, hyphens and underscores."
        else:
            lists = inspect_services.lookup_mailinglists(crsid)
            if "{}-{}".format(crsid, listname) in lists:
                error = "This mailing list already exists."

    if request.method == "POST" and not error:
        return create_job_maybe_email_and_redirect(
                    jobs.CreateUserMailingList, member=mem,
                    listname=listname)
    else:
        return render_template("member/create_mailing_list.html", member=mem, listname=listname, error=error)

@bp.route("/member/mailinglist/<listname>/password", methods=["GET", "POST"])
def reset_mailing_list_password(listname):
    crsid, mem = find_member()

    lists = inspect_services.lookup_mailinglists(crsid)
    if listname not in lists:
        raise NotFound

    if request.method == "POST":
        return create_job_maybe_email_and_redirect(
                    jobs.ResetUserMailingListPassword, member=mem, listname=listname)
    else:
        return render_template("member/reset_mailing_list_password.html", member=mem, listname=listname)

@bp.route("/member/srcf/password", methods=["GET", "POST"], defaults={"type": "srcf"})
@bp.route("/member/mysql/password", methods=["GET", "POST"], defaults={"type": "mysql"})
@bp.route("/member/postgres/password", methods=["GET", "POST"], defaults={"type": "postgres"})
def reset_password(type):
    crsid, mem = find_member()

    if request.method == "POST":
        cls = {"mysql": jobs.ResetMySQLUserPassword,
               "postgres": jobs.ResetPostgresUserPassword,
               "srcf": jobs.ResetUserPassword}[type]
        return create_job_maybe_email_and_redirect(cls, member=mem)
    else:
        formatted_name = {"mysql": "MySQL",
                          "postgres": "PostgreSQL",
                          "srcf": "SRCF"}[type]
        web_interface = {"mysql": "phpMyAdmin",
                         "postgres": "phpPgAdmin",
                         "srcf": None}[type]

        if type == "srcf":
            affects = "password-based access to the shell service and SFTP"
        else:
            affects = "access to " + web_interface + ", as well as any scripts that access databases using your account"

        return render_template("member/reset_password.html", member=mem, type=type, name=formatted_name, affects=affects)

@bp.route("/member/mysql/createuser", methods=["GET", "POST"], defaults={"type": "mysql"})
@bp.route("/member/postgres/createuser", methods=["GET", "POST"], defaults={"type": "postgres"})
def create_database_account(type):
    crsid, mem = find_member()

    if request.method == "POST":
        cls = {"mysql": jobs.ResetMySQLUserPassword,
               "postgres": jobs.ResetPostgresUserPassword}[type]
        return create_job_maybe_email_and_redirect(cls, member=mem)
    else:
        formatted_name = {"mysql": "MySQL",
                          "postgres": "PostgreSQL"}[type]

        return render_template("member/create_database_account.html", member=mem, type=type, name=formatted_name)

@bp.route("/member/mysql/create",    methods=["GET", "POST"], defaults={"type": "mysql"})
@bp.route("/member/postgres/create", methods=["GET", "POST"], defaults={"type": "postgres"})
def create_database(type):
    crsid, mem = find_member()

    if request.method == "POST":
        cls = {"mysql": jobs.CreateMySQLUserDatabase,
               "postgres": jobs.CreatePostgresUserDatabase}[type]
        return create_job_maybe_email_and_redirect(cls, member=mem)
    else:
        formatted_name = {"mysql": "MySQL",
                          "postgres": "PostgreSQL"}[type]
        inspect = {"mysql": inspect_services.lookup_mysqluser,
                   "postgres": inspect_services.lookup_pguser}[type]
        has_user = inspect(mem.crsid)
        return render_template("member/create_database.html", member=mem, type=type, name=formatted_name, user=has_user)

@bp.route("/member/domains/add", methods=["GET", "POST"])
def add_vhost():
    crsid, mem = find_member()

    domain = ""
    root = ""
    errors = {}

    if request.method == "POST":

        domain = request.form.get("domain", "").strip()
        root = request.form.get("root", "").strip()
        if domain:
            parsed = parse_domain_name(domain)
            if domain != parsed:
                domain = parsed
                errors["domain"] = "We've corrected your input to just the domain name, submit again once you've checked it's correct."
            elif "." not in domain:
                errors["domain"] = "Please enter a fully-qualified domain name."
            elif domain.endswith("." + crsid + ".user.srcf.net"):
                pass
            elif domain.endswith(".user.srcf.net") or domain.endswith(".soc.srcf.net"):
                errors["domain"] = "SRCF domains can't be registered here."
            elif sess.query(Domain).filter(Domain.domain == domain).count():
                errors["domain"] = "This domain is already registered."
        else:
            errors["domain"] = "Please enter a domain or subdomain."

        if request.form.get("edit") or errors:
            return render_template("member/add_vhost.html", member=mem, domain=domain, root=root, errors=errors)
        elif not request.form.get("confirm"):
            valid = {}
            prefixed = "www.{}".format(domain)
            for d in (domain, prefixed):
                valid[d] = domains.verify(d)
            good = all(v == (True, True) for v in valid.values())
            return render_template("member/add_vhost_test.html", member=mem, domain=domain, root=root, valid=valid, good=good)
        else:
            return create_job_maybe_email_and_redirect(
                        jobs.AddUserVhost, member=mem,
                        domain=domain, root=root)

    else:
        return render_template("member/add_vhost.html", member=mem, domain=domain, root=root, errors=errors)

@bp.route("/member/domains/<domain>/changedocroot", methods=["GET", "POST"])
def change_vhost_docroot(domain):
    crsid, mem = find_member()

    errors = {}

    try:
        record = sess.query(Domain).filter(Domain.domain == domain, Domain.owner == crsid)[0]
    except IndexError:
        raise NotFound

    root = record.root.replace("public_html/", "") if record.root else ""

    if request.method == "POST":
        root = request.form.get("root", "").strip()
        if any([ch in root for ch in string.whitespace + "\\" + "\"" + "\'"]) or ".." in root:
            errors["root"] = "This document root is invalid."
        try:
            domain = parse_domain_name(domain)
        except ValueError as e:
            errors["domain"] = e.args[0]

    if request.method == "POST" and not errors:
        return create_job_maybe_email_and_redirect(
                    jobs.ChangeUserVhostDocroot, member=mem,
                    domain=domain, root=root)
    else:
        return render_template("member/change_vhost_docroot.html", member=mem, domain=domain, root=root, errors=errors)

@bp.route("/member/domains/<domain>/remove", methods=["GET", "POST"])
def remove_vhost(domain):
    crsid, mem = find_member()

    try:
        record = sess.query(Domain).filter(Domain.domain == domain)[0]
    except IndexError:
        raise NotFound
    if not record.owner == crsid:
        raise Forbidden

    if request.method == "POST":
        return create_job_maybe_email_and_redirect(
                    jobs.RemoveUserVhost, member=mem,
                    domain=domain)
    else:
        return render_template("member/remove_vhost.html", member=mem, domain=domain)
