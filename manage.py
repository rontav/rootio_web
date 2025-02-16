#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os, sys
import subprocess
import time

from flask.ext.script import Manager, Shell

from rootio.app import create_app
from rootio.extensions import db

from rootio.radio import Station, Language
from rootio.user import User, UserDetail, ADMIN, ACTIVE
from rootio.utils import MALE

from alembic import command
from alembic.config import Config
from rootio.config import DefaultConfig


def _make_context():
    from rootio.extensions import db
    import rootio.telephony as t
    import rootio.user as u
    import rootio.radio as r
    return dict(db=db, u=u.models, t=t.models, r=r.models)


app = create_app()
manager = Manager(app)
manager.add_command("sh", Shell(make_context=_make_context))


alembic_config = Config(os.path.realpath(os.path.dirname(__name__)) + "/alembic.ini")


def easy():
    """ pre import some things """
    from rootio.extensions import db
    import rootio.telephony as t
    import rootio.user as u
    import rootio.radio as r

@manager.command
def run():
    """Run webserver for local development."""
    app.run(debug=True, use_reloader=True, host='0.0.0.0', port=8080)

@manager.command
def vscodedebug():
    """Run webserver for debug development."""
    app.run(debug=False, use_reloader=False, host='0.0.0.0', port=8081)

@manager.command
def waitress(bind_address='127.0.0.1', port=8080):
    """Run with waitress for production."""
    import waitress
    waitress.serve(app.wsgi_app, host=bind_address, port=port)

@manager.command
def alembic():
    """Run in local machine."""
    subprocess.call(["venv/bin/alembic", "init", "alembic"])

@manager.command
def migrate(direction):
    """Migrate db revision"""
    if direction == "up":
        command.upgrade(alembic_config, "head")
    elif direction == "down":
        command.downgrade(alembic_config, "-1")

@manager.command
def migration(message):
    """Create migration file"""
    command.revision(alembic_config, autogenerate=True, message=message)

@manager.command
def stamp(revision):
    """Fake a migration to a particular revision"""
    alembic_cfg = Config("alembic.ini")
    command.stamp(alembic_cfg, revision)

@manager.command
def reset_db(noinput=False):
    """Reset database"""

    if not noinput:
        print "WARNING: This will reset the database and may cause data loss."
        response = raw_input("Are you sure you want to continue? (Yes/No) ")
        if not response == "Yes":
            print "Aborted."
            sys.exit()

    db.drop_all()
    db.create_all()

    admin = User(
            name=u'admin',
            email=u'admin@example.com',
            password=u'123456',
            role_code=ADMIN,
            status_code=ACTIVE,
            user_detail=UserDetail(
                gender_code=MALE,
                age=25,
                url=u'http://example.com',
                location=u'Kampala',
                bio=u''))
    db.session.add(admin)
    
    english = Language(name="English",iso639_1="en",iso639_2="eng",locale_code="en_UG")
    db.session.add(english)
    luganda = Language(name="Luganda",iso639_1="lg",iso639_2="lug",locale_code="lg_UG")
    db.session.add(luganda)

    db.session.commit()
    alembic_cfg = Config("alembic.ini")
    command.stamp(alembic_cfg, "head")

manager.add_option('-c', '--config',
                   dest="config",
                   required=False,
                   help="config file")

@manager.command
def demo_data(schedule=0):
    from rootio import demo_data
    demo_data.setup(db, int(schedule))

@manager.command
def drop_db_hard():
    #for when db.drop_all won't cut it, particularly with postgres on server

    print "WARNING: This will drop all database tables."
    response = raw_input("Are you sure you want to continue? (Yes/No) ")
    if not response == "Yes":
        print "Aborted."
        sys.exit()

    import sqlalchemy
    engine = sqlalchemy.create_engine('postgresql://postgres:NLPog1986@localhost')
    meta = sqlalchemy.MetaData(engine)
    meta.reflect()
    meta.drop_all()

@manager.command
def list_routes():
    import urllib
    from flask import url_for
    output = []
    for rule in app.url_map.iter_rules():
        options = {}
        for arg in rule.arguments:
            options[arg] = "[{0}]".format(arg)

        methods = ','.join(rule.methods)
        url = url_for(rule.endpoint, **options)
        line = urllib.unquote("{:50s} {:20s} {}".format(rule.endpoint, methods, url))
        output.append(line)

    for line in sorted(output):
        print line

@manager.command
def i18n_extract_strings():
    subprocess.call(["pybabel", "extract", "-o", "rootio/messages.pot", "rootio"])

@manager.command
def i18n_update_translation(lang):
    f = open("./rootio/translations/{}/LC_MESSAGES/messages.po".format(lang), "w")
    subprocess.call([
        "curl",
        "-s",
        "-L",
        "--user",
        "api:{}".format(DefaultConfig.TRANSIFEX_API_KEY),
        "-X",
        "GET",
        "https://www.transifex.com/api/2/project/rootio_web/resource/messagespo/translation/{}/?file".format(lang)
    ], stdout=f)

@manager.command
def i18n_update_translations():
    languages = [l for l in DefaultConfig.ACCEPT_LANGUAGES]
    skip_languages = ['en']
    for lang in languages:
        if lang not in skip_languages:
            i18n_update_translation(lang)

if __name__ == "__main__":
    manager.run()
